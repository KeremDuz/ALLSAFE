FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app
COPY deploy/renderer/requirements.lock /tmp/renderer-requirements.lock
RUN pip install --require-hashes -r /tmp/renderer-requirements.lock \
    && python -m playwright install --with-deps chromium \
    && chmod -R a+rX /ms-playwright \
    && groupadd --gid 10001 renderer \
    && useradd --uid 10001 --gid 10001 --no-create-home --home-dir /tmp renderer

COPY packages/phishcatch/apps/backend/app/services/offline_renderer*.py /app/app/services/

USER 10001:10001
CMD ["python", "-m", "app.services.offline_renderer_service"]
