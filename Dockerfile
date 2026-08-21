FROM python:3.13-slim

# Install system dependencies required for pdfplumber and ML packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    libjpeg62-turbo \
    libjpeg-dev \
    zlib1g-dev \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user
RUN groupadd -r appuser && useradd -r -g appuser appuser

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY backend/ backend/
COPY investigative_copilot/ investigative_copilot/

# Create data directory with appropriate permissions
RUN mkdir -p /app/data /app/data/cases /app/backend/data && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "backend.api:app", "--host", "0.0.0.0", "--port", "8000"]
