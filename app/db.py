from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from .core import DATABASE_URL

class Base(DeclarativeBase):
    pass

engine = create_engine(DATABASE_URL, connect_args={'check_same_thread': False, 'timeout': 20} if DATABASE_URL.startswith('sqlite') else {}, pool_pre_ping=True)
if DATABASE_URL.startswith('sqlite'):
    @event.listens_for(engine, 'connect')
    def sqlite_settings(connection, record):
        connection.execute('PRAGMA foreign_keys=ON')
        connection.execute('PRAGMA journal_mode=WAL')
        connection.execute('PRAGMA busy_timeout=20000')

SessionLocal = sessionmaker(engine, expire_on_commit=False)

def get_db():
    with SessionLocal() as db:
        try:
            yield db
        except Exception:
            db.rollback()
            raise

def init_db():
    from . import models
    Base.metadata.create_all(engine)
    with SessionLocal.begin() as db:
        for name in ['superadmin', 'admin', 'employee', 'readonly']:
            if not db.get(models.Role, name):
                db.add(models.Role(name=name))
