FROM python:3.12-slim

WORKDIR /app

# Install system dependencies including GDAL
RUN apt-get update -qq && apt-get install -y \
    gcc \
    g++ \
    make \
    cmake \
    gdal-bin \
    libgdal-dev \
    libproj-dev \
    && rm -rf /var/lib/apt/lists/*

# Install GDAL Python bindings with correct version
# Use environment variables instead of deprecated --global-option
ENV CPLUS_INCLUDE_PATH=/usr/include/gdal
ENV C_INCLUDE_PATH=/usr/include/gdal
RUN pip install GDAL==`gdal-config --version`

# Copy and install core package first
COPY packages/core /app/core
RUN pip install -e /app/core

# Copy and install API package (includes dependencies from pyproject.toml)
COPY packages/api /app/api
RUN pip install -e /app/api

# Set working directory to API
WORKDIR /app/api

# Expose port
EXPOSE 8000

# Run uvicorn
CMD ["uvicorn", "spheraform_api.main:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "debug"]
