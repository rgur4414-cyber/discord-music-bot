FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg nodejs && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY bot.py .
# yt-dlp can ban moi nhat luc chay (YouTube doi lien tuc)
RUN pip install --no-cache-dir -U yt-dlp
CMD ["python", "bot.py"]
