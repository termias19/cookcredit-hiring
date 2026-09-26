# CookCredit backend — Cloud Run container.
#
# Python 3.12 (numpy 2.2.1 / scipy 1.15.1 require >=3.10). The slim base is enough:
# every dep ships a self-contained manylinux wheel (psycopg2-binary bundles libpq,
# Pillow bundles libjpeg/zlib, numpy/scipy bundle OpenBLAS), so NO apt build toolchain
# is needed. Keep it that way — if you add a source-only dep, install its build libs here.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependencies first so this layer caches until requirements.txt changes.
COPY requirements.txt .
RUN pip install -r requirements.txt

# App code. .dockerignore keeps venv/.env/credentials/local junk out of the image.
COPY . .

# Drop root.
RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app
USER appuser

# Cloud Run injects $PORT (default 8080). gunicorn binds it; database.init_db() runs at
# import but create_engine() is lazy, so boot is fast and the first request opens the
# Cloud SQL connection (Unix socket at /cloudsql/<CONNECTION>, mounted by
# --add-cloudsql-instances). Workers/threads are env-tunable; mind the Cloud SQL
# connection budget = workers * (pool_size 5 + max_overflow 10).
ENV PORT=8080 GUNICORN_WORKERS=2 GUNICORN_THREADS=4
CMD exec gunicorn wsgi:app \
    --bind 0.0.0.0:$PORT \
    --workers ${GUNICORN_WORKERS} --threads ${GUNICORN_THREADS} \
    --timeout 120 \
    --access-logfile - --error-logfile -
