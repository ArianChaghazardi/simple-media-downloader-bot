"""
Functional command-line interface for Simple Media Downloader Bot.
Zero custom classes: pure functions and argparse.
"""

import argparse
import os
import shutil
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

from src.media_bot.bot_api.client import delete_webhook, get_me, get_updates
from src.media_bot.bot_api.dispatch import dispatch_update
from src.media_bot.config import load_config, validate_config
from src.media_bot.db.engine import (
    close_connection,
    create_connection,
    fetch_one,
    get_backend_type,
)
from src.media_bot.db.migrations import get_current_version, run_migrations
from src.media_bot.logging_setup import get_logger, setup_logging
from src.media_bot.workers.worker import run_worker_loop

logger = get_logger("cli")


def is_ffmpeg_available(custom_path: Optional[str] = None) -> bool:
    if custom_path and os.path.isfile(custom_path) and os.access(custom_path, os.X_OK):
        return True
    return bool(shutil.which("ffmpeg"))


def cmd_doctor(cfg: Dict[str, Any]) -> int:
    print("=" * 60)
    print("  SYSTEM HEALTH & DIAGNOSTICS (DOCTOR)")
    print("=" * 60)

    # 1. Python version
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    print(f"[*] Python Version: {py_ver} ... OK")

    # 2. Writable directories
    for path_key in ("DATA_DIR", "TEMP_DIR"):
        p_val = cfg.get(path_key, "data")
        p = Path(p_val)
        try:
            p.mkdir(parents=True, exist_ok=True)
            test_file = p / ".write_test"
            test_file.write_text("ok")
            test_file.unlink()
            print(f"[*] Directory [{path_key}]: '{p_val}' ... Writable [OK]")
        except Exception as e:
            print(f"[!] Directory [{path_key}]: '{p_val}' ... FAILED ({e})")

    # 3. Database connection & migrations
    db_url = cfg.get("DATABASE_URL", "sqlite:///data/bot.db")
    backend = get_backend_type(db_url)
    print(f"[*] Database Backend: {backend}")
    try:
        conn = create_connection(db_url)
        row = fetch_one(conn, db_url, "SELECT 1 as test")
        if row and row.get("test") == 1:
            print("    Database Connection: SUCCESS")
        ver = get_current_version(db_url)
        print(f"    Current Schema Version: {ver}")
        close_connection(conn)
    except Exception as e:
        print(f"    Database Connection: FAILED ({e})")

    # 4. Telegram API check
    token = cfg.get("BOT_TOKEN", "")
    if token:
        safe_token_preview = token[:6] + "..." + token[-4:]
        res = get_me(token)
        if res.get("ok"):
            bot_user = res["result"].get("username", "")
            print(f"[*] Telegram Bot API: SUCCESS (@{bot_user}, Token: {safe_token_preview})")
        else:
            print(f"[!] Telegram Bot API: FAILED ({res.get('description', '')})")
    else:
        print("[!] Telegram Bot Token: Not configured")

    # 5. FFmpeg availability
    ffmpeg_custom = cfg.get("FFMPEG_PATH")
    if is_ffmpeg_available(ffmpeg_custom):
        print("[*] FFmpeg Executable: DETECTED (Video compression & audio conversion enabled)")
    else:
        print("[~] FFmpeg Executable: NOT FOUND (Large video compression disabled)")

    print("=" * 60)
    return 0


def cmd_migrate(cfg: Dict[str, Any]) -> int:
    db_url = cfg.get("DATABASE_URL", "sqlite:///data/bot.db")
    migrations_dir = str(Path(__file__).parent.parent.parent / "migrations")
    if not Path(migrations_dir).is_dir():
        migrations_dir = "migrations"
    print(f"[*] Running database migrations on {db_url} using '{migrations_dir}'...")
    run_migrations(db_url, migrations_dir)
    print("[*] Migrations complete.")
    return 0


def run_poller_loop(cfg: Dict[str, Any]) -> None:
    bot_token = cfg["BOT_TOKEN"]
    database_url = cfg["DATABASE_URL"]

    # Delete webhook to allow getUpdates
    delete_webhook(bot_token, drop_pending_updates=False)

    print("Starting Telegram Poller loop...")
    logger.info("Starting Telegram Poller daemon...")
    offset = None

    while True:
        try:
            updates_res = get_updates(bot_token, offset=offset, timeout=30)
            if not updates_res.get("ok"):
                logger.warning("getUpdates error: %s", updates_res.get("description"))
                time.sleep(3)
                continue

            results = updates_res.get("result", [])
            for raw_u in results:
                u_id = raw_u.get("update_id")
                offset = u_id + 1

                conn = create_connection(database_url)
                try:
                    dispatch_update(cfg, conn, raw_u)
                except Exception as e:
                    logger.exception("Error dispatching update %s: %s", u_id, str(e))
                finally:
                    close_connection(conn)

        except Exception as e:
            logger.error("Poller loop exception: %s", str(e))
            time.sleep(3)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Simple Media Downloader Telegram Bot CLI - by sourcio.ir"
    )
    parser.add_argument(
        "command",
        choices=["poller", "worker", "all", "migrate", "doctor"],
        nargs="?",
        default="poller",
        help="Command to run (default: poller)",
    )
    parser.add_argument(
        "--env",
        dest="env_file",
        default=".env",
        help="Path to .env configuration file (default: .env)",
    )

    args = parser.parse_args()

    cfg = load_config(args.env_file)
    setup_logging(cfg.get("LOG_LEVEL", "INFO"))

    # Ensure required data directories exist
    data_dir = cfg.get("DATA_DIR", "data")
    temp_dir = cfg.get("TEMP_DIR", "data/tmp")
    Path(data_dir).mkdir(parents=True, exist_ok=True)
    Path(temp_dir).mkdir(parents=True, exist_ok=True)

    if args.command == "doctor":
        sys.exit(cmd_doctor(cfg))

    if args.command == "migrate":
        sys.exit(cmd_migrate(cfg))

    # Auto run migrations before service start
    db_url = cfg.get("DATABASE_URL", "sqlite:///data/bot.db")
    migrations_dir = str(Path(__file__).parent.parent.parent / "migrations")
    if not Path(migrations_dir).is_dir():
        migrations_dir = "migrations"
    run_migrations(db_url, migrations_dir)

    is_valid, errs = validate_config(cfg)
    if not is_valid:
        print("[!] Configuration Validation FAILED:")
        for e in errs:
            print(f"    - {e}")
        sys.exit(1)

    if args.command == "poller":
        run_poller_loop(cfg)

    elif args.command == "worker":
        print("Starting continuous worker daemon...")
        run_worker_loop(cfg, interval_seconds=2)

    elif args.command == "all":
        print("Starting Simple Media Downloader in combined mode (Poller + Worker)...")
        w_thread = threading.Thread(
            target=run_worker_loop,
            args=(cfg, 2),
            daemon=True,
            name="WorkerThread",
        )
        w_thread.start()
        run_poller_loop(cfg)


if __name__ == "__main__":
    main()
