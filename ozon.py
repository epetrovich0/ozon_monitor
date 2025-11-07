#!/usr/bin/env python3
import time
import logging
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from telegram import Bot

# === НАСТРОЙКИ ===
TELEGRAM_TOKEN = '8531859495:AAHZusQJdMslQ3nQ7yCI1jcBkUwKp9g_nsk'
CHAT_ID = '789161700'
OZON_URL = 'https://ozon.by/category/televizory-15528/?category_was_predicted=true&deny_category_prediction=true&from_global=true&rsdiagonalstr=24.000%3B109.000&sorting=price&text=телевизор&__rr=1'
TARGET_PRICE = 190.0
CHECK_INTERVAL_MIN = 30

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
bot = Bot(token=TELEGRAM_TOKEN)

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
            return None

        min_price = min(prices)
        logger.info(f"Минимальная цена: {min_price} BYN")
        return min_price

    except Exception as e:
        logger.error(f"Ошибка: {e}")
        if 'driver' in locals():
            driver.quit()
        return None

def main():
    logger.info("Запуск мониторинга на Render.com")
    while True:
        price = get_min_price()
        if price and price < TARGET_PRICE:
            bot.send_message(
                chat_id=CHAT_ID,
                text=f"ЦЕНА НИЖЕ {TARGET_PRICE} BYN!\nСейчас: {price} BYN\n{OZON_URL}"
            )
        time.sleep(CHECK_INTERVAL_MIN * 60)

if __name__ == "__main__":
    main()