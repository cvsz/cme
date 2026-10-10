FROM python:3.12-slim AS runtime

ARG CME_RELEASE_SHA=REPLACE_ME
LABEL org.opencontainers.image.revision="${CME_RELEASE_SHA}"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN addgroup --system cme && adduser --system --ingroup cme cme
WORKDIR /app

COPY apps/api/pyproject.toml ./pyproject.toml
COPY apps/api/alembic.ini ./alembic.ini
COPY apps/api/migrations ./migrations
COPY apps/api/cme_api ./cme_api
RUN pip install --no-cache-dir .

USER cme
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"

CMD ["uvicorn", "cme_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
