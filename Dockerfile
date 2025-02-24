FROM python:3.12-slim

RUN apt update -y && apt install awscli -y
WORKDIR /app

COPY . /app
COPY .env /app/.env
RUN pip install -r requirements.txt
#requirements1.txt #i got from #pip freeze > requirements1.txt
CMD ["python3", "voiceimage.py"]