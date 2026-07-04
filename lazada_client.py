"""
Client goi API noi bo (mtop) ma trang "Tao affiliate shortlink" cua Lazada
dung khi bam nut "Tao shortlink":

    mtop.lazada.cheetah.aff.shortlink.create

Phat hien quan trong (da kiem chung bang du lieu that do nguoi dung cung cap):
API nay KHONG bat buoc phai dang nhap. Goi o tab an danh, khong cookie, chi
can masterLink hop le:
  - Lan goi dau tien (chua co cookie _m_h5_tk) se bi tu choi:
        {"ret": ["FAIL_SYS_TOKEN_EMPTY::..."]}
    nhung response do kem theo Set-Cookie cap 1 token an danh moi.
  - Goi lai lan 2 voi token vua nhan thi THANH CONG:
        {"data": {"affShortUrl": "https://s.lazada.vn/l.ZC6m1"}, "ret": ["SUCCESS::..."]}

=> Bot tu "bootstrap" token an danh theo dung pattern nay (dung
requests.Session de tu giu cookie giua 2 lan goi), khong can ban phai dang
nhap / copy cookie thu cong. Neu sau nay Lazada that chat va cach an danh
nay ngung hoat dong, co the truyen cookie that qua set_manual_cookie() /
lenh /setsession lam phuong an du phong.
"""
import hashlib
import json
import re
import time

import requests

APP_KEY_DEFAULT = "24677475"
API_PATH = "mtop.lazada.cheetah.aff.shortlink.create"
API_URL = f"https://acs-m.lazada.vn/h5/{API_PATH}/1.0/"

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)

SHORTLINK_IN_RESPONSE_RE = re.compile(r"https://s\.lazada\.vn/[A-Za-z0-9._\-/]+")
MAX_RETRIES = 2  # so lan thu lai toi da khi gap loi token/session


class LazadaApiError(Exception):
    def __init__(self, message, raw_response=None):
        super().__init__(message)
        self.raw_response = raw_response


def _build_data_string(master_link, source_url, sub_id1, sub_id2, sub_id3):
    inner = {
        "masterLink": master_link,
        "sourceUrl": source_url,
        "sub_id1": sub_id1 or "",
        "sub_id2": sub_id2 or "",
        "sub_id3": sub_id3 or "",
    }
    inner_json = json.dumps(inner, separators=(",", ":"), ensure_ascii=False)
    return json.dumps({"payload": inner_json}, separators=(",", ":"), ensure_ascii=False)


def _sign(token, t, app_key, data):
    raw = f"{token}&{t}&{app_key}&{data}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _extract_shortlink(response_json):
    data = response_json.get("data") if isinstance(response_json, dict) else None
    if isinstance(data, dict) and data.get("affShortUrl"):
        return data["affShortUrl"]
    # fallback: tim theo pattern URL trong toan bo response (phong khi Lazada doi ten field)
    text = json.dumps(response_json, ensure_ascii=False)
    m = SHORTLINK_IN_RESPONSE_RE.search(text)
    return m.group(0) if m else None


class LazadaClient:
    def __init__(self, app_key=APP_KEY_DEFAULT, user_agent=DEFAULT_USER_AGENT, extra_headers=None):
        self.app_key = app_key
        self.user_agent = user_agent
        self.extra_headers = extra_headers or {}
        self.session = requests.Session()
        self.session.headers.update(self._base_headers())

    def _base_headers(self):
        h = {
            "accept": "application/json",
            "accept-language": "vi,en-US;q=0.9,en;q=0.8",
            "cache-control": "no-cache",
            "content-type": "application/x-www-form-urlencoded",
            "origin": "https://pages.lazada.vn",
            "referer": "https://pages.lazada.vn/",
            "user-agent": self.user_agent,
            "x-i18n-language": "vi",
            "x-i18n-regionid": "VN",
        }
        h.update(self.extra_headers)
        return h

    def set_manual_cookie(self, cookie_string):
        """Ghi de bang cookie that (da dang nhap) - dung lam phuong an du
        phong neu che do an danh ngung hoat dong. cookie_string dang
        "k1=v1; k2=v2; ..." (copy nguyen phan sau -b trong curl)."""
        self.session.cookies.clear()
        for part in cookie_string.split(";"):
            part = part.strip()
            if "=" in part:
                k, v = part.split("=", 1)
                self.session.cookies.set(k.strip(), v.strip())

    def _current_token(self):
        tk = self.session.cookies.get("_m_h5_tk")
        return tk.split("_")[0] if tk else ""

    def _call(self, master_link, source_url, sub_id1, sub_id2, sub_id3):
        data_str = _build_data_string(master_link, source_url, sub_id1, sub_id2, sub_id3)
        t = str(int(time.time() * 1000))
        sign = _sign(self._current_token(), t, self.app_key, data_str)
        params = {
            "jsv": "2.4.11",
            "appKey": self.app_key,
            "t": t,
            "sign": sign,
            "api": API_PATH,
            "v": "1.0",
            "type": "originaljson",
            "isSec": "1",
            "AntiCreep": "true",
            "timeout": "20000",
            "dataType": "json",
            "sessionOption": "AutoLoginOnly",
            "x-i18n-language": "vi",
            "x-i18n-regionID": "VN",
        }
        try:
            resp = self.session.post(API_URL, params=params, data={"data": data_str}, timeout=20)
        except requests.RequestException as e:
            raise LazadaApiError(f"Loi ket noi toi Lazada: {e}") from e
        try:
            return resp.json()
        except ValueError as e:
            raise LazadaApiError(
                f"Lazada tra ve du lieu khong phai JSON (HTTP {resp.status_code}).",
                raw_response=resp.text[:500],
            ) from e

    def create_shortlink(self, master_link, source_url, sub_id1="", sub_id2="", sub_id3=""):
        """Tao affiliate shortlink. Tu dong bootstrap/refresh token an danh
        khi can (retry toi da MAX_RETRIES lan). Raise LazadaApiError neu
        van that bai sau khi da thu lai."""
        last_payload = None
        last_ret = ""
        for attempt in range(MAX_RETRIES + 1):
            payload = self._call(master_link, source_url, sub_id1, sub_id2, sub_id3)
            ret = (payload.get("ret") or [""])[0]
            if ret.upper().startswith("SUCCESS"):
                link = _extract_shortlink(payload)
                if link:
                    return link
                raise LazadaApiError(
                    "Lazada bao thanh cong nhung khong thay link rut gon trong response.",
                    raw_response=json.dumps(payload, ensure_ascii=False)[:800],
                )
            last_payload, last_ret = payload, ret
            is_token_issue = "TOKEN" in ret.upper() or "SESSION" in ret.upper()
            if not is_token_issue:
                break  # loi khac (vd sourceUrl khong hop le) - thu lai vo ich
            # neu la loi token/session: session.cookies le ra da duoc server
            # set 1 _m_h5_tk moi qua Set-Cookie -> vong lap se tu dung token do

        hint = ""
        if "TOKEN" in last_ret.upper() or "SESSION" in last_ret.upper():
            hint = " (da thu refresh token an danh nhung van that bai - co the Lazada da that chat, hay thu /setsession voi cookie that.)"
        raise LazadaApiError(
            f"Lazada tu choi request: {last_ret}{hint}",
            raw_response=json.dumps(last_payload, ensure_ascii=False)[:800] if last_payload else None,
        )
