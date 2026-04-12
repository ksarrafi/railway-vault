FROM python:3.12-alpine

# Install dependencies
RUN pip install --no-cache-dir cryptography==44.0.0

# Create non-root user
RUN adduser -D -h /app vaultuser

# Create data directory
RUN mkdir -p /vault/data && chown -R vaultuser:vaultuser /vault/data

# Copy application
COPY vault_server.py /app/vault_server.py
RUN chown -R vaultuser:vaultuser /app

# Switch to non-root user
USER vaultuser

WORKDIR /app

# Railway expects PORT env var
ENV PORT=9999
ENV VAULT_DB_PATH=/vault/data/secrets.db

# Expose port (Railway will assign its own)
EXPOSE ${PORT}

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT}/health')"

# Run the server
CMD ["python3", "/app/vault_server.py"]
