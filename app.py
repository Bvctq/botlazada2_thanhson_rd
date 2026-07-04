"""
Bot Telegram tao affiliate shortlink Lazada.

Luong xu ly 1 tin nhan:
  1. Kiem tra nguoi gui co trong danh sach duoc phep dung bot khong.
  2. Neu la lenh (/start, /help, /status, /setsession, /link) -> xu ly rieng.
  3. Neu la tin nhan thuong -> tim tat ca URL Lazada trong tin nhan, chuan
     hoa tung link (url_normalizer), roi goi API tao shortlink (lazada_client)
     cho tung link, tra ket qua ve cho nguoi dung.

Bien moi truong can thiet - xem .env.example va README.md.
"""
import logging
import os
import threading
import time

from flask import Flask, jsonify, request

from curl_parser import parse_curl_command
from lazada_client import LazadaApiError, LazadaClient
from telegram_api import TelegramClient
from url_normalizer import UrlNormalizeError, extract_urls, normalize_lazada_url

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("lazada-bot")

# ---------------------------------------------------------------------------
# Cau hinh tu bien moi truong
# ---------------------------------------------------------------------------
BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
WEBHOOK_SECRET = os.environ["TELEGRAM_WEBHOOK_SECRET"]
MASTER_LINK = os.environ["LAZADA_MASTER_LINK"]

_allowed_raw = os.environ.get("ALLOWED_USER_IDS", "").strip()
if not _allowed_raw:
    raise RuntimeError(
        "Chua cau hinh ALLOWED_USER_IDS. Dat bien moi truong nay bang Telegram "
        "user id (dang so) cua ban, cach nhau boi dau phay, de tranh bot bi "
        "nguoi la dung. Lay user id bang cach nhan tin cho @userinfobot tren Telegram."
    )
ALLOWED_USER_IDS = {int(x) for x in _allowed_raw.split(",") if x.strip()}

LAZADA_APP_KEY = os.environ.get("LAZADA_APP_KEY", "24677475")
LAZADA_COOKIE_ENV = os.environ.get("LAZADA_COOKIE", "").strip()
EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL", "").rstrip("/")
PORT = int(os.environ.get("PORT", "10000"))
CALL_DELAY_SECONDS = float(os.environ.get("CALL_DELAY_SECONDS", "0.6"))

tg = TelegramClient(BOT_TOKEN)
lazada = LazadaClient(app_key=LAZADA_APP_KEY)

# State nho, dung de /status bao dung che do dang dung (khong doan qua cookie)
_state = {"manual_session": False}

if LAZADA_COOKIE_ENV:
    lazada.set_manual_cookie(LAZADA_COOKIE_ENV)
    _state["manual_session"] = True
    log.info("Da nap LAZADA_COOKIE tu bien moi truong khi khoi dong.")
else:
    log.info("Chua co LAZADA_COOKIE - bot se tu bootstrap token an danh khi can.")

app = Flask(__name__)

HELP_TEXT = f"""Bot tao affiliate shortlink Lazada.

Cach dung:
- Gui 1 hoac nhieu link san pham/trang Lazada (moi link 1 dong hoac cach nhau boi khoang trang), bot se tu nhan dien, tao shortlink cho tung link, roi tra loi lai dung noi dung tin nhan ban gui nhung da thay link cu bang shortlink moi (giu nguyen chu, emoji, xuong dong...) de ban copy dang di ngay.
- Ho tro: link s.lazada.vn, link .../products/pdp-..., link pages.lazada.vn (se tu bo tham so tracking rac).

Lenh:
/link <url> [sub_id1] [sub_id2] [sub_id3] - tao 1 shortlink kem sub id de theo doi
/status - xem trang thai session hien tai
/setsession <cookie hoac nguyen curl> - cap nhat cookie/session Lazada thu cong (chi can khi che do tu dong an danh ngung hoat dong)
/setsession auto - quay lai che do tu dong (khong dung cookie thu cong)

Master link dang dung: {MASTER_LINK}
"""


def is_authorized(user_id) -> bool:
    return user_id in ALLOWED_USER_IDS


def _format_result_line(original_url: str, source_url: str, shortlink: str = None, error: str = None) -> str:
    if shortlink:
        return f"OK: {shortlink}\n   (nguon: {source_url})"
    return f"LOI: {original_url}\n   -> {error}"


def _handle_single_link(original_url: str, sub_id1="", sub_id2="", sub_id3="") -> str:
    try:
        source_url = normalize_lazada_url(original_url)
    except UrlNormalizeError as e:
        return _format_result_line(original_url, None, error=str(e))
    try:
        shortlink = lazada.create_shortlink(MASTER_LINK, source_url, sub_id1, sub_id2, sub_id3)
        return _format_result_line(original_url, source_url, shortlink=shortlink)
    except LazadaApiError as e:
        return _format_result_line(original_url, source_url, error=str(e))


def _resolve_link_for_replacement(original_url: str):
    """
    Xu ly 1 link tim thay trong tin nhan thuong (khac /link) - dung cho che
    do "thay the ngay trong tin nhan goc" thay vi tra ve danh sach ket qua
    rieng.

    Tra ve (text_thay_the, loi):
    - Thanh cong: text_thay_the la shortlink moi, loi la None.
    - That bai: text_thay_the la CHINH original_url (giu nguyen trong tin
      nhan chinh de khong lam sai lech noi dung goc), loi la 1 dong mo ta -
      se duoc gom lai va bao rieng cho nguoi dung o 1 tin nhan phu, khong
      chen vao giua tin nhan chinh de ban con copy nguyen tin nhan chinh di
      dang duoc.
    """
    try:
        source_url = normalize_lazada_url(original_url)
    except UrlNormalizeError as e:
        return original_url, f"{original_url}\n   -> {e}"
    try:
        shortlink = lazada.create_shortlink(MASTER_LINK, source_url)
        return shortlink, None
    except LazadaApiError as e:
        return original_url, f"{original_url}\n   -> {e}"


