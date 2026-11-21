FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core ca-certificates && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY static ./static
ENV VIETFRAME_DATA=/data VIETFRAME_HOST=0.0.0.0 VIETFRAME_PORT=8010
EXPOSE 8010
# Local/dev binding only. Expose behind authenticated reverse proxy in production.
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8010"]
