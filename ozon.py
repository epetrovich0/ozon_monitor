#!/usr/bin/env python3
import os
import time
import logging
import json
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from telegram import Bot
import asyncio

# === НАСТРОЙКИ ===
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('CHAT_ID')
OZON_URL = 'https://ozon.by/category/televizory-15528/?category_was_predicted=true&deny_category_prediction=true&from_global=true&rsdiagonalstr=24.000%3B109.000&sorting=price&text=телевизор&__rr=1'
TARGET_PRICE = 190.0
DATA_FILE = '/tmp/ozon_monitor.json'

# Минск = UTC+3
MINSK_TZ = timezone(timedelta(hours=3))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# === Загрузка/сохранение состояния ===
def load_state():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Ошибка чтения состояния: {e}")
            return {}
    return {}

def save_state(state):
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка сохранения: {e}")

# === Получение цены ===
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
        logger.error(f"Ошибка Selenium: {e}")
        if 'driver' in locals():
            driver.quit()
        return None

# === Асинхронная отправка ===
async def send_telegram(bot: Bot, message: str):
    try:
        await bot.send_message(chat_id=CHAT_ID, text=message)
        logger.info("Уведомление отправлено в Telegram")
    except Exception as e:
        logger.error(f"Ошибка отправки: {e}")

# === Основная логика ===
async def main():
    logger.info("Запуск проверки цен...")
    if not TELEGRAM_TOKEN or not CHAT_ID:
        logger.error("TELEGRAM_TOKEN или CHAT_ID не заданы!")
        return

    bot = Bot(token=TELEGRAM_TOKEN)
    state = load_state()

    now_utc = datetime.now(timezone.utc)
    now_minsk = now_utc.astimezone(MINSK_TZ)
    today_minsk = now_minsk.strftime('%Y-%m-%d')
    is_report_time = now_minsk.hour == 10 and 25 <= now_minsk.minute <= 35

    price = get_min_price()
    if not price:
        return

    # === Первый запуск ===
    if 'first_run' not in state:
        await send_telegram(
            bot,
            f"Мониторинг запущен!\n"
            f"Текущая минимальная цена: {price} BYN\n"
            f"Ежедневный отчёт: 10:30 по Минску\n"
            f"Уведомление при цене < {TARGET_PRICE} BYN\n"
            f"{OZON_URL}"
        )
        state['first_run'] = True
        state['daily_min'] = price
        state['last_report_date'] = today_minsk
        save_state(state)
        return

    # === Обновление минимума ===
    daily_min = state.get('daily_min', price)
    last_report_date = state.get('last_report_date', today_minsk)

    if price < daily_min:
        daily_min = price

    # === Уведомление при снижении ===
    if price < TARGET_PRICE:
        await send_telegram(
            bot,
            f"ЦЕНА НИЖЕ {TARGET_PRICE} BYN!\n"
            f"Сейчас: {price} BYN\n"
            f"{OZON_URL}"
        )

    # === Ежедневный отчёт в 10:30 по Минску ===
    if is_report_time and last_report_date != today_minsk:
        await send_telegram(
            bot,
            f"Ежедневный отчёт за {last_report_date}\n"
            f"Минимальная цена за день: {daily_min} BYN\n"
            f"Время: {now_minsk.strftime('%H:%M')} по Минску\n"
            f"{OZON_URL}"
        )
        daily_min = price
        last_report_date = today_minsk

    # === Сохранение ===
    state['daily_min'] = daily_min
    state['last_report_date'] = last_report_date
    save_state(state)

# === Запуск ===
if __name__ == "__main__":
    asyncio.run(main())