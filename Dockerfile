FROM python:3.11-slim

# Non-root user for security
RUN groupadd -r revolut && useradd -r -g revolut revolut

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

# Install Python deps first (layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

# Fix ownership
RUN chown -R revolut:revolut /app
USER revolut

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

ENV MCP_TRANSPORT=http
ENV PORT=8080

CMD ["python", "main.py"]
