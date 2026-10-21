FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 5100
CMD ["sh", "-c", "python seed_demo.py && exec gunicorn -b 0.0.0.0:5100 --workers 1 --threads 4 main_yt_syslog:app"]
