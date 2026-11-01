# FastAPI API and background worker. They share this image; the worker overrides the command.
FROM python:3.14.3-slim

# Pango for WeasyPrint, and fonts because the slim image has none to render PDF text with.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpango-1.0-0 libpangoft2-1.0-0 fonts-liberation fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

WORKDIR /srv

COPY Pipfile Pipfile.lock ./
RUN pip install --no-cache-dir pipenv==2026.6.1 \
    && pipenv install --deploy --system

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./

RUN useradd --create-home --uid 10001 portal
USER portal

EXPOSE 8001
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
