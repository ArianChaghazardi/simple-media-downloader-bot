"""
Functional database migrations module.
Runs versioned SQL migrations for SQLite and MySQL.
Zero classes: pure functions and plain dictionaries.
"""

import datetime
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

from src.media_bot.db.engine import (
    close_connection,
    create_connection,
    db_transaction,
    execute,
    fetch_all,
    get_backend_type,
)


def _adapt_migration_sql(sql_content: str, backend: str) -> str:
    if backend == "mysql":
        # Convert SQLite AUTOINCREMENT syntax to MySQL AUTO_INCREMENT
        adapted = re.sub(
            r"INTEGER PRIMARY KEY AUTOINCREMENT",
            "INT AUTO_INCREMENT PRIMARY KEY",
            sql_content,
            flags=re.IGNORECASE,
        )
        return adapted
    return sql_content


def ensure_migrations_table(conn: Any, database_url: str) -> None:
    backend = get_backend_type(database_url)
    if backend == "mysql":
        create_sql = """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INT PRIMARY KEY,
            applied_at VARCHAR(50) NOT NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """
    else:
        create_sql = """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        );
        """
    execute(conn, database_url, create_sql, commit=True)


def get_applied_versions(conn: Any, database_url: str) -> List[int]:
    rows = fetch_all(
        conn, database_url, "SELECT version FROM schema_migrations ORDER BY version ASC"
    )
    return [int(r["version"]) for r in rows]


def get_migration_files(migrations_dir_str: str) -> List[Tuple[int, Path]]:
    migrations_dir = Path(migrations_dir_str)
    if not migrations_dir.is_dir():
        return []

    migration_files: List[Tuple[int, Path]] = []
    for file_path in migrations_dir.glob("*.sql"):
        match = re.match(r"^(\d+)_", file_path.name)
        if match:
            version = int(match.group(1))
            migration_files.append((version, file_path))

    migration_files.sort(key=lambda item: item[0])
    return migration_files


def run_migrations(
    database_url: str,
    migrations_dir_str: str = "migrations",
) -> Dict[str, Any]:
    conn = create_connection(database_url)
    try:
        ensure_migrations_table(conn, database_url)
        applied_versions = set(get_applied_versions(conn, database_url))
        migration_files = get_migration_files(migrations_dir_str)
        backend = get_backend_type(database_url)

        newly_applied = []
        for version, file_path in migration_files:
            if version in applied_versions:
                continue

            raw_sql = file_path.read_text(encoding="utf-8")
            adapted_sql = _adapt_migration_sql(raw_sql, backend)

            # Split statements cleanly
            statements = [s.strip() for s in adapted_sql.split(";") if s.strip()]

            with db_transaction(conn):
                for stmt in statements:
                    cursor = conn.cursor()
                    try:
                        cursor.execute(stmt)
                    finally:
                        cursor.close()

                now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
                execute(
                    conn,
                    database_url,
                    "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                    (version, now_utc),
                )
            newly_applied.append(version)

        current_ver = max(applied_versions.union(newly_applied), default=0)
        return {
            "success": True,
            "applied": newly_applied,
            "current_version": current_ver,
            "database_backend": backend,
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "database_backend": get_backend_type(database_url),
        }
    finally:
        close_connection(conn)


def get_current_version(database_url: str) -> int:
    conn = create_connection(database_url)
    try:
        ensure_migrations_table(conn, database_url)
        versions = get_applied_versions(conn, database_url)
        return max(versions, default=0)
    except Exception:
        return 0
    finally:
        close_connection(conn)
