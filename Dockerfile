FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg nodejs curl unzip ca-certificates && rm -rf /var/lib/apt/lists/*
# yt-dlp can JS runtime de giai ma format (n-token). Mac dinh no dung deno,
# nen cai deno + dam bao co lenh `node` (Debian co khi chi co `nodejs`).
RUN curl -fsSL https://deno.land/install.sh | sh
ENV DENO_INSTALL="/root/.deno"
ENV PATH="$DENO_INSTALL/bin:$PATH"
RUN if [ ! -e /usr/bin/node ] && [ -e /usr/bin/nodejs ]; then ln -s /usr/bin/nodejs /usr/bin/node; fi; node --version; deno --version || true
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY bot.py .
# yt-dlp can ban moi nhat luc chay (YouTube doi lien tuc)
RUN pip install --no-cache-dir -U yt-dlp
CMD ["python", "bot.py"]
