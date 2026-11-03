"""
Functional update intake and normalization module.
Zero custom classes: pure functions and plain dictionaries.
"""

import datetime
from typing import Any, Dict

from src.media_bot.db.engine import execute, fetch_one


def parse_update(raw_update: Dict[str, Any]) -> Dict[str, Any]:
    update_id = raw_update.get("update_id", 0)

    if "message" in raw_update:
        msg = raw_update["message"]
        chat = msg.get("chat", {})
        from_u = msg.get("from", {})
        text = msg.get("text", "") or msg.get("caption", "")

        media_info = None
        if "audio" in msg:
            media_info = {"type": "audio", "file_id": msg["audio"]["file_id"]}
        elif "voice" in msg:
            media_info = {"type": "voice", "file_id": msg["voice"]["file_id"]}
        elif "video" in msg:
            media_info = {"type": "video", "file_id": msg["video"]["file_id"]}

        return {
            "update_id": update_id,
            "type": "message",
            "chat_id": chat.get("id"),
            "chat_type": chat.get("type", "private"),
            "user_id": from_u.get("id"),
            "from_user": from_u,
            "message_id": msg.get("message_id"),
            "text": text.strip(),
            "media": media_info,
            "reply_to_message": msg.get("reply_to_message"),
            "raw": raw_update,
        }

    elif "callback_query" in raw_update:
        cb = raw_update["callback_query"]
        msg = cb.get("message", {})
        chat = msg.get("chat", {})
        from_u = cb.get("from", {})

        return {
            "update_id": update_id,
            "type": "callback_query",
            "callback_query_id": cb.get("id"),
            "chat_id": chat.get("id"),
            "chat_type": chat.get("type", "private"),
            "user_id": from_u.get("id"),
            "from_user": from_u,
            "message_id": msg.get("message_id"),
            "callback_data": cb.get("data", ""),
            "raw": raw_update,
        }

    return {
        "update_id": update_id,
        "type": "unknown",
        "raw": raw_update,
    }


def is_update_processed(conn: Any, database_url: str, update_id: int) -> bool:
    if not update_id:
        return False
    row = fetch_one(
        conn,
        database_url,
        "SELECT update_id FROM processed_updates WHERE update_id = ?",
        (update_id,),
    )
    return row is not None


def mark_update_processed(conn: Any, database_url: str, update_id: int) -> None:
    if not update_id:
        return
    now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
    execute(
        conn,
        database_url,
        "INSERT OR IGNORE INTO processed_updates (update_id, processed_at) VALUES (?, ?)",
        (update_id, now_utc),
        commit=True,
    )
