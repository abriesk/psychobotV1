FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for building python packages
RUN apt-get update && apt-get install -y gcc libpq-dev curl && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/

# Copy Alembic configuration and migrations
COPY alembic/ ./alembic/
COPY alembic.ini .

# Copy data migration scripts
COPY migrations/ ./migrations/

# Create landings directory if not exists
RUN mkdir -p landings

CMD ["python", "-m", "app.main"]
