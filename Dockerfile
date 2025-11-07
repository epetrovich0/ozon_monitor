FROM selenium/standalone-chrome:130.0

USER root

RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

# Копируем всё
COPY . /app
WORKDIR /app

# Устанавливаем зависимости
RUN pip3 install --no-cache-dir -r requirements.txt

# Запускаем ozon.py (или ozon_price_monitor.py)
CMD ["python3", "ozon.py"]