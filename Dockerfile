# Use Python 3.11 slim image for smaller size
FROM python:3.11-slim

# Build arguments for metadata
ARG BUILD_DATE
ARG VCS_REF
ARG VERSION

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Add metadata labels
LABEL org.opencontainers.image.title="Birthday Sync" \
      org.opencontainers.image.description="Automated CardDAV to CalDAV birthday synchronization service" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.vendor="Birthday Sync Project" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.source="https://github.com/your-username/your-repo"

# Install system dependencies (minimal)
RUN apt-get update && apt-get install -y \
    tzdata \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Set timezone
ENV TZ=UTC
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Create app directory and user
RUN groupadd -r birthday && useradd -r -g birthday -m birthday
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY bdaysync/ ./bdaysync/

# Change ownership of app files
RUN chown -R birthday:birthday /app

# Create log directory (optional, can use stdout instead)
RUN mkdir -p /var/log/birthday-sync && \
    chown birthday:birthday /var/log/birthday-sync

# Switch to non-root user
USER birthday

# Set default environment variables for scheduling
ENV SYNC_SCHEDULE="0 6 * * *"
ENV DIAGNOSTIC_SCHEDULE="0 7 * * 0"
ENV RUN_MODE="daemon"

# Health check using the Python script itself
HEALTHCHECK --interval=30m --timeout=30s --start-period=1m --retries=3 \
    CMD python bdaysync/main.py --health-check || exit 1

# Run the application
CMD ["python", "bdaysync/main.py"]
