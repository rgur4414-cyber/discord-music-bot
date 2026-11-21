# Discord Music Bot — phát nhạc YouTube qua link

Bot Python, slash command, chạy bằng `discord.py + yt-dlp + FFmpeg`.
Lệnh: `/play <link hoặc tên bài>` `/skip` `/queue` `/pause` `/resume` `/stop` `/leave` `/nowplaying` `/volume`

## 1. Tạo bot lấy token (5 phút, bắt buộc)

1. Vào https://discord.com/developers/applications → New Application → đặt tên
2. Bot → Reset Token → copy token, **không gửi token này cho ai, không commit lên GitHub**
3. Bot → Privileged Gateway Intents: bật **Server Members Intent** và **Message Content Intent** (dù bot dùng slash command, bật cho chắc)
4. OAuth2 → URL Generator → Scopes: tick `bot` + `applications.commands` → Bot Permissions: tick `Connect`, `Speak`, `Send Messages`, `Embed Links` → copy link ở dưới, mở link đó để mời bot vào server của bạn
5. Vào voice channel rồi gõ `/play https://www.youtube.com/watch?v=...`

## 2. Chạy thử trên máy

```bash
cd discord-music-bot
pip install -r requirements.txt
cp .env.example .env   # điền DISCORD_TOKEN vào .env
python bot.py
```

Cần có `ffmpeg` trong PATH. Windows: `winget install ffmpeg`, macOS: `brew install ffmpeg`.

## 3. Host free — sự thật 2026

Không có host free nào vừa 24/7 vừa ổn định vừa không cần thẻ. Bảng dưới là mình kiểm tra tháng 11/2026:

| Host | Free thật? | Chạy 24/7? | Vấn đề |
|---|---|---|---|
| **Oracle Cloud Always Free** | ✅ Có, vĩnh viễn | ✅ Có | Cần thẻ để đăng ký, hay hết capacity lúc tạo VM, VM ít dùng có thể bị thu hồi. Nhưng là lựa chọn free tốt nhất cho bot nhạc (2 OCPU / 12GB ARM hoặc 2 VM AMD 1GB). |
| **Railway** | Trial $5 / 30 ngày, sau đó $1/tháng | ✅ Trong lúc còn credit | Hết credit là bot tắt. Deploy dễ nhất, 1 click từ GitHub. |
| **Fly.io** | Không còn free tier cho tài khoản mới (trial 7 ngày) | ❌ Hết trial là tính tiền | Rẻ nhất trong nhóm trả phí: ~$1.94–2.19/tháng cho 256MB. File `fly.toml` đã có sẵn. |
| **Render free** | ✅ Có | ❌ Ngủ sau 15 phút không có traffic, không có worker free | Bot nhạc sẽ lúc on lúc off, không nên dùng chính thức. File `render.yaml` chỉ để test. |
| **Replit / Heroku / Glitch** | ❌ | ❌ | Đã bỏ always-on free từ lâu. |
| **Máy nhà / Raspberry Pi** | ✅ | ✅ Khi máy bật | Tốn điện, tự lo mạng + restart. |

**Khuyến nghị của mình:** muốn 0đ thật thì **Oracle Cloud**. Muốn deploy nhanh nhất, chấp nhận $5 trial rồi ~$2/tháng thì **Fly.io / Railway**.

### Oracle Cloud (0đ, 24/7) — tóm tắt
1. Đăng ký Oracle Cloud Free Tier (cần thẻ, không trừ tiền nếu chỉ dùng Always Free)
2. Tạo VM ARM: 1 OCPU, 6GB RAM, Ubuntu 22.04, mở port 22
3. SSH vào, chạy:
```bash
sudo apt update && sudo apt install -y python3-pip ffmpeg nodejs git
git clone <repo-cua-ban> && cd discord-music-bot
pip install -r requirements.txt
cp .env.example .env && nano .env   # điền DISCORD_TOKEN
# Chạy nền, tự restart khi crash / reboot:
sudo apt install -y tmux
tmux new -s bot
python3 bot.py
# Ctrl+B rồi D để thoát tmux, bot vẫn chạy
```
Nâng cao: dùng `systemd` thay tmux để tự chạy lại sau reboot.

### Railway (dễ nhất)
1. Push code lên GitHub (nhớ `.gitignore` đã chặn `.env`)
2. railway.app → New Project → Deploy from GitHub → chọn repo
3. Variables → thêm `DISCORD_TOKEN`
4. Railway tự detect Dockerfile và chạy. Hết $5 trial thì bot dừng, nạp thêm hoặc chuyển Oracle.

### Fly.io (~$2/tháng)
```bash
fly launch --no-deploy
fly secrets set DISCORD_TOKEN=xxx
fly deploy
fly logs
```

## 4. Lỗi hay gặp với YouTube

Stream nhạc YouTube qua bot **vi phạm Điều khoản YouTube** (chỉ dùng cho cá nhân / học tập), và YouTube ngày càng chặn yt-dlp, nhất là từ IP datacenter (Render/Railway/Fly/Oracle đều là datacenter).

- `ERROR: Sign in to confirm you're not a bot` / `HTTP 403` → thử: `pip install -U yt-dlp` rồi restart. Vẫn lỗi thì thêm `cookies.txt`:
  1. Dùng tài khoản Google **phụ**, cài extension "Get cookies.txt LOCALLY" trên Chrome
  2. Mở youtube.com, export cookies → lưu thành `cookies.txt` trong thư mục bot
  3. Hoặc set env `COOKIES_TXT` = base64 của file đó (bot sẽ tự ghi ra `cookies.txt`)
  4. Không dùng tài khoản chính, không share file này.
- Bot vào voice nhưng không có tiếng → thiếu FFmpeg / thiếu quyền Speak / sai voice channel.
- Slash command không hiện → đợi 5–10 phút sau khi bot online lần đầu, hoặc kick bot ra mời lại.

## 5. Bảo mật

- Không bao giờ commit `.env` / `cookies.txt` / token lên GitHub công khai.
- Token lộ → vào Developer Portal → Reset Token ngay.
