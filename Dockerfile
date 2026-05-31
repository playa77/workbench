FROM python:3.12-slim

WORKDIR /app

# Copy build artifacts first so hatchling can find the package source
COPY pyproject.toml .
COPY src/ src/
COPY agents/ agents/
RUN pip install --no-cache-dir ".[news,research]"

# Copy remaining files (config, alembic, etc.)
COPY . .

CMD ["workbench", "serve", "--host", "0.0.0.0", "--port", "8420"]
