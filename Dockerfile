FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    awscli \
    libsndfile1 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy application files
COPY . /app/

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Make sure models directory is accessible
RUN chmod -R 755 /app/models

# Set environment variables for TensorFlow
ENV PYTHONUNBUFFERED=1
ENV TENSORFLOW_CPP_MIN_LOG_LEVEL=2

CMD ["python3", "voiceimage.py"]