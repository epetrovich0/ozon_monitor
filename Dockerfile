# Используем образ с Chrome
FROM selenium/standalone-chrome:130.0

# Устанавливаем Python и зависимости
USER root

# Устанавливаем Python 3 и pip
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

# Копируем файлы
COPY requirements.txt /app/requirements.txt
COPY ozon_price_monitor.py /app/ozon_price_monitor.py

WORKDIR /app

# Устанавливаем зависимости
RUN pip3 install --no-cache-dir -r requirements.txt

# Запускаем скрипт
CMD ["python3", "ozon_price_monitor.py"]