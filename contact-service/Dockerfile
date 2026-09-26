FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY app.py mail_transport.py ./
RUN useradd --uid 10001 --create-home appuser
USER appuser
ENV PORT=8080
CMD exec gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 45 --error-logfile -
