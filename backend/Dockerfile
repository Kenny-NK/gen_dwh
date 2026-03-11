FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
COPY src ./src
RUN pip install --no-cache-dir .

# Health checks and some admin diagnostics expect Meltano CLI to be present
# in the backend image, not only in the worker image.
RUN pip install --no-cache-dir meltano

COPY . .

EXPOSE 8000

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
