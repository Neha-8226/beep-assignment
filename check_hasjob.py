from app.database import SessionLocal
from app.models import Job, DuplicateRecord

db = SessionLocal()
hasjobs = db.query(Job).filter(Job.source == 'hasjob').all()
print(f"Total Hasjob canonical jobs: {len(hasjobs)}")
for j in hasjobs:
    desc_len = len(j.description) if j.description else 0
    print(f"Job {j.id}: title='{j.title}' | company='{j.company}' | loc='{j.raw_location}' | desc_len={desc_len}")

dups = db.query(DuplicateRecord).all()
print(f"\nTotal Duplicate Records in DB: {len(dups)}")
for d in dups[:10]:
    print(f"Dup {d.id} for Canonical {d.canonical_job_id}: [{d.source}] '{d.title}' - reason: {d.duplicate_reason}")

db.close()
