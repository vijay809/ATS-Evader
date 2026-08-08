from openclaw.core.config import RuntimeSettings
from openclaw.core.storage import SQLModel
from sqlmodel import create_engine
import os

db = RuntimeSettings().database_path
if db.exists():
    os.remove(db)

engine = create_engine(f"sqlite:///{db}")
SQLModel.metadata.create_all(engine)
print("Database reset complete.")
