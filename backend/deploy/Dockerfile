FROM python:3.12-slim AS base

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# ============================================
# Development stage
# ============================================
FROM base AS development

# Install uv
RUN pip install uv

# Copy dependency files
COPY pyproject.toml ./

# Install all dependencies (including dev)
RUN uv sync --no-install-project

# Copy source code
COPY . .

# Run development server
CMD ["uvicorn", "backend.web.__main__:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ============================================
# Production stage
# ============================================
FROM base AS production

# Create non-root user
RUN groupadd --gid 1000 appgroup && \
    useradd --uid 1000 --gid 1000 --shell /bin/bash appuser

# Install uv
RUN pip install uv

# Copy dependency files
COPY pyproject.toml ./

# Install production dependencies only
RUN uv sync --no-install-project --no-group dev

# Copy source code
COPY --chown=appuser:appgroup . .

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run application
CMD ["uvicorn", "backend.web.__main__:app", "--host", "0.0.0.0", "--port", "8000"]
