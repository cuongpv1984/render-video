FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core && rm -rf /var/lib/apt/lists/*
WORKDIR /studio
COPY services/api/requirements.txt /studio/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY services/api/app /studio/services/api/app
COPY db /studio/db
COPY apps/web/public/art /studio/apps/web/public/art
ENV PYTHONPATH=/studio/services/api PYTHONUNBUFFERED=1 DATA_DIR=/studio/data
RUN useradd --create-home studio && mkdir -p /studio/data && chown -R studio:studio /studio
USER studio
EXPOSE 8080
CMD ["python","-m","app.serve"]
