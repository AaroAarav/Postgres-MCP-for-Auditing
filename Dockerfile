# Use a slim Python 3.12 image
FROM python:3.12-slim

# Install system dependencies required for psycopg binary
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set working directory
WORKDIR /app

# Copy dependency files first
COPY pyproject.toml uv.lock README.md ./

# 1. Install DEPENDENCIES ONLY (This caches the heavy downloads)
RUN uv sync --frozen --no-dev --no-install-project

# 2. Copy the actual application code
COPY src/ ./src/

# 3. Install the pg-auditor project itself
RUN uv sync --frozen --no-dev

# Ensure the virtual environment is in the PATH
ENV PATH="/app/.venv/bin:$PATH"

# Set the entrypoint to our CLI
ENTRYPOINT ["pg-auditor"]