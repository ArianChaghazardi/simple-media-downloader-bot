"""
Functional Telegram keyboard builder.
Zero custom classes: pure functions returning plain dictionaries.
"""

from typing import Any, Dict, List, Optional

from src.media_bot.locales import t


def build_inline_keyboard(rows: List[List[Dict[str, Any]]]) -> Dict[str, Any]:
    return {"inline_keyboard": rows}


def build_button(
    text: str,
    callback_data: Optional[str] = None,
    url: Optional[str] = None,
) -> Dict[str, Any]:
    btn: Dict[str, Any] = {"text": text}
    if callback_data is not None:
        btn["callback_data"] = callback_data
    elif url is not None:
        btn["url"] = url
    return btn


def main_menu_keyboard(
    bot_username: str = "",
    locale: str = "fa",
    is_admin: bool = False,
) -> Dict[str, Any]:
    group_url = (
        f"https://t.me/{bot_username}?startgroup=botstart"
        if bot_username
        else "https://telegram.me"
    )

    rows = [
        [
            build_button(t("btn_account", locale), callback_data="nav:account"),
            build_button(t("btn_help", locale), callback_data="nav:help"),
        ],
        [
            build_button(t("btn_add_group", locale), url=group_url),
        ],
    ]

    if is_admin:
        rows.append([build_button(t("btn_admin_panel", locale), callback_data="admin:home")])

    return build_inline_keyboard(rows)


def account_menu_keyboard(locale: str = "fa") -> Dict[str, Any]:
    return build_inline_keyboard(
        [
            [
                build_button(t("btn_back", locale), callback_data="nav:home"),
            ]
        ]
    )


def admin_main_keyboard(locale: str = "fa") -> Dict[str, Any]:
    return build_inline_keyboard(
        [
            [
                build_button(t("btn_admin_stats", locale), callback_data="admin:stats"),
            ],
            [
                build_button(t("btn_admin_limits", locale), callback_data="admin:limits"),
            ],
            [
                build_button(t("btn_back_to_bot", locale), callback_data="nav:home"),
            ],
        ]
    )


def admin_limits_keyboard(
    user_limit_enabled: bool,
    group_limit_enabled: bool,
    locale: str = "fa",
) -> Dict[str, Any]:
    u_status = "✅ فعال" if user_limit_enabled else "❌ غیرفعال"
    g_status = "✅ فعال" if group_limit_enabled else "❌ غیرفعال"

    return build_inline_keyboard(
        [
            [
                build_button(f"محدودیت کاربر: {u_status}", callback_data="admin:toggle_user_limit"),
                build_button("✏️ تنظیم سقف کاربر", callback_data="admin:set_user_limit"),
            ],
            [
                build_button(f"محدودیت گروه: {g_status}", callback_data="admin:toggle_group_limit"),
                build_button("✏️ تنظیم سقف گروه", callback_data="admin:set_group_limit"),
            ],
            [
                build_button(t("btn_back", locale), callback_data="admin:home"),
            ],
        ]
    )


def back_cancel_keyboard(target_cb: str = "admin:home", locale: str = "fa") -> Dict[str, Any]:
    return build_inline_keyboard(
        [
            [
                build_button(t("btn_back", locale), callback_data=target_cb),
            ]
        ]
    )


def large_file_options_keyboard(
    job_id: int,
    locale: str = "fa",
    allow_compress: bool = True,
) -> Dict[str, Any]:
    rows: List[List[Dict[str, Any]]] = []
    if allow_compress:
        rows.append(
            [
                build_button(
                    t("btn_large_file_compress", locale),
                    callback_data=f"large_file:compress:{job_id}",
                )
            ]
        )
    rows.append(
        [
            build_button(
                t("btn_large_file_audio", locale),
                callback_data=f"large_file:audio:{job_id}",
            )
        ]
    )
    rows.append(
        [
            build_button(
                t("btn_large_file_cancel", locale),
                callback_data=f"large_file:cancel:{job_id}",
            )
        ]
    )
    return build_inline_keyboard(rows)


def quota_exhausted_keyboard(locale: str = "fa") -> Dict[str, Any]:
    return build_inline_keyboard(
        [
            [
                build_button(t("btn_back", locale), callback_data="nav:home"),
            ]
        ]
    )
