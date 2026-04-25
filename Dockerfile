FROM python:3.11-slim

WORKDIR /app

# Copy and install requirements first for caching
COPY learnr/backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application (both frontend and backend)
COPY learnr/ .

# Set working directory to backend where main.py lives
WORKDIR /app/backend

# Run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
