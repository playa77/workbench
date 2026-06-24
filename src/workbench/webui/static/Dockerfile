FROM python:3.12-slim

WORKDIR /app

# Install tectonic (modern LaTeX engine) runtime dependencies + professional fonts
RUN apt-get update && apt-get install -y --no-install-recommends \
    libfontconfig1 libgraphite2-3 libharfbuzz0b \
    fonts-linuxlibertine fonts-inconsolata git \
    && rm -rf /var/lib/apt/lists/*

# Install tectonic — single-binary modern LaTeX engine (XeTeX-based, auto-fetch packages)
RUN python3 -c "import urllib.request; import io, tarfile; \
    data = urllib.request.urlopen('https://github.com/tectonic-typesetting/tectonic/releases/download/tectonic%400.15.0/tectonic-0.15.0-x86_64-unknown-linux-gnu.tar.gz').read(); \
    tf = tarfile.open(fileobj=io.BytesIO(data)); \
    tf.extract('tectonic', '/usr/local/bin/')" && \
    chmod +x /usr/local/bin/tectonic && tectonic --version

# Copy build artifacts first so hatchling can find the package source
COPY pyproject.toml .
COPY src/ src/
COPY agents/ agents/
RUN pip install --no-cache-dir ".[news,research]"

# Copy remaining files (config, alembic, etc.)
COPY . .

CMD ["workbench", "serve", "--host", "0.0.0.0", "--port", "8420"]
