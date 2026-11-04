"""
Functional Telegram Bot API client using standard library urllib.
Zero custom classes: pure functions, plain dict responses, safe error handling.
"""

import json
import mimetypes
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

TELEGRAM_API_BASE = os.environ.get("TELEGRAM_API_BASE", "http://127.0.0.1:8081").rstrip("/")


def make_api_request(
    bot_token: str,
    method: str,
    payload: Optional[Dict[str, Any]] = None,
    timeout: int = 40,
) -> Dict[str, Any]:
    url = f"{TELEGRAM_API_BASE}/bot{bot_token}/{method}"
    data = None
    headers = {"Content-Type": "application/json"}

    if payload is not None:
        data = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(url, data=data, headers=headers, method="POST" if data else "GET")

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            return json.loads(body)
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="ignore")
        try:
            return json.loads(error_body)
        except Exception:
            return {"ok": False, "error_code": e.code, "description": e.reason}
    except Exception as e:
        return {"ok": False, "error_code": 0, "description": str(e)}


def send_message(
    bot_token: str,
    chat_id: Union[int, str],
    text: str,
    reply_markup: Optional[Dict[str, Any]] = None,
    parse_mode: Optional[str] = "HTML",
    reply_to_message_id: Optional[int] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"chat_id": chat_id, "text": text}
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if reply_to_message_id:
        payload["reply_to_message_id"] = reply_to_message_id
    return make_api_request(bot_token, "sendMessage", payload)


def edit_message_text(
    bot_token: str,
    chat_id: Union[int, str],
    message_id: int,
    text: str,
    reply_markup: Optional[Dict[str, Any]] = None,
    parse_mode: Optional[str] = "HTML",
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
    }
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    if parse_mode:
        payload["parse_mode"] = parse_mode
    return make_api_request(bot_token, "editMessageText", payload)


def delete_message(
    bot_token: str,
    chat_id: Union[int, str],
    message_id: int,
) -> Dict[str, Any]:
    payload = {"chat_id": chat_id, "message_id": message_id}
    return make_api_request(bot_token, "deleteMessage", payload)


def send_chat_action(
    bot_token: str,
    chat_id: Union[int, str],
    action: str = "typing",
) -> Dict[str, Any]:
    payload = {"chat_id": chat_id, "action": action}
    return make_api_request(bot_token, "sendChatAction", payload)


def forward_message(
    bot_token: str,
    chat_id: Union[int, str],
    from_chat_id: Union[int, str],
    message_id: int,
) -> Dict[str, Any]:
    payload = {
        "chat_id": chat_id,
        "from_chat_id": from_chat_id,
        "message_id": message_id,
    }
    return make_api_request(bot_token, "forwardMessage", payload)


def copy_message(
    bot_token: str,
    chat_id: Union[int, str],
    from_chat_id: Union[int, str],
    message_id: int,
    caption: Optional[str] = None,
    parse_mode: Optional[str] = "HTML",
    reply_markup: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "chat_id": chat_id,
        "from_chat_id": from_chat_id,
        "message_id": message_id,
    }
    if caption is not None:
        payload["caption"] = caption
    if parse_mode is not None:
        payload["parse_mode"] = parse_mode
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    return make_api_request(bot_token, "copyMessage", payload)


def send_photo_remote(
    bot_token: str,
    chat_id: Union[int, str],
    photo: str,
    caption: Optional[str] = None,
    parse_mode: Optional[str] = "HTML",
    reply_markup: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"chat_id": chat_id, "photo": photo}
    if caption:
        payload["caption"] = caption
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    return make_api_request(bot_token, "sendPhoto", payload)


def send_video_remote(
    bot_token: str,
    chat_id: Union[int, str],
    video: str,
    caption: Optional[str] = None,
    parse_mode: Optional[str] = "HTML",
    reply_markup: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"chat_id": chat_id, "video": video}
    if caption:
        payload["caption"] = caption
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    return make_api_request(bot_token, "sendVideo", payload)


