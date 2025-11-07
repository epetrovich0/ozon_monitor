# Используем образ с Chrome
FROM selenium/standalone-chrome:130.0

# Устанавливаем Python и зависимости
USER root
RUN apt-get update && apt-get install -y python3 python3-pip
RUN pip3 install --no-cache-dir -r /app/requirements.txt

# Копируем скрипт
COPY . /app
WORKDIR /app

# Запускаем
CMD ["python3", "ozon.py"]