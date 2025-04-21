# Dockerfile
FROM registry.access.redhat.com/ubi8/python-39:latest

WORKDIR /app

# Copy requirements first for better layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY . .

# Run as non-root user
USER 1001

# Expose the application port
EXPOSE 5000

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=5000

# Start the application
CMD ["python", "app.py"]
