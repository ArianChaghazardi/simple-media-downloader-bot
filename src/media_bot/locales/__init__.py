"""
Functional localization module.
Loads translations from JSON without defining custom classes.
"""

import json
from pathlib import Path
from typing import Any, Dict

_CACHE: Dict[str, Dict[str, str]] = {}


def load_locale(locale_name: str = "fa") -> Dict[str, str]:
    if locale_name in _CACHE:
        return _CACHE[locale_name]

    locales_dir = Path(__file__).resolve().parent
    file_path = locales_dir / f"{locale_name}.json"
    if not file_path.is_file():
        file_path = locales_dir / "fa.json"

    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
        _CACHE[locale_name] = data
        return data
    except Exception:
        return {}


def t(key: str, locale: str = "fa", **kwargs: Any) -> str:
    strings = load_locale(locale)
    template = strings.get(key)
    if template is None and locale != "en":
        # Fallback to english if missing in target locale
        fallback = load_locale("en")
        template = fallback.get(key, key)
    elif template is None:
        template = key

    if kwargs:
        try:
            return template.format(**kwargs)
        except Exception:
            return template
    return template
