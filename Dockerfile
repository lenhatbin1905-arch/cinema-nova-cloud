FROM node:22-bookworm-slim AS js-runtime
# Licensed MIT (Jad/AllenK). Build-time vendor: the AI watermark remover
# runs entirely in the user's browser; Render never decodes these clips.
FROM node:22-bookworm-slim AS gwr-assets
WORKDIR /gwr
RUN npm pack @pilio/gemini-watermark-remover@1.0.46 --silent > package-name.txt \
 && tar -xzf "$(cat package-name.txt)" \
 && test -s package/dist/video-preview.html \
 && test -s package/dist/video-app.js \
 && test -s package/LICENSE \
 && mkdir -p /export \
 && cp -a package/dist/. /export/ \
 && cp package/LICENSE /export/LICENSE

FROM python:3.12-slim
WORKDIR /app
# yt-dlp's YouTube EJS solver requires a supported JS runtime.
COPY --from=js-runtime /usr/local/bin/node /usr/local/bin/node
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core ca-certificates && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY static ./static
COPY --from=gwr-assets /export/ ./static/gwr/
COPY scripts/gwr_localize.py ./scripts/gwr_localize.py
RUN python ./scripts/gwr_localize.py
COPY tests ./tests
# Build is blocked if backend, JavaScript, or any pytest regression fails.
RUN python -m compileall -q app \
 && node --check static/app.js \
 && node --check static/gwr/video-app.js \
 && pip install --no-cache-dir 'pytest>=8,<10' \
 && python -m pytest -q tests
ENV VIETFRAME_DATA=/data VIETFRAME_HOST=0.0.0.0 VIETFRAME_PORT=8010
EXPOSE 10000
# Render auto-configures PORT; startup rejects any unauthenticated media API request.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-10000}"]
