FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

COPY backend/pyproject.toml .
COPY backend/src ./src
RUN pip install --no-cache-dir .

COPY backend/ .
COPY meltano ./meltano

# Install meltano for worker tasks
RUN pip install --no-cache-dir meltano

CMD ["celery", "-A", "src.core.celery_app", "worker", "--loglevel=info"]
