# syntax=docker/dockerfile:1.7
# One image for api (Daphne: HTTP + WebSockets), Celery workers and beat.

FROM python:3.13-slim AS builder
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /build
COPY requirements/ requirements/
ARG REQUIREMENTS=prod
RUN pip wheel --wheel-dir /wheels -r requirements/${REQUIREMENTS}.txt

FROM python:3.13-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DJANGO_SETTINGS_MODULE=config.settings.production
RUN apt-get update && apt-get install -y --no-install-recommends gettext curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system homesika && useradd --system --gid homesika --home /app homesika
WORKDIR /app
COPY --from=builder /wheels /wheels
RUN pip install --no-index --find-links=/wheels /wheels/* && rm -rf /wheels
COPY --chown=homesika:homesika . .
# Static files are collected with production settings at build time. Placeholder values only: the real
# ones (secrets, gateways, providers) come from the host's environment when the container runs.
RUN DJANGO_SECRET_KEY=build-only-not-a-secret DATABASE_URL=sqlite:////tmp/build.db \
    PAYMENT_GATEWAYS=paystack ASSISTANT_PROVIDER=anthropic WHATSAPP_PROVIDER=off BILLS_PROVIDERS=vtung \
    python manage.py collectstatic --noinput \
    && rm -f /tmp/build.db && chown -R homesika:homesika /app
USER homesika
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:${PORT:-8000}/health/live || exit 1
ENTRYPOINT ["./docker/entrypoint.sh"]
# Render (and most hosts) pass the port in $PORT; 8000 locally.
CMD ["sh", "-c", "exec daphne -b 0.0.0.0 -p ${PORT:-8000} --proxy-headers config.asgi:application"]
