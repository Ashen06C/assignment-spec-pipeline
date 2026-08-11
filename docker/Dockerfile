# ==============================================================================
# Dockerfile for AI-Native Spec-Driven Pipeline Web Studio & CLI
# ==============================================================================

FROM python:3.12-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# Set working directory
WORKDIR /app

# Install system utilities
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy configuration and project definitions
COPY pyproject.toml README.md ./

# Install package dependencies
RUN pip install --upgrade pip && \
    pip install -e ".[dev]"

# Copy source code and assets
COPY spec_pipeline/ ./spec_pipeline/
COPY examples/ ./examples/
COPY demo.py run_ui.py ./

# Create default directories
RUN mkdir -p /app/artifacts /app/sandbox

# Expose Web Studio port
EXPOSE 8000

# Default entrypoint runs Web Studio
CMD ["python", "run_ui.py", "--host", "0.0.0.0", "--port", "8000", "--no-browser"]
