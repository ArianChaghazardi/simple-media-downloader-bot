"""
Functional database engine module.
Supports SQLite (built-in) and MySQL/MariaDB (via PyMySQL).
Zero custom classes: functional transactions, pure dict query outputs, parameterized SQL.
"""

import contextlib
import sqlite3
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple
from urllib.parse import parse_qs, unquote, urlparse


def parse_database_url(url: str) -> Dict[str, Any]:
    if not url:
        return {"backend": "sqlite", "path": ":memory:"}

    if url.startswith("sqlite:///"):
        path = url[len("sqlite:///") :]
        return {"backend": "sqlite", "path": path}
    elif url.startswith("sqlite://"):
        path = url[len("sqlite://") :]
        return {"backend": "sqlite", "path": path}

    if url.startswith("mysql://") or url.startswith("mariadb://"):
        parsed = urlparse(url)
        database = parsed.path.lstrip("/")
        query_params = parse_qs(parsed.query)
        charset = query_params.get("charset", ["utf8mb4"])[0]

        return {
            "backend": "mysql",
            "host": parsed.hostname or "localhost",
            "port": parsed.port or 3306,
            "user": unquote(parsed.username or "root"),
            "password": unquote(parsed.password or ""),
            "database": database,
            "charset": charset,
        }

    # Default fallback
    return {"backend": "sqlite", "path": url}


def get_backend_type(database_url: str) -> str:
    parsed = parse_database_url(database_url)
    return str(parsed.get("backend", "sqlite"))


def adapt_query(query: str, backend: str) -> str:
    """
    Translates standard '?' parameterized query to '%s' when targeting MySQL.
    """
    if backend == "mysql":
        return query.replace("?", "%s")
    return query


def create_connection(database_url: str) -> Any:
    parsed = parse_database_url(database_url)
    backend = parsed["backend"]

    if backend == "sqlite":
        db_path = parsed["path"]
        if db_path != ":memory:":
            path_obj = Path(db_path)
            path_obj.parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(db_path, timeout=30.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        # Enable foreign keys and WAL mode for better concurrency in SQLite
        conn.execute("PRAGMA foreign_keys = ON;")
        if db_path != ":memory:":
            try:
                conn.execute("PRAGMA journal_mode = WAL;")
            except Exception:
                pass
        return conn

    elif backend == "mysql":
        try:
            import pymysql
            import pymysql.cursors
        except ImportError:
            raise RuntimeError(
                "pymysql is required for MySQL databases. Install it via pip install pymysql."
            ) from None

        conn = pymysql.connect(
            host=parsed["host"],
            port=parsed["port"],
            user=parsed["user"],
            password=parsed["password"],
            database=parsed["database"],
            charset=parsed["charset"],
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=False,
            connect_timeout=10,
        )
        return conn

    raise ValueError(f"Unsupported database backend: {backend}")


def close_connection(conn: Any) -> None:
    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass


@contextlib.contextmanager
def db_transaction(conn: Any) -> Generator[Any, None, None]:
    try:
        yield conn
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise


def execute(
    conn: Any,
    database_url: str,
    query: str,
    params: Tuple[Any, ...] = (),
    commit: bool = False,
) -> int:
    backend = get_backend_type(database_url)
    adapted = adapt_query(query, backend)
    cursor = conn.cursor()
    try:
        cursor.execute(adapted, params)
        if commit:
            conn.commit()
        last_id = getattr(cursor, "lastrowid", 0) or 0
        return int(last_id)
    finally:
        cursor.close()


def fetch_all(
    conn: Any,
    database_url: str,
    query: str,
    params: Tuple[Any, ...] = (),
) -> List[Dict[str, Any]]:
    backend = get_backend_type(database_url)
    adapted = adapt_query(query, backend)
    cursor = conn.cursor()
    try:
        cursor.execute(adapted, params)
        rows = cursor.fetchall()
        result = []
        for row in rows:
            if isinstance(row, dict):
                result.append(row)
            else:
                result.append(dict(row))
        return result
    finally:
        cursor.close()


def fetch_one(
    conn: Any,
    database_url: str,
    query: str,
    params: Tuple[Any, ...] = (),
) -> Optional[Dict[str, Any]]:
    backend = get_backend_type(database_url)
    adapted = adapt_query(query, backend)
    cursor = conn.cursor()
    try:
        cursor.execute(adapted, params)
        row = cursor.fetchone()
        if row is None:
            return None
        if isinstance(row, dict):
            return row
        return dict(row)
    finally:
        cursor.close()
