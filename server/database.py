from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from conf.system import SYS_CONFIG


Base = declarative_base()

database_path = Path(SYS_CONFIG.base_dir) / "database" / "database.db"
database_path.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(f"sqlite:///{database_path}")
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
