FROM python:3.12-slim
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
RUN groupadd -r audio || true && \
    groupadd -r video || true && \
    usermod -a -G audio,video root
    
ENV PYTHONUNBUFFERED=1
ENV PULSE_SERVER=unix:/run/pulse/native
ENV DISPLAY=:0

WORKDIR /app

RUN git lfs install
COPY . /app/

RUN chmod -R 755 /app/models
RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 8080

CMD ["python3", "voiceimage.py"]