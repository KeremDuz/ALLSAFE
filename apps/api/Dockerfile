FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY apps/api/pyproject.toml ./pyproject.toml
COPY apps/api/requirements.lock ./requirements.lock
COPY apps/api/src ./src
RUN pip install --no-cache-dir -r requirements.lock \
    && pip install --no-cache-dir --no-deps . \
    && useradd --create-home --uid 10001 allsafe \
    && mkdir -p /app/data \
    && chown -R allsafe:allsafe /app/data

USER allsafe
EXPOSE 8000
CMD ["uvicorn", "allsafe_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
