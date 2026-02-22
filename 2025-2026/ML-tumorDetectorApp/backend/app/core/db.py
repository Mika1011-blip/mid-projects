import os 
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import logging
from app.core.config import settings

logger = logging.getLogger(__name__)


DATABASE_URL = settings.DATABASE_URL
if not DATABASE_URL :
    raise RuntimeError("DATABASE_URL is not set")
engine = create_engine(DATABASE_URL,pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False,bind=engine)

def get_db():
    db=SessionLocal()
    try:
        yield db
    finally:
        db.close()

def ping_db() -> bool:
    try :
        with engine.connect() as conn :
            conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.exception("DB ping failed: %s", e)
        return False