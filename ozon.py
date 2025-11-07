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

# === Состояние ===
def load_state():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_state(state):
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except:
        pass

# === Chrome без прокси + антибот ===
def get_chrome_options():
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    return options

# === Получение цены ===
def get_min_price():
    try:
        driver = webdriver.Chrome(options=get_chrome_options())
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => false});")
        logger.info("Открываем Ozon...")
        driver.get(OZON_URL)
        time.sleep(15)

        soup = BeautifulSoup(driver.page_source, 'html.parser')
        driver.quit()

        if "ozon.by" not in soup.text:
            logger.warning("Страница не загрузилась")
            return None

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

# === Telegram ===
async def send_telegram(bot: Bot, message: str):
    try:
        await bot.send_message(chat_id=CHAT_ID, text=message)
        logger.info("Уведомление отправлено")
    except Exception as e:
        logger.error(f"Ошибка отправки: {e}")

# === Основной код ===
async def main():
    logger.info("Запуск проверки...")
    if not TELEGRAM_TOKEN or not CHAT_ID:
        logger.error("Secrets не заданы!")
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
        await send_telegram(bot, f"Мониторинг запущен!\nЦена: {price} BYN\nБез прокси\n{OZON_URL}")
        state['first_run'] = True
        state['daily_min'] = price
        state['last_report_date'] = today_minsk
        save_state(state)
        return

    # === Логика ===
    daily_min = state.get('daily_min', price)
    last_report_date = state.get('last_report_date', today_minsk)

    if price < daily_min:
        daily_min = price

    if price < TARGET_PRICE:
        await send_telegram(bot, f"ЦЕНА НИЖЕ {TARGET_PRICE}!\nСейчас: {price} BYN\n{OZON_URL}")

    if is_report_time and last_report_date != today_minsk:
        await send_telegram(bot, f"Отчёт за {last_report_date}\nМин: {daily_min} BYN\n{OZON_URL}")
        daily_min = price
        last_report_date = today_minsk

    state['daily_min'] = daily_min
    state['last_report_date'] = last_report_date
    save_state(state)

if __name__ == "__main__":
    asyncio.run(main())