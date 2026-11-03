"""
Functional configuration module for Simple Media Downloader Bot.
Pure functions, plain dictionaries, no custom classes.
"""

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def get_default_config() -> Dict[str, Any]:
    return {
        "BOT_TOKEN": "",
        "BOT_USERNAME": "",
        "ADMIN_IDS": [],
        "BOT_MODE": "polling",
        "DATABASE_URL": "sqlite:///data/bot.db",
        "DATA_DIR": "data",
        "TEMP_DIR": "data/tmp",
        "LOG_LEVEL": "INFO",
        "DEFAULT_LOCALE": "fa",
        "USER_LIMIT_ENABLED": True,
        "DAILY_USER_DOWNLOAD_LIMIT": 10,
        "GROUP_LIMIT_ENABLED": True,
        "DAILY_GROUP_DOWNLOAD_LIMIT": 50,
        "MAX_DOWNLOAD_BYTES": 104857600,  # 100 MB
        "USER_COOLDOWN_SECONDS": 10,
        "GROUP_COOLDOWN_SECONDS": 20,
        "JOB_TIMEOUT_SECONDS": 300,
        "MAX_QUEUE_SIZE": 50,
        "FILE_RETENTION_HOURS": 2,
        "FFMPEG_PATH": "",
        "YOUTUBE_COOKIES_PATH": "data/cookies.txt",
        "PROXY_URL": "",
        "TELEGRAM_API_BASE": "",
    }


def parse_admin_ids(raw_val: Any) -> List[int]:
    if isinstance(raw_val, list):
        parsed = []
        for item in raw_val:
            try:
                parsed.append(int(item))
            except (ValueError, TypeError):
                continue
        return parsed
    if isinstance(raw_val, str):
        cleaned = raw_val.strip()
        if not cleaned:
            return []
        parts = [p.strip() for p in cleaned.split(",") if p.strip()]
        result = []
        for p in parts:
            try:
                result.append(int(p))
            except ValueError:
                continue
        return result
    if isinstance(raw_val, int):
        return [raw_val]
    return []


def parse_env_file(path_str: str) -> Dict[str, str]:
    path = Path(path_str)
    if not path.is_file():
        return {}
    res = {}
    content = path.read_text(encoding="utf-8")
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip()
            if (val.startswith('"') and val.endswith('"')) or (
                val.startswith("'") and val.endswith("'")
            ):
                val = val[1:-1]
            res[key] = val
    return res


def validate_config(cfg: Dict[str, Any]) -> Tuple[bool, List[str]]:
    errors: List[str] = []

    token = str(cfg.get("BOT_TOKEN", "")).strip()
    if not token:
        errors.append("BOT_TOKEN is required.")
    elif not re.match(r"^\d{6,12}:[A-Za-z0-9_-]{30,50}$", token):
        errors.append("BOT_TOKEN format is invalid.")

    admins = cfg.get("ADMIN_IDS", [])
    if not isinstance(admins, list):
        errors.append("ADMIN_IDS must be a list of integers.")

    mode = cfg.get("BOT_MODE", "polling")
    if mode not in ("polling", "webhook"):
        errors.append("BOT_MODE must be 'polling' or 'webhook'.")

    return (len(errors) == 0, errors)


def load_config(
    env_file_path: Optional[str] = None,
    overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    cfg = get_default_config()

    file_to_read = env_file_path or os.environ.get("ENV_FILE", ".env")
    env_dict = parse_env_file(file_to_read)

    for k, v in env_dict.items():
        if k in cfg:
            cfg[k] = v

    for k in cfg.keys():
        if k in os.environ:
            cfg[k] = os.environ[k]

    if "ADMIN_IDS" in cfg:
        cfg["ADMIN_IDS"] = parse_admin_ids(cfg["ADMIN_IDS"])

    for int_key in (
        "DAILY_USER_DOWNLOAD_LIMIT",
        "DAILY_GROUP_DOWNLOAD_LIMIT",
        "MAX_DOWNLOAD_BYTES",
        "USER_COOLDOWN_SECONDS",
        "GROUP_COOLDOWN_SECONDS",
        "JOB_TIMEOUT_SECONDS",
        "MAX_QUEUE_SIZE",
        "FILE_RETENTION_HOURS",
    ):
        if int_key in cfg:
            try:
                cfg[int_key] = int(cfg[int_key])
            except (ValueError, TypeError):
                pass

    for bool_key in ("USER_LIMIT_ENABLED", "GROUP_LIMIT_ENABLED"):
        if bool_key in cfg:
            val = cfg[bool_key]
            if isinstance(val, str):
                cfg[bool_key] = val.lower() in ("true", "1", "yes", "on")
            else:
                cfg[bool_key] = bool(val)

    if overrides:
        cfg.update(overrides)

    return cfg


def save_config_file(cfg: Dict[str, Any], path_str: str = ".env") -> None:
    lines = [
        "# Simple Media Downloader Bot Configuration",
        "# Created for sourcio.ir",
        "",
        f"BOT_TOKEN={cfg.get('BOT_TOKEN', '')}",
        f"BOT_USERNAME={cfg.get('BOT_USERNAME', '')}",
        f"ADMIN_IDS={','.join(str(a) for a in cfg.get('ADMIN_IDS', []))}",
        f"DATABASE_URL={cfg.get('DATABASE_URL', 'sqlite:///data/bot.db')}",
        f"DEFAULT_LOCALE={cfg.get('DEFAULT_LOCALE', 'fa')}",
        "",
        "# Limits & Quotas",
        f"USER_LIMIT_ENABLED={'true' if cfg.get('USER_LIMIT_ENABLED', True) else 'false'}",
        f"DAILY_USER_DOWNLOAD_LIMIT={cfg.get('DAILY_USER_DOWNLOAD_LIMIT', 10)}",
        f"GROUP_LIMIT_ENABLED={'true' if cfg.get('GROUP_LIMIT_ENABLED', True) else 'false'}",
        f"DAILY_GROUP_DOWNLOAD_LIMIT={cfg.get('DAILY_GROUP_DOWNLOAD_LIMIT', 50)}",
        "",
        "# Advanced & Network",
        f"FFMPEG_PATH={cfg.get('FFMPEG_PATH', '')}",
        f"YOUTUBE_COOKIES_PATH={cfg.get('YOUTUBE_COOKIES_PATH', 'data/cookies.txt')}",
        f"PROXY_URL={cfg.get('PROXY_URL', '')}",
        f"TELEGRAM_API_BASE={cfg.get('TELEGRAM_API_BASE', '')}",
    ]
    Path(path_str).write_text("\n".join(lines) + "\n", encoding="utf-8")
