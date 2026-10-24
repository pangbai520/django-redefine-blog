FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY requirements.txt requirements-postgresql.txt requirements-production.txt requirements-redis.txt ./
RUN python -m pip install --upgrade pip && \
    python -m pip install -r requirements-production.txt -r requirements-redis.txt

COPY . .
RUN sed -i 's/\r$//' deploy/docker-entrypoint.sh && chmod +x deploy/docker-entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/app/deploy/docker-entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--access-logfile", "-"]
