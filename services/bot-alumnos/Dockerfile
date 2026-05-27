FROM python:3.11-slim

WORKDIR /app

COPY shared /app/shared
COPY services/bot-alumnos/requirements.txt /app/services/bot-alumnos/requirements.txt
RUN pip install --no-cache-dir -r /app/services/bot-alumnos/requirements.txt

COPY services/bot-alumnos /app/services/bot-alumnos
COPY data /app/data

ENV PYTHONPATH=/app
WORKDIR /app/services/bot-alumnos
CMD ["python", "main.py"]
