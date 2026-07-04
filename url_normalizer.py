"""
Chuẩn hoá các dạng link Lazada người dùng gửi vào bot, đưa về dạng
sourceUrl "sạch" mà API tạo affiliate shortlink của Lazada chấp nhận.

Các dạng được xử lý:
1. s.lazada.vn/xxxx           -> theo redirect lấy link đích, rút về dạng /products/i..-s..html
2. /products/pdp-i..-s..html  -> bỏ tiền tố "pdp-"
3. pages.lazada.vn (share)    -> loại các tham số tracking: exlaz, laz_share_info
4. pages.lazada.vn (router)   -> loại các tham số tracking: trafficFrom, laz_trackid, mkttid, exlaz
"""
import re
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

import requests

PRODUCT_RE = re.compile(r"/products/(?:pdp-)?i(\d+)-s(\d+)\.html", re.IGNORECASE)

# Các tham số tracking cần loại bỏ khỏi link pages.lazada.vn trước khi gửi cho API.
# Có thể bổ sung thêm nếu Lazada thêm tham số mới sau này.
TRACKING_PARAMS_TO_STRIP = {
    "exlaz",
    "laz_share_info",
    "trafficfrom",
    "laz_trackid",
    "mkttid",
}

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)


class UrlNormalizeError(Exception):
    pass


def _clean_product_path(path: str) -> str | None:
    m = PRODUCT_RE.search(path)
    if not m:
        return None
    item_id, sku_id = m.groups()
    return f"/products/i{item_id}-s{sku_id}.html"


def _strip_tracking_params(parsed) -> str:
    qs = parse_qsl(parsed.query, keep_blank_values=True)
    filtered = [(k, v) for k, v in qs if k.lower() not in TRACKING_PARAMS_TO_STRIP]
    new_query = urlencode(filtered)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", new_query, ""))


def resolve_short_link(short_url: str, timeout: int = 10) -> str:
    """Theo redirect của link s.lazada.vn để lấy URL đích cuối cùng."""
    headers = {"User-Agent": DEFAULT_UA}
    resp = requests.get(short_url, headers=headers, allow_redirects=True, timeout=timeout)
    return resp.url


def normalize_lazada_url(url: str, _already_resolved: bool = False) -> str:
    """
    Trả về sourceUrl đã chuẩn hoá, sẵn sàng gửi cho API tạo affiliate shortlink.
    Raise UrlNormalizeError nếu không nhận diện được / không xử lý được link.
    """
    url = url.strip()
    parsed = urlparse(url)
    if not parsed.scheme:
        url = "https://" + url
        parsed = urlparse(url)

    host = parsed.netloc.lower()

    # 1) short link s.lazada.vn -> giải mã qua redirect rồi chuẩn hoá tiếp
    if host == "s.lazada.vn" and not _already_resolved:
        try:
            final_url = resolve_short_link(url)
        except requests.RequestException as e:
            raise UrlNormalizeError(f"Không giải mã được short link: {e}") from e
        return normalize_lazada_url(final_url, _already_resolved=True)

    # 2) link sản phẩm (pdp- hoặc đã sạch) -> rút về /products/i..-s..html
    product_path = _clean_product_path(parsed.path)
    if product_path:
        return urlunparse((parsed.scheme or "https", parsed.netloc, product_path, "", "", ""))

    # 3 & 4) pages.lazada.vn -> loại bỏ tham số tracking, giữ nguyên phần còn lại
    if host == "pages.lazada.vn":
        return _strip_tracking_params(parsed)

    raise UrlNormalizeError("Không nhận diện được định dạng link Lazada này.")


# Regex bắt mọi URL http/https xuất hiện trong 1 tin nhắn (để xử lý nhiều link 1 lúc)
URL_IN_TEXT_RE = re.compile(r"https?://[^\s]+")


def extract_urls(text: str) -> list[str]:
    return URL_IN_TEXT_RE.findall(text or "")
