import sqlite3

def inspect_db(db_path='jobs.db'):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [r[0] for r in cursor.fetchall() if not r[0].startswith('sqlite_')]
    print(f"=== INSPECTING {db_path} ===")
    print(f"Tables found: {tables}")

    for t in tables:
        cursor.execute(f"PRAGMA table_info({t});")
        cols = [r[1] for r in cursor.fetchall()]
        cursor.execute(f"SELECT count(*) FROM {t};")
        count = cursor.fetchone()[0]
        print(f"Table: {t} | Rows: {count} | Total Columns: {len(cols)}")
        print(f"  Columns: {cols}")

    conn.close()

if __name__ == '__main__':
    inspect_db()
