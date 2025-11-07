#!/usr/bin/env python3
import os
import time
import logging
import json
import requests
import random
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
PROXY_LIST_URL = "https://api.proxyscrape.com/v2/?request=getproxies&protocol=http&timeout=5000&country=BY,RU&ssl=yes&anonymity=elite"

# Минск = UTC+3
MINSK_TZ = timezone(timedelta(hours=3))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# === Кэш прокси ===
PROXY_CACHE = '/tmp/working_proxies.txt'
PROXY_CACHE_TIME = 3600  # 1 час


def load_working_proxies():
    if os.path.exists(PROXY_CACHE):
        age = time.time() - os.path.getmtime(PROXY_CACHE)
        if age < PROXY_CACHE_TIME:
            with open(PROXY_CACHE, 'r') as f:
                proxies = [line.strip() for line in f if line.strip()]
                random.shuffle(proxies)
                return proxies
    return []


def save_working_proxy(proxy):
    with open(PROXY_CACHE, 'w') as f:
        f.write(proxy + '\n')


def fetch_fresh_proxies():
    try:
        logger.info("Загружаем свежие прокси (BY/RU)...")
        response = requests.get(PROXY_LIST_URL, timeout=10)
        if response.status_code == 200:
            proxies = [f"http://{p.strip()}" for p in response.text.splitlines() if p.strip()]
            random.shuffle(proxies)
            with open(PROXY_CACHE, 'w') as f:
                f.write('\n'.join(proxies[:50]))
            return proxies
    except:
        logger.warning("Не удалось загрузить прокси")
    return []


def test_proxy(proxy):
    try:
        driver = webdriver.Chrome(options=get_chrome_options(proxy))
        driver.get("https://httpbin.org/ip")
        time.sleep(3)
        if proxy.split('@')[0].split('//')[1].split(':')[0] in driver.page_source:
            driver.quit()
            return True
        driver.quit()
    except:
        pass
    return False


def get_chrome_options(proxy=None):
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    if proxy:
        options.add_argument(f'--proxy-server={proxy}')
    return options


def get_working_proxy():
    proxies = load_working_proxies()
    if not proxies:
        proxies = fetch_fresh_proxies()

    for proxy in proxies[:10]:
        if test_proxy(proxy):
            logger.info(f"Рабочий прокси: {proxy}")
            save_working_proxy(proxy)
            return proxy

    logger.warning("Все прокси упали — ждём 5 мин")
    time.sleep(300)
    return get_working_proxy()


# === Остальное без изменений ===
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


def get_min_price():
    proxy = get_working_proxy()
    options = get_chrome_options(proxy)

    try:
        driver = webdriver.Chrome(options=options)
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => false});")
        logger.info(f"Открываем Ozon через {proxy}...")
        driver.get(OZON_URL)
        time.sleep(18)

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


async def send_telegram(bot: Bot, message: str):
    try:
        await bot.send_message(chat_id=CHAT_ID, text=message)
        logger.info("Уведомление отправлено")
    except Exception as e:
        logger.error(f"Ошибка: {e}")


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
        await send_telegram(bot, f"Мониторинг запущен!\nЦена: {price} BYN\nПрокси: авто\n{OZON_URL}")
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