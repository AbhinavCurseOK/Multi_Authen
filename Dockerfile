FROM python:3.12-slim

# Install system dependencies including audio and video support
RUN apt-get update && apt-get install -y \
    awscli \
    libsndfile1 \
    ffmpeg \
    git \
    git-lfs \
    v4l-utils \
    alsa-utils \
    libportaudio2 \
    portaudio19-dev \
    pulseaudio \
    libasound2 \
    libasound2-plugins \
    && rm -rf /var/lib/apt/lists/*

# Create audio and video groups and add permissions
RUN groupadd -r audio || true && \
    groupadd -r video || true && \
    usermod -a -G audio,video root

# Set environment variables for audio and display
ENV PYTHONUNBUFFERED=1
ENV PULSE_SERVER=unix:/run/pulse/native
ENV DISPLAY=:0

WORKDIR /app

# Initialize Git LFS
RUN git lfs install

# Copy application files
COPY . /app/

# Set permissions for models directory
RUN chmod -R 755 /app/models

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose port
EXPOSE 8080

# Command to run the application
CMD ["python3", "voiceimage.py"]