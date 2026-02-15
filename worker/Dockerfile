FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (including build tools for madmom/Cython)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsndfile1 \
    libffi-dev \
    gcc \
    g++ \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for running FFmpeg jobs (security)
# Use explicit UID 1000 for consistency with backend
RUN useradd --create-home --shell /bin/bash --uid 1000 worker

# Install Poetry, Cython, and numpy (required for building madmom)
RUN pip install poetry cython numpy && \
    poetry config virtualenvs.create false

# Pre-install madmom with pip (poetry's isolated build doesn't have Cython)
# This ensures madmom is built with system-level Cython available
RUN pip install madmom==0.16.1

# Copy dependency files first for better caching
COPY pyproject.toml poetry.lock* ./

# Install remaining dependencies (madmom already installed, will be skipped)
# --only main replaces deprecated --no-dev in Poetry 1.2+
# --no-root skips installing the project itself (we just need dependencies)
RUN poetry install --only main --no-root --no-interaction --no-ansi

# Copy application code
COPY . .

# Ensure data directories are accessible
RUN mkdir -p /data && chown -R worker:worker /data

# Change ownership of app directory
RUN chown -R worker:worker /app

# Switch to non-root user (critical for security)
USER worker

# Run worker
CMD ["python", "-m", "app.main"]
