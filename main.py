import os
import requests
from bs4 import BeautifulSoup
import logging
from telegram import Update, Bot
from telegram.ext import Updater, CommandHandler, CallbackContext
import schedule
import time
import threading
import json
from flask import Flask
from threading import Thread
from dotenv import load_dotenv

load_dotenv()  # load biến môi trường từ .env nếu có

BOT_TOKEN = os.getenv("BOT_TOKEN")  # Lấy token từ biến môi trường

if not BOT_TOKEN:
    raise ValueError("Bạn chưa cấu hình biến môi trường BOT_TOKEN!")

subscribers = set()

def load_subscribers():
    global subscribers
    try:
        with open("subscribers.json", "r") as f:
            data = json.load(f)
            subscribers.update(data)
    except FileNotFoundError:
        pass

def save_subscribers():
    with open("subscribers.json", "w") as f:
        json.dump(list(subscribers), f)

def get_btc_price():
    url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"
    try:
        response = requests.get(url)
        data = response.json()
        price = data.get("bitcoin", {}).get("usd")
        return price
    except Exception as e:
        print("Lỗi lấy giá BTC:", e)
        return None

def get_followin_news():
    url = "https://followin.io/"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            return "Không lấy được tin từ followin.io"
        soup = BeautifulSoup(response.text, "html.parser")

        articles = soup.find_all("article", limit=5)
        news_list = []
        for art in articles:
            title_tag = art.find("h2") or art.find("h3") or art.find("a")
            if not title_tag:
                continue
            title = title_tag.get_text(strip=True)
            link_tag = art.find("a", href=True)
            link = link_tag['href'] if link_tag else url
            if link and not link.startswith("http"):
                link = "https://followin.io" + link
            news_list.append(f"🔹 {title}\n{link}")

        return "\n\n".join(news_list) if news_list else "Không tìm thấy tin mới"
    except Exception as e:
        print("Lỗi lấy tin followin.io:", e)
        return "Lỗi khi lấy tin tức."

def get_latest_news():
    return get_followin_news()

def get_top_gainers(hours=1, limit=5):
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {
        "vs_currency": "usd",
        "order": "market_cap_desc",
        "per_page": 100,
        "page": 1,
        "price_change_percentage": "1h,2h,24h"
    }
    try:
        res = requests.get(url, params=params).json()
    except Exception as e:
        return f"Lỗi lấy dữ liệu coin: {e}"

    time_map = {
        1: "price_change_percentage_1h_in_currency",
        2: "price_change_percentage_2h_in_currency",
        24: "price_change_percentage_24h_in_currency"
    }
    key = time_map.get(hours, "price_change_percentage_1h_in_currency")

    filtered = [c for c in res if c.get(key) is not None]
    sorted_coins = sorted(filtered, key=lambda x: x[key], reverse=True)
    top = sorted_coins[:limit]

    lines = [f"Top {limit} coin tăng mạnh trong {hours}h:"]
    for coin in top:
        lines.append(f"{coin['name']} ({coin['symbol'].upper()}): {coin[key]:.2f}%")
    return "\n".join(lines)

def get_top_losers(hours=1, limit=5):
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {
        "vs_currency": "usd",
        "order": "market_cap_desc",
        "per_page": 100,
        "page": 1,
        "price_change_percentage": "1h,2h,24h"
    }
    try:
        res = requests.get(url, params=params).json()
    except Exception as e:
        return f"Lỗi lấy dữ liệu coin: {e}"

    time_map = {
        1: "price_change_percentage_1h_in_currency",
        2: "price_change_percentage_2h_in_currency",
        24: "price_change_percentage_24h_in_currency"
    }
    key = time_map.get(hours, "price_change_percentage_1h_in_currency")

    filtered = [c for c in res if c.get(key) is not None]
    sorted_coins = sorted(filtered, key=lambda x: x[key])
    top = sorted_coins[:limit]

    lines = [f"Top {limit} coin giảm mạnh trong {hours}h:"]
    for coin in top:
        lines.append(f"{coin['name']} ({coin['symbol'].upper()}): {coin[key]:.2f}%")
    return "\n".join(lines)

def start(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    if chat_id not in subscribers:
        subscribers.add(chat_id)
        save_subscribers()
    update.message.reply_text("Bạn đã đăng ký nhận cảnh báo biến động coin và tin tức crypto.")

def stop(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    if chat_id in subscribers:
        subscribers.remove(chat_id)
        save_subscribers()
    update.message.reply_text("Bạn đã hủy đăng ký nhận cảnh báo.")

def checklong(update: Update, context: CallbackContext):
    msg = ""
    for h in [1, 2, 24]:
        msg += get_top_gainers(hours=h) + "\n\n"
    update.message.reply_text(msg.strip())

def checkshort(update: Update, context: CallbackContext):
    msg = ""
    for h in [1, 2, 24]:
        msg += get_top_losers(hours=h) + "\n\n"
    update.message.reply_text(msg.strip())

def checknews(update: Update, context: CallbackContext):
    news = get_latest_news()
    update.message.reply_text(news)

def send_alerts(bot: Bot):
    price = get_btc_price()
    news = get_latest_news()
    if price is None:
        price_text = "Không lấy được giá Bitcoin."
    else:
        price_text = f"Cập nhật giá Bitcoin hiện tại: ${price}"
    message = f"⚡ {price_text}\n\n📰 Tin tức mới nhất từ followin.io:\n\n{news}"

    for chat_id in subscribers:
        try:
            bot.send_message(chat_id=chat_id, text=message)
        except Exception as e:
            print(f"Không gửi được cho {chat_id}: {e}")

def run_schedule(updater: Updater):
    def job():
        send_alerts(updater.bot)
    schedule.every(1).hour.do(job)

    while True:
        schedule.run_pending()
        time.sleep(1)

app = Flask('')

@app.route('/')
def home():
    return "Bot is alive"

def run_web():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run_web)
    t.start()

def main():
    logging.basicConfig(level=logging.INFO)
    load_subscribers()
    keep_alive()

    updater = Updater(BOT_TOKEN, use_context=True)

    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("stop", stop))
    dp.add_handler(CommandHandler("checklong", checklong))
    dp.add_handler(CommandHandler("checkshort", checkshort))
    dp.add_handler(CommandHandler("checknews", checknews))

    updater.start_polling()

    thread = threading.Thread(target=run_schedule, args=(updater,), daemon=True)
    thread.start()

    updater.idle()

if __name__ == "__main__":
    main()
