#!/usr/bin/env python3
import os
import time
import logging
from datetime import datetime
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from telegram import Bot
import json

# === НАСТРОЙКИ ===
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('CHAT_ID')
OZON_URL = 'https://ozon.by/category/televizory-15528/?category_was_predicted=true&deny_category_prediction=true&from_global=true&rsdiagonalstr=24.000%3B109.000&sorting=price&text=телевизор&__rr=1'
TARGET_PRICE = 190.0
DATA_FILE = '/tmp/ozon_monitor.json'  # Временный файл (сбрасывается между запусками Actions)

# Логирование
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
bot = Bot(token=TELEGRAM_TOKEN)

def load_state():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_state(state):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def get_min_price():
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')

    try:
        driver = webdriver.Chrome(options=options)
        logger.info("Открываем Ozon...")
        driver.get(OZON_URL)
        time.sleep(12)

        soup = BeautifulSoup(driver.page_source, 'html.parser')
        driver.quit()

        prices = []
        for span in soup.find_all('span', class_='tsHeadline500Medium'):
            text = span.get_text(strip=True)
            price_str = text.replace('BYN', '').replace(' ', '').replace(',', '.').strip()
            try:
                prices.append(float(price_str))
            except:
                continue

        if not prices:
            logger.warning("Цены не найдены")
            return None

        min_price = min(prices)
        logger.info(f"Минимальная цена: {min_price} BYN")
        return min_price

    except Exception as e:
        logger.error(f"Ошибка: {e}")
        if 'driver' in locals():
            driver.quit()
        return None

def send_telegram(message):
    try:
        bot.send_message(chat_id=CHAT_ID, text=message)
        logger.info("Уведомление отправлено!")
    except Exception as e:
        logger.error(f"Ошибка отправки: {e}")

def main():
    logger.info("Запуск проверки...")
    state = load_state()

    now = datetime.utcnow()
    today = now.strftime('%Y-%m-%d')

    price = get_min_price()
    if price:
        daily_min = state.get('daily_min', price)
        last_day = state.get('last_day', today)

        # Обновляем ежедневный минимум
        if price < daily_min:
            daily_min = price

        # Уведомление при цене ниже порога
        if price < TARGET_PRICE:
            send_telegram(
                f"ЦЕНА НИЖЕ {TARGET_PRICE} BYN!\n"
                f"Сейчас: {price} BYN\n"
                f"{OZON_URL}"
            )

        # Первый запуск (или новый день — отправляем текущую цену)
        if 'first_run' not in state or today != last