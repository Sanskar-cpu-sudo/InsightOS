# Dockerfile
# This builds a container image for the InsightOS backend.

FROM python:3.13-slim

# Where our code will live inside the container
WORKDIR /app

# System packages needed to build some Python libraries (like psycopg2)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy just requirements first. Docker caches this step, so if you only
# change your own code (not requirements.txt), rebuilding is much faster
# because it skips reinstalling every package again.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Now copy the rest of our actual application code
COPY . .

# The port FastAPI/uvicorn will run on inside the container
EXPOSE 8000

# The command that runs when the container starts
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]