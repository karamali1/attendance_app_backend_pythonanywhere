from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker


DATABASE_URL = "postgresql+psycopg2://super:karam2ali0karam0ali2@KaramAli111-5306.postgres.pythonanywhere-services.com:15306/attendance"


engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=5,
    pool_timeout=30,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()