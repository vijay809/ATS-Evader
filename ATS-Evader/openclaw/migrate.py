from openclaw.core.config import RuntimeSettings
import sqlite3

db = str(RuntimeSettings().database_path)
print(f"Migrating {db}")
try:
    conn = sqlite3.connect(db)
    conn.execute('ALTER TABLE jobdescriptionrecord ADD COLUMN status VARCHAR NOT NULL DEFAULT "Discovered"')
    conn.execute('ALTER TABLE jobdescriptionrecord ADD COLUMN url VARCHAR')
    conn.commit()
    print("Success")
except Exception as e:
    print(f"Skipped or error: {e}")
