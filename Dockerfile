FROM ghcr.io/astral-sh/uv:0.11.9 AS uv
FROM python:3.12-slim

COPY --from=uv /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --extra storage-s3

COPY . .

# WhiteNoise serves STATIC_ROOT. Production settings refuse to import without
# secrets; static storage is defined in base settings, which local imports.
RUN DJANGO_SETTINGS_MODULE=config.settings.local \
    python manage.py collectstatic --noinput

EXPOSE 8000

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]
