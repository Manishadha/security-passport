FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gcc \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir poetry==1.8.3

COPY apps/api/pyproject.toml apps/api/poetry.lock* /app/
RUN poetry config virtualenvs.create false
RUN poetry install --only main --no-interaction --no-ansi

COPY apps/api /app

EXPOSE 58000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "58000", "--no-access-log"]