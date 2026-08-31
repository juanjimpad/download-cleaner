FROM python:3.13-alpine
ENV PYTHONUNBUFFERED=1
RUN pip install --no-cache-dir requests
COPY cleaner.py /app/cleaner.py
CMD ["python", "/app/cleaner.py"]
