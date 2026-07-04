"""
Wrapper mong cho Telegram Bot API (khong dung thu vien python-telegram-bot
de giam phu thuoc - chi can requests, goi thang HTTP API cua Telegram).
https://core.telegram.org/bots/api
"""
import requests

TELEGRAM_API_BASE = "https://api.telegram.org"
MAX_MESSAGE_LEN = 4000  # Telegram gioi han 4096 ky tu, chua bien an toan


class TelegramClient:
    def __init__(self, bot_token: str):
        self.bot_token = bot_token
        self.base_url = f"{TELEGRAM_API_BASE}/bot{bot_token}"

    def _post(self, method: str, payload: dict, timeout: int = 15) -> dict:
        resp = requests.post(f"{self.base_url}/{method}", json=payload, timeout=timeout)
        resp.raise_for_status()
        return resp.json()

    def send_message(self, chat_id, text: str, parse_mode: str = None, disable_preview: bool = True):
        """Tu dong chia nho neu text vuot qua gioi han do dai cua Telegram."""
        chunks = [text[i : i + MAX_MESSAGE_LEN] for i in range(0, len(text), MAX_MESSAGE_LEN)] or [""]
        results = []
        for chunk in chunks:
            payload = {
                "chat_id": chat_id,
                "text": chunk,
                "disable_web_page_preview": disable_preview,
            }
            if parse_mode:
                payload["parse_mode"] = parse_mode
            results.append(self._post("sendMessage", payload))
        return results

    def set_webhook(self, url: str, secret_token: str) -> dict:
        return self._post("setWebhook", {"url": url, "secret_token": secret_token, "allowed_updates": ["message"]})

    def delete_webhook(self) -> dict:
        return self._post("deleteWebhook", {})

    def get_webhook_info(self) -> dict:
        resp = requests.get(f"{self.base_url}/getWebhookInfo", timeout=15)
        resp.raise_for_status()
        return resp.json()

    def get_me(self) -> dict:
        resp = requests.get(f"{self.base_url}/getMe", timeout=15)
        resp.raise_for_status()
        return resp.json()
