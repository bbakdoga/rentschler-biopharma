from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from db.models import Base
from config import DB_PATH

engine = create_engine(f"sqlite:///{DB_PATH}", echo=False,
                       connect_args={"check_same_thread": False,
                                     "timeout": 30})
Session = sessionmaker(bind=engine)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_conn, _conn_record):
    """Enable WAL so readers don't block the writer, and wait up to
    30 s for a lock before raising 'database is locked'."""
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA busy_timeout=30000")
    cur.close()


def init_db():
    Base.metadata.create_all(engine)
    _migrate()


# Columns added after the first release. create_all() never ALTERs existing
# tables, so we add any missing columns here (non-destructive).
_ADDED_COLUMNS = {
    "pages":  [("ocr_width", "INTEGER"), ("ocr_height", "INTEGER")],
    "fields": [("bbox_x", "INTEGER"), ("bbox_y", "INTEGER"),
               ("bbox_w", "INTEGER"), ("bbox_h", "INTEGER")],
}


def _migrate():
    with engine.begin() as conn:
        for table, cols in _ADDED_COLUMNS.items():
            existing = {row[1] for row in
                        conn.exec_driver_sql(f"PRAGMA table_info({table})")}
            for name, col_type in cols:
                if name not in existing:
                    conn.exec_driver_sql(
                        f"ALTER TABLE {table} ADD COLUMN {name} {col_type}")


def get_session():
    return Session()
