"""
Discord Music Bot — Python + discord.py + yt-dlp + FFmpeg
Chay:  python bot.py
Lenh:  /play <link YouTube hoac ten bai> | /skip | /queue | /pause | /resume
        /stop | /leave | /nowplaying | /volume <0-100>

Chi can 1 bien moi truong: DISCORD_TOKEN
Tuy chon: COOKIES_TXT (noi dung file cookies.txt, base64) de giam bi YouTube chan IP datacenter.
"""
import asyncio
import base64
import os
import re
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import discord
import yt_dlp
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise SystemExit("Thieu DISCORD_TOKEN — tao file .env theo .env.example roi chay lai.")

# --- Health-check server (cho Render / Fly / Railway ping, khong anh huong bot) ---
# Render free se sleep sau 15 phut khong co traffic, server nay chi de UptimeRobot ping duoc.
PORT = int(os.getenv("PORT", "0") or 0)
if PORT:
    class _H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200); self.end_headers(); self.wfile.write(b"ok")
        def log_message(self, *a):
            pass
    threading.Thread(target=HTTPServer(("0.0.0.0", PORT), _H).serve_forever, daemon=True).start()
    print(f"Health server on :{PORT}")

# --- yt-dlp ---
# Neu co cookies.txt (xuat tu trinh duyet bang extension Get cookies.txt) thi dung no.
# Cach 2: set env COOKIES_TXT = base64 cua noi dung cookies.txt
COOKIE_FILE = "cookies.txt"
if os.getenv("COOKIES_TXT") and not os.path.exists(COOKIE_FILE):
    with open(COOKIE_FILE, "wb") as f:
        f.write(base64.b64decode(os.getenv("COOKIES_TXT")))
    print("Da ghi cookies.txt tu COOKIES_TXT")

YTDL_OPTS = {
    "format": "bestaudio/best",
    "quiet": True,
    "noplaylist": False,          # playlist se lay toi da 10 bai (gioi han o duoi)
    "extract_flat": False,
    "no_warnings": True,
    "default_search": "ytsearch",
    "source_address": "0.0.0.0",
    "cookiefile": COOKIE_FILE if os.path.exists(COOKIE_FILE) else None,
    "retries": 3,
    "fragment_retries": 3,
    "socket_timeout": 30,
    "http_headers": {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    },
    # Giam bi chan: thu nhieu client.
    # BO QUA player_skip: bo qua webpage player lam mat mot so format,
    # gay ra loi "Requested format is not available" tren Railway.
    # Luu y: IP datacenter (Railway) van hay bi YouTube chan - cach chac nhat
    # la them cookies.txt (xem COOKIES_TXT o tren, huong dan trong README).
    "extractor_args": {
        "youtube": {
            "player_client": ["web", "android", "ios"],
        }
    },
}
FFMPEG_OPTS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}
YOUTUBE_RE = re.compile(r"(https?://)?(www\.)?(youtube\.com|youtu\.be)/")

intents = discord.Intents.default()
intents.voice_states = True
intents.message_content = True  # da bat trong Developer Portal, bat them o day de het warning
bot = commands.Bot(command_prefix="!", intents=intents)

# queue[guild_id] = list[dict(title, url, webpage_url, duration, requester)]
queues: dict[int, list[dict]] = {}
volumes: dict[int, float] = {}
# text_channels[guild_id] = channel text dung de bao "dang phat"
# Khong gan truc tiep len Guild: discord.py dung __slots__ nen Guild khong co
# attribute tu do, gan guild._music_text_channel se loi AttributeError.
text_channels: dict[int, object] = {}

