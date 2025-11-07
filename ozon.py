#!/usr/bin/env python3
import os
import time
import logging
import json
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from telegram import Bot
import asyncio

# === ПОДАВЛЕНИЕ ПРЕДУПРЕЖДЕНИЯ urllib3 (macOS) ===
import warnings
from urllib3.exceptions import NotOpenSSLWarning

warnings.filterwarnings('ignore', category=NotOpenSSLWarning)

# === НАСТРОЙКИ ===
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN', '8531859495:AAHZusQJdMslQ3nQ7yCI1jcBkUwKp9g_nsk')
CHAT_ID = os.getenv('CHAT_ID', '789161700')
OZON_URL = 'https://ozon.by/category/televizory-15528/?category_was_predicted=true&deny_category_prediction=true&from_global=true&rsdiagonalstr=24.000%3B109.000&sorting=price&text=телевизор&__rr=1'
TARGET_PRICE = 190.0
DATA_FILE = 'ozon_monitor.json'  # Локальный файл

# Минск = UTC+3
MINSK_TZ = timezone(timedelta(hours=3))

# Логирование
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# === Состояние ===
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


# === Парсинг Ozon ===
def get_min_price(url):
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument(
        '--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36')
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)

    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => false});")

        logger.info("Открываем Ozon через Selenium...")
        driver.get(url)
        time.sleep(12)  # Ozon грузится медленно

        soup = BeautifulSoup(driver.page_source, 'html.parser')
        driver.quit()

        price_spans = soup.find_all('span', class_='tsHeadline500Medium')
        if not price_spans:
            logger.warning("Цены не найдены")
            return None

        prices = []
        for span in price_spans:
            price_text = span.get_text(strip=True)
            price_str = price_text.replace('BYN', '').replace(' ', '').replace(',', '.').strip()
            try:
                price = float(price_str)
                prices.append(price)
            except:
                continue

        if not prices:
            return None

        min_price = min(prices)
        logger.info(f"Минимальная цена: {min_price} BYN")
        return {'price': min_price, 'link': url}

    except Exception as e:
        logger.error(f"Ошибка Selenium: {e}")
        if 'driver' in locals():
            driver.quit()
        return None


# === Telegram ===
async def send_telegram(bot: Bot, message: str):
    try:
        await bot.send_message(chat_id=CHAT_ID, text=message)
        logger.info("Уведомление отправлено в Telegram")
    except Exception as e:
        logger.error(f"Ошибка отправки: {e}")


# === Основной запуск ===
async def main():
    logger.info("Запуск проверки цен Ozon...")

    if not TELEGRAM_TOKEN or not CHAT_ID:
        logger.error("TELEGRAM_TOKEN или CHAT_ID не заданы!")
        return

    bot = Bot(token=TELEGRAM_TOKEN)
    state = load_state()

    now_utc = datetime.now(timezone.utc)
    now_minsk = now_utc.astimezone(MINSK_TZ)
    today_minsk = now_minsk.strftime('%Y-%m-%d')
    is_report_time = now_minsk.hour == 10 and 25 <= now_minsk.minute <= 35

    result = get_min_price(OZON_URL)
    if not result:
        return

    price = result['price']

    # === Первый запуск ===
    if 'first_run' not in state:
        await send_telegram(
            bot,
            f"Мониторинг запущен!\n"
            f"Текущая минимальная цена: {price} BYN\n"
            f"Отчёт каждый день в 10:30 по Минску\n"
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
            f"Проверено в {now_minsk.strftime('%H:%M')} по Минску\n"
            f"{OZON_URL}"
        )
        daily_min = price
        last_report_date = today_minsk

    # === Сохранение ===
    state['daily_min'] = daily_min
    state['last_report_date'] = last_report_date
    save_state(state)


# === ЗАПУСК ===
if __name__ == "__main__":
    asyncio.run(main())