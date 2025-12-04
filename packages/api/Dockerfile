FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy core package
COPY ../core /app/core
RUN pip install -e /app/core

# Copy API package
COPY . /app/api
WORKDIR /app/api

# Expose port
EXPOSE 8000

# Run uvicorn
CMD ["uvicorn", "spheraform_api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
