FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

# Отключаем запуск бота в контейнере по умолчанию
# Экспонируем Flask (по умолчанию 5000)
EXPOSE 5000

CMD ["python", "app.py"]





