# Lazada Affiliate Shortlink Bot (Telegram)

Bot Telegram tự động tạo affiliate shortlink Lazada (giống hệt nút "Tạo shortlink"
trên trang affiliate của Lazada), nhận nhiều dạng link đầu vào (link rút gọn, link
sản phẩm có "pdp-", link pages.lazada.vn có tracking rác) và tự chuẩn hoá trước khi gọi API.

## Lưu ý quan trọng trước khi dùng

- **Đây là API nội bộ, không tài liệu hoá chính thức** (`mtop.lazada.cheetah.aff.shortlink.create`),
  được suy ra từ request thật khi bạn dùng trang web của Lazada. Lazada có thể
  đổi cấu trúc API này bất kỳ lúc nào mà không báo trước, khi đó bot sẽ cần
  cập nhật lại.
- Đã kiểm chứng: API này **không bắt buộc đăng nhập** - chỉ cần `masterLink` hợp
  lệ (của tài khoản affiliate bạn) là tạo được shortlink, kể cả gọi ẩn danh. Bot
  tận dụng điều này để **tự động lấy token phiên ẩn danh**, không cần bạn copy
  cookie thủ công. Nếu sau này Lazada thắt chặt và cách này ngừng hoạt động, bot
  vẫn hỗ trợ nạp cookie thật qua lệnh `/setsession` (xem bên dưới).
- Hãy dùng bot cho đúng mục đích tạo link affiliate của chính bạn, giới hạn số
  người được dùng bot (biến `ALLOWED_USER_IDS`), và tránh tạo link ồ ạt trong
  thời gian ngắn - vừa để tôn trọng hệ thống của Lazada, vừa giảm rủi ro tài
  khoản/luồng bị Lazada chú ý và chặn.
- Không commit file `.env` hay cookie thật lên GitHub công khai.

## Cấu trúc project

```
app.py              - Flask app: nhận webhook Telegram, điều phối xử lý
lazada_client.py     - Gọi API Lazada (tự tính chữ ký sign, tự bootstrap token)
url_normalizer.py    - Chuẩn hoá 4 dạng link Lazada về sourceUrl sạch
curl_parser.py       - Đọc lệnh curl dán vào (cho /setsession) để lấy cookie/header
telegram_api.py      - Gọi thẳng Telegram Bot API (sendMessage, setWebhook...)
requirements.txt
render.yaml          - Cấu hình deploy Render (Blueprint)
.env.example
```

## Bước 1 - Tạo bot Telegram

