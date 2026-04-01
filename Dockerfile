# Use official Python base image
FROM python:3.13-slim

# Set working directory
WORKDIR /app

# Copy project dependencies
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Create database directory and initialize database
RUN mkdir -p /app/data && \
    python -c "from main import init_db; init_db()" && \
    chmod 777 /app/users.db

# Expose port
EXPOSE 8000

# Run application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
