FROM selenium/standalone-chrome:130.0

USER root

# Устанавливаем Python и pip
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    && rm -rf /var/lib/apt/lists/*

# Создаём виртуальное окружение
RUN python3 -m venv /app/venv

# Копируем файлы
COPY requirements.txt /app/requirements.txt
COPY ozon.py /app/ozon.py

WORKDIR /app

# Устанавливаем зависимости в venv
RUN /app/venv/bin/pip install --no-cache-dir -r requirements.txt

# Запускаем через venv
CMD ["/app/venv/bin/python", "ozon.py"]