1. Nhắn tin cho [@BotFather](https://t.me/BotFather) trên Telegram, gõ `/newbot` và làm theo hướng dẫn.
2. Lưu lại **token** BotFather đưa ra (dạng `123456789:AA...`).
3. Nhắn tin cho [@userinfobot](https://t.me/userinfobot) để lấy **user id** (dạng số) của chính bạn - dùng để điền vào `ALLOWED_USER_IDS`.

## Bước 2 - Lấy Master link

Mở trang tạo affiliate shortlink của Lazada (trang trong ảnh bạn gửi), copy giá trị
ở ô **"Master link"** (dạng `https://c.lazada.vn/t/c.YParqP`) - đây là link gắn
với ID affiliate của bạn, dùng cho mọi shortlink tạo ra sau này.

## Bước 3 - Deploy lên Render

### Cách nhanh (dùng Blueprint)

1. Đẩy toàn bộ code này lên 1 repo GitHub của bạn.
2. Trên Render Dashboard: **New > Blueprint**, chọn repo vừa tạo (Render sẽ đọc `render.yaml`).
3. Điền các biến môi trường được yêu cầu (`TELEGRAM_BOT_TOKEN`, `LAZADA_MASTER_LINK`, `ALLOWED_USER_IDS`) - `TELEGRAM_WEBHOOK_SECRET` sẽ được Render tự sinh ngẫu nhiên.
4. Bấm Deploy.

### Cách thủ công

1. **New > Web Service**, chọn repo, runtime **Python 3**.
2. Build command: `pip install -r requirements.txt`
3. Start command: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --timeout 30`
4. Vào tab **Environment**, thêm các biến trong `.env.example` (bắt buộc: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`, `LAZADA_MASTER_LINK`, `ALLOWED_USER_IDS`).
5. Deploy.

> **Lưu ý về gói miễn phí của Render:** web service ở gói free sẽ "ngủ" sau khoảng
> 15 phút không có request, tin nhắn Telegram đầu tiên sau khi bot "ngủ" có thể
> mất 30-60 giây để phản hồi (do phải khởi động lại). Nếu cần bot phản hồi tức
> thì liên tục, hãy nâng cấp lên gói trả phí thấp nhất để tắt tính năng này.
> Nên tự kiểm tra giá/gói hiện tại trên trang Render vì có thể đã thay đổi.

Bot tự động gọi `setWebhook` khi khởi động (dùng biến `RENDER_EXTERNAL_URL` mà
Render tự cấp) - không cần bạn tự thiết lập webhook thủ công. Có thể kiểm tra
bằng cách gọi: `https://api.telegram.org/bot<TOKEN>/getWebhookInfo`

## Cách dùng bot

Nhắn tin trực tiếp cho bot trên Telegram:

- **Gửi link bất kỳ** (1 hoặc nhiều link, mỗi link cách nhau bởi khoảng trắng/xuống dòng) - bot tự nhận diện, chuẩn hoá và tạo shortlink cho từng link:
  ```
  https://www.lazada.vn/products/pdp-i255675772-s14883705485.html
  https://s.lazada.vn/s.nh1n0?c=w
  ```
- **`/link <url> [sub_id1] [sub_id2] [sub_id3]`** - tạo 1 shortlink kèm sub id để theo dõi hiệu quả:
  ```
  /link https://www.lazada.vn/products/i255675772-s14883705485.html chiendichluongve facebook minigame
  ```
- **`/status`** - xem đang dùng chế độ session nào (tự động ẩn danh hay cookie thủ công).
- **`/setsession <cookie hoặc nguyên lệnh curl>`** - nạp cookie thật nếu chế độ tự động ngừng hoạt động (xem bên dưới). Gửi `/setsession auto` để quay lại chế độ tự động.
- **`/help`** - xem hướng dẫn nhanh trong bot.

Các dạng link được xử lý:

| Link vào | Xử lý |
|---|---|
| `s.lazada.vn/...` | Theo redirect lấy link đích, rút về dạng `/products/i..-s..html` |
| `.../products/pdp-i..-s..html` | Bỏ tiền tố `pdp-` |
| `pages.lazada.vn/...share...` | Bỏ tham số `exlaz`, `laz_share_info` |
| `pages.lazada.vn/...router...` | Bỏ tham số `trafficFrom`, `laz_trackid`, `mkttid`, `exlaz` |

## Khi nào cần dùng `/setsession` (cookie thật)

Mặc định bot tự "mượn" token phiên ẩn danh của Lazada, không cần bạn làm gì thêm.
Chỉ cần dùng `/setsession` nếu bot báo lỗi liên quan token/session liên tục
(Lazada có thể đã thắt chặt yêu cầu đăng nhập). Khi đó:

1. Mở trang tạo affiliate shortlink, đăng nhập tài khoản Lazada của bạn.
2. Mở DevTools (F12) > tab Network, bấm nút **"Tạo shortlink"** 1 lần.
3. Click chuột phải vào request `shortlink.create` vừa xuất hiện > **Copy > Copy as cURL**.
4. Dán nguyên văn vào Telegram sau lệnh `/setsession ` (bot hiểu cả curl dạng bash lẫn dạng Windows cmd).
5. Cookie này **sẽ hết hạn theo thời gian** (giống như đăng nhập web bình thường) - lặp lại các bước trên khi bot báo lỗi token/session. Đây là giới hạn tự nhiên của việc dùng session cookie, không có cách nào tránh được ngoài việc lặp lại thao tác này định kỳ.
6. Để cookie tồn tại lâu dài qua các lần Render khởi động lại, cập nhật thêm biến môi trường `LAZADA_COOKIE` trên Render Dashboard (không chỉ dùng `/setsession`, vì giá trị đó chỉ nằm trong bộ nhớ, mất khi service restart).

## Chạy thử ở máy local (không deploy)

```bash
pip install -r requirements.txt
export TELEGRAM_BOT_TOKEN="..."
export TELEGRAM_WEBHOOK_SECRET="mot-chuoi-bi-mat"
export LAZADA_MASTER_LINK="https://c.lazada.vn/t/c.YParqP"
export ALLOWED_USER_IDS="123456789"
python3 app.py
```

Ở local sẽ không có `RENDER_EXTERNAL_URL` nên bot sẽ không tự đăng ký webhook -
muốn test webhook thật cần deploy lên Render (hoặc dùng ngrok/cloudflared để
lấy URL public tạm thời rồi tự gọi `setWebhook`).

## Xử lý sự cố thường gặp

- **Bot không phản hồi gì:** kiểm tra `ALLOWED_USER_IDS` có đúng user id Telegram của bạn không, và xem log trên Render để chắc webhook đã đăng ký thành công.
- **"Lazada từ chối request: FAIL_SYS_TOKEN..." lặp lại kể cả sau khi tự retry:** thử `/setsession` với cookie thật.
- **"Không nhận diện được định dạng link Lazada này":** link gửi vào không khớp 4 dạng đã hỗ trợ - gửi thử link dạng `lazada.vn/products/...` trực tiếp.
- **Tạo thành công nhưng không thấy link rút gọn trong response:** Lazada có thể đã đổi tên field trong response - báo lại để cập nhật hàm `_extract_shortlink()` trong `lazada_client.py`.
