FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Non-root user for security
RUN adduser --disabled-password --gecos "" appuser
USER appuser

EXPOSE 3000

# Production server: gunicorn with 4 workers
CMD ["gunicorn", "--workers", "4", "--bind", "0.0.0.0:3000", "--timeout", "60", "--access-logfile", "-", "run:app"]
