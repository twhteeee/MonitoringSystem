# --------------------------------------------------------------------------- #
# Stage 1 — dependency builder
# --------------------------------------------------------------------------- #
FROM python:3.11-slim AS builder

WORKDIR /build

# Install uv (fast pip replacement)
RUN pip install --no-cache-dir uv==0.2.13

COPY pyproject.toml .
RUN uv pip install --system --no-cache -r pyproject.toml

# --------------------------------------------------------------------------- #
# Stage 2 — ODBC driver layer
# --------------------------------------------------------------------------- #
FROM python:3.11-slim AS odbc

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gnupg \
    unixodbc \
    unixodbc-dev \
  && curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg \
  && curl -fsSL https://packages.microsoft.com/config/debian/12/prod.list > /etc/apt/sources.list.d/mssql-release.list \
  && apt-get update \
  && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*

# --------------------------------------------------------------------------- #
# Stage 3 — final runtime image
# --------------------------------------------------------------------------- #
FROM python:3.11-slim AS runtime

# Copy ODBC drivers from odbc stage
COPY --from=odbc /usr/lib/x86_64-linux-gnu/libodbc* /usr/lib/x86_64-linux-gnu/
COPY --from=odbc /opt/microsoft/msodbcsql18 /opt/microsoft/msodbcsql18
COPY --from=odbc /etc/odbcinst.ini /etc/odbcinst.ini
COPY --from=odbc /etc/odbc.ini /etc/odbc.ini

# Install runtime system deps only
RUN apt-get update && apt-get install -y --no-install-recommends \
    unixodbc \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

WORKDIR /app

# Non-root user for security
RUN groupadd --gid 1001 appuser && useradd --uid 1001 --gid appuser --shell /bin/bash appuser

COPY --chown=appuser:appuser . .

USER appuser

EXPOSE 8000

# Uvicorn with 2 workers per CPU core (adjust to Container App vCPU allocation)
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "4", \
     "--loop", "uvloop", \
     "--http", "httptools", \
     "--proxy-headers", \
     "--forwarded-allow-ips", "*", \
     "--log-config", "/dev/null"]
