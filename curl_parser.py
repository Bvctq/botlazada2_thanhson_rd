"""
Parse 1 lệnh curl (dán từ Chrome DevTools > Copy as cURL, cả 2 kiểu bash và
Windows cmd đều được) để lấy ra cookie string và các header quan trọng.

Dùng cho lệnh /setsession trong bot: mỗi khi cookie/token hết hạn, người dùng
chỉ cần mở lại trang tạo shortlink, bấm "Tạo shortlink" 1 lần, copy request đó
thành curl rồi dán nguyên văn vào bot.
"""
import re

# Các header đáng quan tâm để "giả lập" trình duyệt khi gọi API
INTERESTING_HEADERS = [
    "user-agent",
    "x-ua",
    "x-umidtoken",
    "sec-ch-ua",
    "sec-ch-ua-mobile",
    "sec-ch-ua-platform",
]


def _looks_like_cmd_style(text: str) -> bool:
    return "^\"" in text or "^%^" in text


# Chuỗi ký tự đóng vai trò "quoted string, có thể chứa dấu \" bên trong" -
# giống cú pháp chuỗi kiểu C: nội dung là các ký tự khác " hoặc \, hoặc 1 cặp
# \X bất kỳ (escaped char), cho tới khi gặp dấu " trần (không có \ đứng trước).
QUOTED_VALUE_RE = r'"((?:[^"\\]|\\.)*)"'


def _unescape_cmd(text: str) -> str:
    # Nối các dòng bị ngắt bởi ký tự tiếp diễn "^" cuối dòng của cmd.exe
    text = re.sub(r"\s\^\r?\n\s*", " ", text)
    # Chrome "Copy as cURL (cmd)" đặt "^" trước MỌI ký tự cần escape, kể cả
    # khi ký tự đó là 1 phần của chuỗi "\^"" (dấu " nằm lồng bên trong giá
    # trị, ví dụ header sec-ch-ua). Quy tắc chung: "^X" -> "X" cho mọi X.
    text = re.sub(r"\^(.)", r"\1", text)
    return text


def _normalize_curl_text(text: str) -> str:
    text = text.strip()
    if _looks_like_cmd_style(text):
        text = _unescape_cmd(text)
    else:
        # bash-style: nối dòng bị ngắt bởi "\" cuối dòng, giữ nguyên phần còn lại
        text = re.sub(r"\\\r?\n\s*", " ", text)
    return text


def _unescape_quoted_value(raw: str) -> str:
    """Sau khi khớp QUOTED_VALUE_RE, bỏ escape \" -> " còn lại trong nội dung."""
    return raw.replace('\\"', '"').replace("\\\\", "\\")


def parse_curl_command(curl_text: str) -> dict:
    """
    Trả về {"cookies": str, "headers": {...}}.
    Không raise lỗi nếu thiếu phần nào - trả về rỗng cho phần đó.
    """
    text = _normalize_curl_text(curl_text)

    result = {"cookies": "", "headers": {}}

    # -b "....." hoặc -b '.....' (cookie jar)
    m = re.search(r"-b\s+" + QUOTED_VALUE_RE, text)
    if m:
        result["cookies"] = _unescape_quoted_value(m.group(1)).strip()
    else:
        m = re.search(r"-b\s+'([^']*)'", text)
        if m:
            result["cookies"] = m.group(1).strip()

    # tất cả -H "key: value" (dùng regex nhận biết dấu " escape bên trong value)
    for hm in re.finditer(r"-H\s+" + QUOTED_VALUE_RE, text):
        header_line = _unescape_quoted_value(hm.group(1))
        if ":" not in header_line:
            continue
        key, val = header_line.split(":", 1)
        key = key.strip().lower()
        if key in INTERESTING_HEADERS:
            result["headers"][key] = val.strip()

    # fallback cho kiểu bash (dấu nháy đơn)
    if not result["headers"]:
        for hm in re.finditer(r"-H\s+'([^:']+):\s*([^']*)'", text):
            key, val = hm.group(1).strip().lower(), hm.group(2).strip()
            if key in INTERESTING_HEADERS:
                result["headers"][key] = val

    return result
