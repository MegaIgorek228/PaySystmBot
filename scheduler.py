from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime, timedelta
import requests
from config import BOT_TOKEN
from database import (get_payments_due_for_retry, increment_retry, mark_recurrent_failed)
from bot import create_payment_link

scheduler = AsyncIOScheduler()
MAX_RETRIES = 2


def send_telegram_message(chat_id: int, text: str):
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=10,
        )
    except Exception as e:
        print(f"Не удалось отправить сообщение: {e}")


async def check_due_payments():
    print(f"[{datetime.now()}] Проверка рекуррентных платежей...")

    due_payments = get_payments_due_for_retry()
    print(f"Найдено {len(due_payments)} платежей к обработке")

    for payment in due_payments:
        user_id = payment["user_id"]
        label = payment["label"]
        amount = payment["amount"]
        retry_count = payment["retry_count"]

        if retry_count >= MAX_RETRIES:
            mark_recurrent_failed(label)
            send_telegram_message(
                user_id,
                f"Не удалось списать {amount} ₽\n\n"
                f"Заказ: {label}\n"
                f"Причина: пользователь не оплатил после {MAX_RETRIES} попыток.\n\n"
                f"Подписка приостановлена. Используйте /pay для возобновления.",
            )
            print(f"Рекуррентный платёж {label} помечен как проваленный")
        else:
            link = create_payment_link(user_id, float(amount), f"{label}_retry{retry_count + 1}")

            next_attempt = datetime.now() + timedelta(days=1)
            increment_retry(label, next_attempt)

            send_telegram_message(
                user_id,
                f"Напоминание об оплате\n\n"
                f"Сумма: {amount} ₽\n"
                f"Попытка: {retry_count + 1} из {MAX_RETRIES}\n\n"
                f"Оплатить: {link}\n\n"
                f"Если не оплатить в течение суток, подписка будет приостановлена.",
            )
            print(f"Отправлено напоминание пользователю {user_id}")


def start_scheduler():
    scheduler.add_job(
        check_due_payments,
        trigger=IntervalTrigger(minutes=1),
        id="check_due_payments",
        replace_existing=True,
    )
    scheduler.start()
    print("Планировщик запущен")