def answer_callback_query(
    bot_token: str,
    callback_query_id: str,
    text: Optional[str] = None,
    show_alert: bool = False,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "callback_query_id": callback_query_id,
        "show_alert": show_alert,
    }
    if text:
        payload["text"] = text
    return make_api_request(bot_token, "answerCallbackQuery", payload)


def get_chat_member(
    bot_token: str,
    chat_id: Union[int, str],
    user_id: int,
) -> Dict[str, Any]:
    payload = {"chat_id": chat_id, "user_id": user_id}
    return make_api_request(bot_token, "getChatMember", payload)


def get_me(bot_token: str) -> Dict[str, Any]:
    return make_api_request(bot_token, "getMe")


def set_webhook(
    bot_token: str,
    url: str,
    secret_token: Optional[str] = None,
    drop_pending_updates: bool = False,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "url": url,
        "drop_pending_updates": drop_pending_updates,
    }
    if secret_token:
        payload["secret_token"] = secret_token
    return make_api_request(bot_token, "setWebhook", payload)


def delete_webhook(bot_token: str, drop_pending_updates: bool = False) -> Dict[str, Any]:
    payload = {"drop_pending_updates": drop_pending_updates}
    return make_api_request(bot_token, "deleteWebhook", payload)


def get_updates(
    bot_token: str,
    offset: Optional[int] = None,
    limit: int = 100,
    timeout: int = 30,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"limit": limit, "timeout": timeout}
    if offset is not None:
        payload["offset"] = offset
    return make_api_request(bot_token, "getUpdates", payload, timeout=timeout + 10)


def _build_multipart_payload(
    fields: Dict[str, Any],
    files: Dict[str, Tuple[str, bytes, str]],
    boundary: str,
) -> bytes:
    lines: List[bytes] = []
    b_boundary = boundary.encode("utf-8")

    # Regular form fields
    for key, val in fields.items():
        if val is None:
            continue
        if isinstance(val, (dict, list)):
            val = json.dumps(val)
        val_str = str(val)
        lines.append(b"--" + b_boundary)
        lines.append(f'Content-Disposition: form-data; name="{key}"'.encode("utf-8"))
        lines.append(b"")
        lines.append(val_str.encode("utf-8"))

    # File fields
    for field_name, (filename, file_bytes, mime_type) in files.items():
        lines.append(b"--" + b_boundary)
        lines.append(
            f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"'.encode(
                "utf-8"
            )
        )
        lines.append(f"Content-Type: {mime_type}".encode("utf-8"))
        lines.append(b"")
        lines.append(file_bytes)

    lines.append(b"--" + b_boundary + b"--")
    lines.append(b"")
    return b"\r\n".join(lines)


def send_file(
    bot_token: str,
    method: str,
    chat_id: Union[int, str],
    file_field: str,
    file_path: str,
    caption: Optional[str] = None,
    extra_fields: Optional[Dict[str, Any]] = None,
    timeout: int = 120,
) -> Dict[str, Any]:
    path = Path(file_path)
    if not path.is_file():
        return {"ok": False, "error_code": 404, "description": f"File not found: {file_path}"}

    filename = path.name
    mime_type, _ = mimetypes.guess_type(filename)
    if not mime_type:
        mime_type = "application/octet-stream"

    file_bytes = path.read_bytes()

    fields: Dict[str, Any] = {"chat_id": chat_id}
    if caption:
        fields["caption"] = caption
        fields["parse_mode"] = "HTML"
    if extra_fields:
        fields.update(extra_fields)

    files = {file_field: (filename, file_bytes, mime_type)}

    boundary = f"----WebKitFormBoundary{os.urandom(16).hex()}"
    data = _build_multipart_payload(fields, files, boundary)

    url = f"{TELEGRAM_API_BASE}/bot{bot_token}/{method}"
    headers = {
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Content-Length": str(len(data)),
    }

    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            return json.loads(body)
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="ignore")
        try:
            return json.loads(error_body)
        except Exception:
            return {"ok": False, "error_code": e.code, "description": e.reason}
    except Exception as e:
        return {"ok": False, "error_code": 0, "description": str(e)}


