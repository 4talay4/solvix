FROM python:3.11-slim

WORKDIR /app

COPY shared /app/shared
COPY services/bot-admin/requirements.txt /app/services/bot-admin/requirements.txt
RUN pip install --no-cache-dir -r /app/services/bot-admin/requirements.txt

COPY services/bot-admin /app/services/bot-admin

ENV PYTHONPATH=/app
WORKDIR /app/services/bot-admin
CMD ["python", "main.py"]
