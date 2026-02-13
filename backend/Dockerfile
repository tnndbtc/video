FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsndfile1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN pip install poetry && \
    poetry config virtualenvs.create false

# Copy dependency files first for better caching
COPY pyproject.toml poetry.lock* ./

# Install dependencies (--only main replaces deprecated --no-dev in Poetry 1.2+)
# --no-root skips installing the project itself (we just need dependencies)
RUN poetry install --only main --no-root --no-interaction --no-ansi

# Copy application code
COPY . .

# Create data directories
RUN mkdir -p /data/db /data/uploads /data/derived /data/outputs

# Expose port
EXPOSE 8000

# Run uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