def send_video(
    bot_token: str,
    chat_id: Union[int, str],
    video_path: str,
    caption: Optional[str] = None,
    supports_streaming: bool = True,
    duration: Optional[int] = None,
    width: Optional[int] = None,
    height: Optional[int] = None,
) -> Dict[str, Any]:
    extra = {"supports_streaming": supports_streaming}
    if duration:
        extra["duration"] = duration
    if width:
        extra["width"] = width
    if height:
        extra["height"] = height
    return send_file(bot_token, "sendVideo", chat_id, "video", video_path, caption, extra)


def send_audio(
    bot_token: str,
    chat_id: Union[int, str],
    audio_path: str,
    caption: Optional[str] = None,
    performer: Optional[str] = None,
    title: Optional[str] = None,
    duration: Optional[int] = None,
) -> Dict[str, Any]:
    extra: Dict[str, Any] = {}
    if performer:
        extra["performer"] = performer
    if title:
        extra["title"] = title
    if duration:
        extra["duration"] = duration
    return send_file(bot_token, "sendAudio", chat_id, "audio", audio_path, caption, extra)


def send_photo(
    bot_token: str,
    chat_id: Union[int, str],
    photo_path: str,
    caption: Optional[str] = None,
) -> Dict[str, Any]:
    return send_file(bot_token, "sendPhoto", chat_id, "photo", photo_path, caption)


def send_media_group(
    bot_token: str,
    chat_id: Union[int, str],
    media_paths: List[str],
    caption: Optional[str] = None,
    timeout: int = 120,
) -> Dict[str, Any]:
    if not media_paths:
        return {"ok": False, "error_code": 400, "description": "Empty media paths"}

    media_items: List[Dict[str, Any]] = []
    files: Dict[str, Tuple[str, bytes, str]] = {}

    for idx, path_str in enumerate(media_paths[:10]):
        p = Path(path_str)
        if not p.is_file():
            continue
        ext = p.suffix.lower()
        m_type = "video" if ext in (".mp4", ".mov", ".mkv", ".webm") else "photo"
        field_name = f"media_{idx}"
        mime_type, _ = mimetypes.guess_type(p.name)
        if not mime_type:
            mime_type = "video/mp4" if m_type == "video" else "image/jpeg"

        files[field_name] = (p.name, p.read_bytes(), mime_type)
        item: Dict[str, Any] = {
            "type": m_type,
            "media": f"attach://{field_name}",
        }
        if idx == 0 and caption:
            item["caption"] = caption
            item["parse_mode"] = "HTML"
        media_items.append(item)

    if not media_items:
        return {"ok": False, "error_code": 404, "description": "No valid files found for media group"}

    fields: Dict[str, Any] = {
        "chat_id": chat_id,
        "media": media_items,
    }

    boundary = f"----WebKitFormBoundary{os.urandom(16).hex()}"
    data = _build_multipart_payload(fields, files, boundary)

    url = f"{TELEGRAM_API_BASE}/bot{bot_token}/sendMediaGroup"
    headers = {
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Content-Length": str(len(data)),
    }

    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            return json.loads(body)
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="ignore")
        try:
            return json.loads(error_body)
        except Exception:
            return {"ok": False, "error_code": e.code, "description": e.reason}
    except Exception as e:
        return {"ok": False, "error_code": 0, "description": str(e)}


def send_document(
    bot_token: str,
    chat_id: Union[int, str],
    document_path: str,
    caption: Optional[str] = None,
) -> Dict[str, Any]:
    return send_file(bot_token, "sendDocument", chat_id, "document", document_path, caption)


def get_file(bot_token: str, file_id: str) -> Dict[str, Any]:
    return make_api_request(bot_token, "getFile", {"file_id": file_id})


def download_telegram_file(
    bot_token: str,
    file_id: str,
    destination_path: str,
    timeout: int = 60,
) -> bool:
    res = get_file(bot_token, file_id)
    if not res.get("ok"):
        return False
    file_path = res.get("result", {}).get("file_path")
    if not file_path:
        return False
    url = f"{TELEGRAM_API_BASE}/file/bot{bot_token}/{file_path}"
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            with open(destination_path, "wb") as f:
                f.write(response.read())
        return True
    except Exception:
        return False

