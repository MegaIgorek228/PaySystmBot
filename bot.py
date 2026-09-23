import asyncio
import uuid
import requests
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from config import BOT_TOKEN, YOOMONEY_TOKEN
from yoomoney_service import create_payment_link, make_refund
from database import (
    create_payment, get_user_payments, set_recurrent,
    get_payments_due_for_retry, increment_retry, mark_recurrent_failed,
    get_last_successful_payment, mark_payment_refunded,
)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler()
MAX_RETRIES = 2


# Telegram API
def send_telegram_message(chat_id: int, text: str):
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=10,
        )
    except Exception as e:
        print(f"Ошибка отправки в Telegram: {e}")


# Напоминание
async def check_due_payments():
    print(f"[{datetime.now()}] Проверка рекуррентных платежей...")
    due = get_payments_due_for_retry()
    print(f"Найдено {len(due)} к обработке")

    for p in due:
        user_id, label = p["user_id"], p["label"]
        amount, retry_count = p["amount"], p["retry_count"]

        if retry_count >= MAX_RETRIES:
            mark_recurrent_failed(label)
            send_telegram_message(user_id,
                                  f"Не удалось списать {amount} ₽\n\nЗаказ: <code>{label}</code>\nПричина: пользователь не оплатил после {MAX_RETRIES} попыток.\nПодписка приостановлена. Используйте /pay для возобновления.")
        else:
            link = create_payment_link(user_id, float(amount), f"{label}_retry{retry_count + 1}")
            next_attempt = datetime.now() + timedelta(minutes=2)  # для теста; в проде days=1
            increment_retry(label, next_attempt)
            send_telegram_message(user_id,
                                  f"Напоминание об оплате\n\nСумма: {amount} ₽\nПопытка: {retry_count + 1} из {MAX_RETRIES}\n\nОплатить: {link}\n\nЕсли не оплатить — подписка будет приостановлена.")


def start_scheduler():
    scheduler.add_job(
        check_due_payments,
        trigger=IntervalTrigger(minutes=1),
        id="check_due",
        replace_existing=True,
    )
    scheduler.start()
    print("Планировщик запущен")


# Команды
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "Это бот для оплаты.\n\nКоманды:\n/pay — разовый платёж\n/subscribe — оформить подписку\n/refund — вернуть последний платёж\n/status — последние платежи"
    )


@dp.message(Command("pay"))
async def cmd_pay(message: types.Message):
    user_id = message.from_user.id
    amount = 2.00
    label = f"order_{user_id}_{uuid.uuid4().hex[:8]}"

    create_payment(user_id, label, amount)
    link = create_payment_link(user_id, amount, label)

    await message.answer(f"Ссылка на оплату {amount:.2f} ₽:\n{link}")


@dp.message(Command("subscribe"))
async def cmd_subscribe(message: types.Message):
    user_id = message.from_user.id
    amount = 2.00
    label = f"sub_{user_id}_{uuid.uuid4().hex[:8]}"

    create_payment(user_id, label, amount)
    next_payment = datetime.now() + timedelta(minutes=1)
    set_recurrent(label, next_payment)

    link = create_payment_link(user_id, amount, label)
    await message.answer(
        f"Оформление подписки\n\nСумма: {amount:.2f} ₽\nСледующее списание: {next_payment.strftime('%d.%m.%Y %H:%M')}\n\nОплатить: {link}")


@dp.message(Command("refund"))
async def cmd_refund(message: types.Message):
    user_id = message.from_user.id
    payment = get_last_successful_payment(user_id)

    if not payment:
        await message.answer("У вас нет успешных платежей для возврата.")
        return

    sender = payment.get("sender")
    if not sender:
        await message.answer(
            "Невозможно вернуть автоматически.\nПлатёж был сделан с карты — возврат только через личный кабинет YooMoney.")
        return

    amount = float(payment["amount"])
    label = payment["label"]

    await message.answer(f"Инициирую возврат {amount:.2f} ₽ на {sender}...")

    result = make_refund(sender, amount, f"Возврат по заказу {label}")

    if result["success"]:
        mark_payment_refunded(label, result["operation_id"])
        await message.answer(
            f" Возврат выполнен!\n\n"
            f"Сумма: {amount:.2f} ₽\n"
            f"Куда: <code>{sender}</code>\n"
            f"Операция: <code>{result['operation_id']}</code>"
        )
    else:
        await message.answer(f"Возврат не удался: {result['error']}")


@dp.message(Command("status"))
async def cmd_status(message: types.Message):
    payments = get_user_payments(message.from_user.id)
    if not payments:
        await message.answer("У вас нет платежей.")
        return

    text = "Ваши последние платежи:\n\n"
    for p in payments:
        text += f"{p['amount']} ₽ — {p['status']} ({p['created_at']})\n"
    await message.answer(text)


# Запуск
async def main():
    start_scheduler()
    print("Бот запущен...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
