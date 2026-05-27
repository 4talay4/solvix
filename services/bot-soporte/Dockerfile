FROM python:3.11-slim

WORKDIR /app

COPY shared /app/shared
COPY services/bot-soporte/requirements.txt /app/services/bot-soporte/requirements.txt
RUN pip install --no-cache-dir -r /app/services/bot-soporte/requirements.txt

COPY services/bot-soporte /app/services/bot-soporte

ENV PYTHONPATH=/app
WORKDIR /app/services/bot-soporte
CMD ["python", "main.py"]
