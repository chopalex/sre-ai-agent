FROM python:3.12-slim

# Install system diagnostics and networking utilities for SRE operations
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    iproute2 \
    procps \
    net-tools \
    dnsutils \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create dedicated non-root ops user
RUN useradd -u 1000 -m -s /bin/bash opsuser

WORKDIR /app

# Copy dependency definition and install
COPY pyproject.toml .
RUN pip install --no-cache-dir .

# Copy application source code and documentation
COPY src/ ./src/
COPY docs/ ./docs/
COPY README.md .

# Create logs directory with proper permissions
RUN mkdir -p logs && chown -R opsuser:opsuser /app

USER opsuser

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    DOCS_DIR=/app/docs

EXPOSE 8000

CMD ["uvicorn", "src.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
