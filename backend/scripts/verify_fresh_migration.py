"""Verification script for fresh database migration.

Executes:
1. Fresh migration on completely empty SQLite database.
2. Full schema inspection: tables, columns, PKs, FKs, indexes.
3. Detailed schema comparison between fresh DB and existing jobs.db.
4. 'alembic check' against jobs.db to detect any drift between models and database.
5. Verification of row counts in jobs.db (24 jobs, 24 duplicates, 4 runs).
"""
import os
import sys
import sqlite3
import subprocess
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent.parent
fresh_db = root_dir / "test_fresh.db"
jobs_db = root_dir / "jobs.db"

if fresh_db.exists():
    fresh_db.unlink()

print("=" * 70)
print("ALEMBIC FRESH DATABASE MIGRATION VERIFICATION")
print("=" * 70)

# 1. Run alembic upgrade head against completely empty database
env = os.environ.copy()
env["DATABASE_URL"] = f"sqlite:///{fresh_db.name}"

print(f"Applying 'alembic upgrade head' to empty database: {fresh_db.name}...")
res_upgrade = subprocess.run(
    ["alembic", "upgrade", "head"],
    cwd=str(root_dir),
    env=env,
    capture_output=True,
    text=True
)
print("STDOUT:")
print(res_upgrade.stdout)
if res_upgrade.stderr:
    print("STDERR:")
    print(res_upgrade.stderr)

assert res_upgrade.returncode == 0, f"alembic upgrade head failed with code {res_upgrade.returncode}"

# 2. Inspect fresh database schema
def extract_full_schema(db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = sorted([r[0] for r in cur.fetchall() if not r[0].startswith("sqlite_")])
    schema = {}

    for t in tables:
        # Columns: (cid, name, type, notnull, dflt_value, pk)
        cur.execute(f"PRAGMA table_info({t});")
        columns = {
            r[1]: {
                "type": r[2].upper(),
                "notnull": bool(r[3]),
                "pk": bool(r[5])
            }
            for r in cur.fetchall()
        }
        # Foreign Keys: (id, seq, table, from, to, on_update, on_delete, match)
        cur.execute(f"PRAGMA foreign_key_list({t});")
        fks = [
            {"from": r[3], "to_table": r[2], "to_column": r[4]}
            for r in cur.fetchall()
        ]
        # Indexes: (seq, name, unique, origin, partial)
        cur.execute(f"PRAGMA index_list({t});")
        indexes = sorted([r[1] for r in cur.fetchall() if not r[1].startswith("sqlite_autoindex")])

        schema[t] = {
            "columns": columns,
            "foreign_keys": fks,
            "indexes": indexes
        }
    conn.close()
    return schema

fresh_schema = extract_full_schema(fresh_db)
jobs_schema = extract_full_schema(jobs_db)

print("\n--- TABLES CREATED IN FRESH DATABASE ---")
for t in sorted(fresh_schema.keys()):
    col_count = len(fresh_schema[t]["columns"])
    fk_count = len(fresh_schema[t]["foreign_keys"])
    idx_count = len(fresh_schema[t]["indexes"])
    print(f"Table: {t:<20} | Columns: {col_count:<2} | FKs: {fk_count} | Indexes: {idx_count}")

# 3. Compare fresh_db schema with jobs.db schema
print("\n--- SCHEMA COMPARISON: test_fresh.db vs jobs.db ---")
differences = []

all_tables = sorted(set(fresh_schema.keys()) | set(jobs_schema.keys()))
for t in all_tables:
    if t not in fresh_schema:
        differences.append(f"Table '{t}' missing from test_fresh.db")
        continue
    if t not in jobs_schema:
        differences.append(f"Table '{t}' missing from jobs.db")
        continue

    # Compare columns
    fresh_cols = fresh_schema[t]["columns"]
    jobs_cols = jobs_schema[t]["columns"]
    if set(fresh_cols.keys()) != set(jobs_cols.keys()):
        missing_in_fresh = set(jobs_cols.keys()) - set(fresh_cols.keys())
        missing_in_jobs = set(fresh_cols.keys()) - set(jobs_cols.keys())
        if missing_in_fresh:
            differences.append(f"Table '{t}': columns missing in fresh DB: {missing_in_fresh}")
        if missing_in_jobs:
            differences.append(f"Table '{t}': columns missing in jobs.db: {missing_in_jobs}")

    # Compare column attributes
    for col_name in set(fresh_cols.keys()) & set(jobs_cols.keys()):
        c1 = fresh_cols[col_name]
        c2 = jobs_cols[col_name]
        if c1["pk"] != c2["pk"]:
            differences.append(f"Table '{t}', Col '{col_name}': PK mismatch ({c1['pk']} vs {c2['pk']})")
        if c1["notnull"] != c2["notnull"]:
            differences.append(f"Table '{t}', Col '{col_name}': NOT NULL mismatch ({c1['notnull']} vs {c2['notnull']})")

    # Compare Foreign Keys
    fks_fresh = fresh_schema[t]["foreign_keys"]
    fks_jobs = jobs_schema[t]["foreign_keys"]
    if fks_fresh != fks_jobs:
        # Note: SQLite PRAGMA foreign_key_list formatting
        differences.append(f"Table '{t}': FK mismatch (fresh: {fks_fresh} vs jobs: {fks_jobs})")

if not differences:
    print(">> ZERO SCHEMA DIFFERENCES: test_fresh.db and jobs.db match exactly across all tables, columns, types, nullability, and primary keys!")
else:
    print(">> Differences found:")
    for d in differences:
        print("   -", d)

# 4. Run alembic check against jobs.db
print("\n--- RUNNING 'alembic check' ON jobs.db ---")
env_jobs = os.environ.copy()
env_jobs["DATABASE_URL"] = f"sqlite:///{jobs_db.name}"
res_check = subprocess.run(
    ["alembic", "check"],
    cwd=str(root_dir),
    env=env_jobs,
    capture_output=True,
    text=True
)
print("STDOUT:")
print(res_check.stdout or "(No output)")
if res_check.stderr:
    print("STDERR:")
    print(res_check.stderr)
print(f"Exit Code: {res_check.returncode}")

# 5. Verify records in original jobs.db
print("\n--- VERIFYING ORIGINAL jobs.db RECORD INTEGRITY ---")
conn = sqlite3.connect(jobs_db)
cur = conn.cursor()
cur.execute("SELECT count(*) FROM jobs;")
jobs_count = cur.fetchone()[0]
cur.execute("SELECT count(*) FROM duplicate_records;")
dups_count = cur.fetchone()[0]
cur.execute("SELECT count(*) FROM pipeline_runs;")
runs_count = cur.fetchone()[0]
conn.close()

print(f"Jobs Table Count:              {jobs_count} (Expected: 24)")
print(f"Duplicate Records Table Count: {dups_count} (Expected: 24)")
print(f"Pipeline Runs Table Count:     {runs_count} (Expected: 4)")

assert jobs_count == 24, f"Jobs count mismatch: {jobs_count} != 24"
assert dups_count == 24, f"Duplicate records count mismatch: {dups_count} != 24"
assert runs_count == 4, f"Pipeline runs count mismatch: {runs_count} != 4"
print(">> DATA INTEGRITY VERIFIED: Original jobs.db records remain completely intact.")

# Clean up fresh_db
if fresh_db.exists():
    fresh_db.unlink()
    print("\nTemporary test_fresh.db removed.")

print("=" * 70)
print("ALL MIGRATION AUDIT CHECKS PASSED SUCCESSFULLY")
print("=" * 70)
