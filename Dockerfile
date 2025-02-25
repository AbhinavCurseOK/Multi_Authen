FROM python:3.12-slim

# Install system dependencies including git and git-lfs
RUN apt-get update && apt-get install -y \
    awscli \
    libsndfile1 \
    ffmpeg \
    git \
    git-lfs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Initialize Git LFS
RUN git lfs install

# Copy application files
COPY . /app/

# Set permissions for models directory
RUN chmod -R 755 /app/models

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Set environment variables for TensorFlow
ENV PYTHONUNBUFFERED=1
ENV TENSORFLOW_CPP_MIN_LOG_LEVEL=2

CMD ["python3", "voiceimage.py"]