def _cmd_setsession(chat_id: int, payload: str) -> None:
    payload = payload.strip()
    if payload.lower() == "auto":
        lazada.session.cookies.clear()
        _state["manual_session"] = False
        tg.send_message(chat_id, "Da chuyen ve che do tu dong (an danh).")
        return
    if not payload:
        tg.send_message(
            chat_id,
            "Dan cookie (vd: k1=v1; k2=v2; ...) hoac dan nguyen lenh curl "
            "(copy tu DevTools > Network > Copy as cURL) ngay sau /setsession.",
        )
        return
    try:
        if payload.lstrip().lower().startswith("curl"):
            parsed = parse_curl_command(payload)
            cookie = parsed["cookies"]
            headers = parsed["headers"]
        else:
            cookie = payload
            headers = {}
        if not cookie:
            raise ValueError("khong doc duoc cookie tu noi dung ban gui")
        lazada.set_manual_cookie(cookie)
        if headers:
            lazada.extra_headers.update(headers)
            lazada.session.headers.update(lazada._base_headers())
        _state["manual_session"] = True
        tg.send_message(
            chat_id,
            "Da cap nhat session thu cong. Luu y: chi ton tai trong lan chay hien "
            "tai cua bot - neu Render restart bot se quay ve che do tu dong, hay "
            "cap nhat bien moi truong LAZADA_COOKIE tren Render neu muon giu lau dai.",
        )
    except Exception as e:  # noqa: BLE001 - muon bao loi ro rang cho nguoi dung
        tg.send_message(chat_id, f"Khong doc duoc session ban gui: {e}")


def _cmd_status(chat_id: int) -> None:
    has_token = bool(lazada.session.cookies.get("_m_h5_tk"))
    mode = "cookie thu cong" if _state["manual_session"] else "tu dong (an danh)"
    lines = [
        f"Master link: {MASTER_LINK}",
        f"Che do session: {mode}",
        f"Da co token trong bo nho: {'co' if has_token else 'chua - se tu bootstrap o lan tao link tiep theo'}",
    ]
    tg.send_message(chat_id, "\n".join(lines))


def process_message(chat_id: int, user_id: int, text: str) -> None:
    text = (text or "").strip()
    if not is_authorized(user_id):
        tg.send_message(chat_id, "Ban khong co quyen su dung bot nay.")
        log.warning("Tu choi user khong duoc phep: %s", user_id)
        return

    if text in ("/start", "/help"):
        tg.send_message(chat_id, HELP_TEXT)
        return

    if text == "/status":
        _cmd_status(chat_id)
        return

    if text.startswith("/setsession"):
        _cmd_setsession(chat_id, text[len("/setsession") :])
        return

    if text.startswith("/link"):
        parts = text[len("/link") :].strip().split()
        if not parts:
            tg.send_message(chat_id, "Dung: /link <url> [sub_id1] [sub_id2] [sub_id3]")
            return
        url = parts[0]
        sub_ids = (parts[1:] + ["", "", ""])[:3]
        tg.send_message(chat_id, _handle_single_link(url, *sub_ids))
        return

    urls = extract_urls(text)
    if not urls:
        tg.send_message(
            chat_id,
            "Khong tim thay link Lazada nao trong tin nhan. Gui link san pham "
            "hoac /help de xem huong dan.",
        )
        return

    reply_text = text
    errors = []
    for i, url in enumerate(urls):
        if i > 0:
            time.sleep(CALL_DELAY_SECONDS)
        replacement, error = _resolve_link_for_replacement(url)
        reply_text = reply_text.replace(url, replacement, 1)
        if error:
            errors.append(error)

    tg.send_message(chat_id, reply_text)
    if errors:
        tg.send_message(
            chat_id,
            "Luu y - cac link sau CHUA tao duoc shortlink (da giu nguyen "
            "link cu trong tin nhan ben tren):\n\n" + "\n\n".join(errors),
        )


@app.route(f"/webhook/{WEBHOOK_SECRET}", methods=["POST"])
def webhook():
    header_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if header_secret != WEBHOOK_SECRET:
        return jsonify({"ok": False}), 403

    update = request.get_json(silent=True) or {}
    message = update.get("message") or update.get("edited_message")
    if message:
        chat_id = message["chat"]["id"]
        user_id = (message.get("from") or {}).get("id")
        text = message.get("text", "")
        try:
            process_message(chat_id, user_id, text)
        except Exception:
            log.exception("Loi khong xu ly duoc khi xu ly message")
            try:
                tg.send_message(chat_id, "Co loi noi bo xay ra, vui long thu lai sau.")
            except Exception:
                log.exception("Khong the gui thong bao loi ve Telegram")
    return jsonify({"ok": True})


@app.route("/", methods=["GET"])
def health():
    return "Lazada affiliate bot dang chay.", 200


def _ensure_webhook() -> None:
    if not EXTERNAL_URL:
        log.warning(
            "Khong tim thay RENDER_EXTERNAL_URL - bo qua tu dong dang ky webhook. "
            "Hay tu goi setWebhook thu cong (xem README.md)."
        )
        return
    url = f"{EXTERNAL_URL}/webhook/{WEBHOOK_SECRET}"
    try:
        result = tg.set_webhook(url, WEBHOOK_SECRET)
        log.info("setWebhook: %s", result)
    except Exception:
        log.exception("Khong the tu dong dang ky webhook")


# Dang ky webhook ca khi chay truc tiep (python app.py) lan khi chay qua gunicorn
threading.Thread(target=_ensure_webhook, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
