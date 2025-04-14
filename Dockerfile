FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    pandoc \
    && rm -rf /var/lib/apt/lists/*

# Create and switch to user
RUN useradd -m -u 1000 user
USER user
ENV PATH="/home/user/.local/bin:$PATH"
ENV PYTHONPATH=/app
ENV GUNICORN_CMD_ARGS="--timeout 600 --keep-alive 60"

# Set up working directory
WORKDIR /app

# Install Python dependencies
COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --upgrade -r requirements.txt && \
    pip install --no-cache-dir --upgrade g4f[all]

# Copy application code and .env file
COPY --chown=user . .
COPY --chown=user .env .env

# Expose port
EXPOSE 7860

# Run the application
CMD ["gunicorn", "--workers", "3", "--bind", "0.0.0.0:7860", "--worker-class", "gevent", "app:app"]