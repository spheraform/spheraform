FROM python:3.12-slim

WORKDIR /app

# Install system dependencies including GDAL and tippecanoe build deps
RUN apt-get update -qq && apt-get install -y \
    gcc \
    g++ \
    make \
    cmake \
    git \
    zlib1g-dev \
    libsqlite3-dev \
    gdal-bin \
    libgdal-dev \
    libproj-dev \
    && rm -rf /var/lib/apt/lists/*

# Build and install tippecanoe from source
RUN git clone https://github.com/felt/tippecanoe.git /tmp/tippecanoe && \
    cd /tmp/tippecanoe && \
    make -j$(nproc) && \
    make install && \
    rm -rf /tmp/tippecanoe

# Install GDAL Python bindings with correct version
# Use environment variables instead of deprecated --global-option
ENV CPLUS_INCLUDE_PATH=/usr/include/gdal
ENV C_INCLUDE_PATH=/usr/include/gdal
RUN pip install GDAL==`gdal-config --version`

# Copy and install core package first
COPY ./packages/core /app/core
RUN pip install -e /app/core

# Copy and install API package (includes dependencies from pyproject.toml)
COPY ./packages/api /app/api
RUN pip install -e /app/api

# Copy alembic migrations
COPY ./alembic /app/alembic
COPY ./alembic.ini /app/alembic.ini

# Set working directory to app root (for alembic)
WORKDIR /app

# Expose port
EXPOSE 8000

# Run uvicorn (spheraform_api is installed as editable package)
CMD ["uvicorn", "spheraform_api.main:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "info"]
