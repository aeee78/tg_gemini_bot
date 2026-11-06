from pathlib import Path

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import sessionmaker, declarative_base

SQLALCHEMY_DATABASE_URL = "sqlite:///./bot.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False, "timeout": 30},
)


def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
    finally:
        cursor.close()


event.listen(engine, "connect", set_sqlite_pragma)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def init_db(whitelist_path="whitelist.txt"):
    from database.models import User

    Base.metadata.create_all(bind=engine)
    migrate_user_profile()
    imported = migrate_whitelist(whitelist_path, User.__table__)
    if imported is not None:
        print(
            f"Whitelist migration completed: {imported} users granted pro_access=True.",
            flush=True,
        )


def migrate_whitelist(whitelist_path, users_table):
    """Add the access column and import the legacy file exactly once."""
    migration_name = "whitelist_to_pro_access_v1"
    with engine.begin() as connection:
        # Explicit transaction includes SQLite DDL, grants, and the marker.
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        columns = {column["name"] for column in inspect(connection).get_columns("users")}
        if "pro_access" not in columns:
            connection.exec_driver_sql(
                "ALTER TABLE users ADD COLUMN pro_access BOOLEAN NOT NULL DEFAULT 0"
            )
        connection.exec_driver_sql(
            "CREATE TABLE IF NOT EXISTS schema_migrations (name TEXT PRIMARY KEY)"
        )
        completed = connection.execute(
            text("SELECT 1 FROM schema_migrations WHERE name = :name"),
            {"name": migration_name},
        ).scalar()
        if completed:
            return None
        try:
            lines = Path(whitelist_path).read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            # Retry on the next startup if the file is restored later.
            return None

        user_ids = set()
        for line_number, line in enumerate(lines, 1):
            if line.strip():
                try:
                    user_ids.add(int(line.strip()))
                except ValueError as error:
                    raise ValueError(
                        f"Invalid Telegram ID in whitelist at line {line_number}"
                    ) from error

        for user_id in sorted(user_ids):
            statement = insert(users_table).values(id=user_id, pro_access=True)
            connection.execute(statement.on_conflict_do_update(
                index_elements=["id"], set_={"pro_access": True}
            ))
        connection.execute(
            text("INSERT INTO schema_migrations (name) VALUES (:name)"),
            {"name": migration_name},
        )
    return len(user_ids)


def migrate_user_profile():
    """Add nullable profile fields without inventing historical data."""
    fields = {
        "first_name": "VARCHAR",
        "last_name": "VARCHAR",
        "username": "VARCHAR",
        "language_code": "VARCHAR",
        "registered_at": "DATETIME",
        "last_active_at": "DATETIME",
    }
    with engine.begin() as connection:
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        columns = {column["name"] for column in inspect(connection).get_columns("users")}
        for name, sql_type in fields.items():
            if name not in columns:
                connection.exec_driver_sql(f"ALTER TABLE users ADD COLUMN {name} {sql_type}")