def _fmt_duration(sec):
    if not sec:
        return "??:??"
    m, s = divmod(int(sec), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"

def _extract(query: str) -> list[dict]:
    """Tra ve list bai hat. query la URL hoac ten bai."""
    q = query.strip()
    if not YOUTUBE_RE.search(q):
        q = f"ytsearch1:{q}"
    # Thu lan luot cac format: bestaudio truoc, roi best (video+audio,
    # FFmpeg se lay phan tieng voi -vn), roi de yt-dlp tu chon.
    # Mot so video tren Railway bao "Requested format is not available"
    # voi bestaudio nhung lai co best, hoac nguoc lai.
    last_err = None
    for fmt in ("bestaudio/best", "best", None):
        opts = dict(YTDL_OPTS)
        if fmt is None:
            opts.pop("format", None)
        else:
            opts["format"] = fmt
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(q, download=False)
            break
        except Exception as e:
            last_err = e
            print(f"yt-dlp format {fmt!r} failed: {e}")
            info = None
            continue
    if last_err is not None and info is None:
        raise last_err
    if not info:
        return []
    entries = info.get("entries") or [info]
    out = []
    for e in entries[:10]:  # gioi han playlist 10 bai
        if not e:
            continue
        url = e.get("url") or (e.get("formats") or [{}])[-1].get("url")
        if not url:
            continue
        out.append({
            "title": e.get("title") or "Unknown",
            "url": url,
            "webpage_url": e.get("webpage_url") or q,
            "duration": e.get("duration"),
        })
    return out

async def _play_next(guild: discord.Guild):
    q = queues.get(guild.id, [])
    vc = guild.voice_client
    if not vc:
        return
    if not q:
        # Tu roi sau 60s neu khong co nhac
        await asyncio.sleep(60)
        if not queues.get(guild.id) and vc.is_connected() and not vc.is_playing():
            await vc.disconnect()
        return
    song = q.pop(0)
    vol = volumes.get(guild.id, 0.5)
    try:
        source = discord.PCMVolumeTransformer(
            discord.FFmpegOpusAudio(song["url"], **FFMPEG_OPTS), volume=vol
        )
    except Exception as e:
        print("FFmpeg error:", e)
        await _play_next(guild)
        return
    vc.play(source, after=lambda err: asyncio.run_coroutine_threadsafe(_play_next(guild), bot.loop))
    # Bao dang phat o channel text gan nhat (luu trong dict rieng)
    ch = text_channels.get(guild.id)
    if ch:
        try:
            await ch.send(f"▶️ Đang phát: **{song['title']}** ({_fmt_duration(song['duration'])})")
        except Exception:
            pass

@bot.event
async def on_ready():
    print(f"✅ Bot online: {bot.user} — {len(bot.guilds)} server")
    try:
        await bot.tree.sync()
        print("✅ Slash commands synced")
    except Exception as e:
        print("Sync error:", e)

@bot.tree.command(name="play", description="Phát nhạc từ link YouTube hoặc tên bài hát")
@app_commands.describe(query="Link YouTube, link playlist, hoặc tên bài hát")
async def play(interaction: discord.Interaction, query: str):
    if not interaction.user.voice or not interaction.user.voice.channel:
        await interaction.response.send_message("❌ Bạn phải vào voice channel trước đã.", ephemeral=True)
        return
    await interaction.response.defer()
    guild = interaction.guild
    text_channels[guild.id] = interaction.channel
    vc = guild.voice_client
    if not vc:
        vc = await interaction.user.voice.channel.connect()
    elif vc.channel != interaction.user.voice.channel:
        await vc.move_to(interaction.user.voice.channel)

    try:
        songs = await asyncio.to_thread(_extract, query)
    except Exception as e:
        msg = str(e)
        if "Sign in to confirm" in msg or "not a bot" in msg:
            await interaction.followup.send(
                "❌ YouTube chặn IP của server (Railway) nên không lấy được nhạc.\n"
                "Cách sửa: thêm cookies YouTube vào Railway (biến COOKIES_TXT, xem README mục 4) "
                "rồi thử lại. Dùng tài khoản Google phụ, không dùng tài khoản chính."
            )
        else:
            await interaction.followup.send(f"❌ Không lấy được nhạc từ YouTube: `{msg[:200]}`\nGợi ý: thử link khác, hoặc cập nhật yt-dlp / thêm cookies.txt (xem README).")
        return
    if not songs:
        await interaction.followup.send("❌ Không tìm thấy bài hát nào.")
        return
    queues.setdefault(guild.id, []).extend([{**s, "requester": interaction.user.display_name} for s in songs])
    if len(songs) == 1:
        await interaction.followup.send(f"🎵 Đã thêm vào hàng chờ: **{songs[0]['title']}** ({_fmt_duration(songs[0]['duration'])})")
    else:
        await interaction.followup.send(f"🎵 Đã thêm playlist: **{len(songs)} bài**, bắt đầu với **{songs[0]['title']}**")
    if not vc.is_playing() and not vc.is_paused():
        await _play_next(guild)

@bot.tree.command(name="skip", description="Bỏ qua bài đang phát")
async def skip(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and (vc.is_playing() or vc.is_paused()):
        vc.stop()
        await interaction.response.send_message("⏭️ Đã skip.")
    else:
        await interaction.response.send_message("❌ Không có bài nào đang phát.", ephemeral=True)

@bot.tree.command(name="queue", description="Xem hàng chờ")
async def queue(interaction: discord.Interaction):
    q = queues.get(interaction.guild.id, [])
    vc = interaction.guild.voice_client
    text = "📜 **Hàng chờ:**\n"
    if not q and not (vc and vc.is_playing()):
        text += "_Trống._"
    else:
        for i, s in enumerate(q[:10], 1):
            text += f"{i}. {s['title']} ({_fmt_duration(s['duration'])}) — {s['requester']}\n"
        if len(q) > 10:
            text += f"... và {len(q)-10} bài nữa"
    await interaction.response.send_message(text)

@bot.tree.command(name="pause", description="Tạm dừng")
async def pause(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and vc.is_playing():
        vc.pause(); await interaction.response.send_message("⏸️ Đã pause.")
    else:
        await interaction.response.send_message("❌ Không có bài nào đang phát.", ephemeral=True)

@bot.tree.command(name="resume", description="Phát tiếp")
async def resume(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and vc.is_paused():
        vc.resume(); await interaction.response.send_message("▶️ Phát tiếp.")
    else:
        await interaction.response.send_message("❌ Không có bài nào đang pause.", ephemeral=True)

@bot.tree.command(name="nowplaying", description="Xem bài đang phát")
async def nowplaying(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and (vc.is_playing() or vc.is_paused()):
        await interaction.response.send_message("🎧 Đang phát nhạc trong voice channel của bạn.")
    else:
        await interaction.response.send_message("❌ Không có bài nào đang phát.", ephemeral=True)

@bot.tree.command(name="volume", description="Chỉnh âm lượng 0-100")
@app_commands.describe(level="0 - 100")
async def volume(interaction: discord.Interaction, level: int):
    level = max(0, min(100, level))
    volumes[interaction.guild.id] = level / 100
    vc = interaction.guild.voice_client
    if vc and vc.source and isinstance(vc.source, discord.PCMVolumeTransformer):
        vc.source.volume = level / 100
    await interaction.response.send_message(f"🔊 Âm lượng: {level}%")

@bot.tree.command(name="stop", description="Dừng nhạc và xóa hàng chờ")
async def stop(interaction: discord.Interaction):
    queues[interaction.guild.id] = []
    vc = interaction.guild.voice_client
    if vc:
        vc.stop()
    await interaction.response.send_message("⏹️ Đã dừng và xóa hàng chờ.")

@bot.tree.command(name="leave", description="Bot rời voice channel")
async def leave(interaction: discord.Interaction):
    queues[interaction.guild.id] = []
    vc = interaction.guild.voice_client
    if vc:
        await vc.disconnect()
    await interaction.response.send_message("👋 Bot đã rời voice.")

if __name__ == "__main__":
    bot.run(TOKEN)
