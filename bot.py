import asyncio
import uuid
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from config import BOT_TOKEN, YOOMONEY_TOKEN
from payment_service import create_payment_link
from database import create_payment, get_user_payments, set_recurrent
from scheduler import start_scheduler
from database import get_last_successful_payment, mark_payment_refunded
from refund_service import make_refund

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "Привет! Я бот для оплаты.\n\n"
        "Команды:\n"
        "/pay — разовый платёж\n"
        "/subscribe — оформить подписку\n"
        "/status — последние платежи\n"
        "/test_token — проверить токен YooMoney"
        "/refund — вернуть последний платёж\n"
    )


@dp.message(Command("pay"))
async def cmd_pay(message: types.Message):
    user_id = message.from_user.id
    amount = 2.00
    label = f"order_{user_id}_{uuid.uuid4().hex[:8]}"
    create_payment(user_id, label, amount)
    link = create_payment_link(user_id, amount, label)
    await message.answer(
        f"Ссылка на оплату {amount:.2f} ₽:\n{link}\n\n"
        f"После оплаты я пришлю уведомление."
    )


@dp.message(Command("subscribe"))
async def cmd_subscribe(message: types.Message):
    """Оформление подписки — рекуррентный платёж."""
    user_id = message.from_user.id
    amount = 2.00
    label = f"sub_{user_id}_{uuid.uuid4().hex[:8]}"
    create_payment(user_id, label, amount)

    # Помечаем как рекуррентный — следующее списание через 1 день (для теста)
    # В реальности: через 30 дней
    next_payment = datetime.now() + timedelta(minutes=1)
    set_recurrent(label, next_payment, is_recurrent=True)

    link = create_payment_link(user_id, amount, label)
    await message.answer(
        f"<h>Оформление подписки</h>\n\n"
        f"Сумма: {amount:.2f} ₽\n"
        f"Следующее списание: {next_payment.strftime('%d.%m.%Y %H:%M')}\n\n"
        f"Оплатить: {link}\n\n"
        f"Если не оплатить вовремя — напомню через день."
    )


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
            "Невозможно сделать автоматический возврат.\n\n"
            "Ваш платёж был сделан с карты (card-incoming), "
            "а не с кошелька YooMoney. Возврат на карту делается "
            "только через личный кабинет YooMoney."
        )
        return

    amount = float(payment["amount"])
    label = payment["label"]

    await message.answer(
        f"↩Инициирую возврат {amount:.2f} ₽ на кошелёк {sender}..."
    )

    result = make_refund(sender, amount, f"Возврат по заказу {label}")

    if result["success"]:
        mark_payment_refunded(label, result["operation_id"])
        await message.answer(
            f"<b>Возврат выполнен!</b>\n\n"
            f"Сумма: {amount:.2f} ₽\n"
            f"Куда: <code>{sender}</code>\n"
            f"Операция: <code>{result['operation_id']}</code>"
        )
    else:
        await message.answer(
            f"<b>Возврат не удался</b>\n\n"
            f"Причина: {result['error']}"
        )


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


@dp.message(Command("test_token"))
async def cmd_test_token(message: types.Message):
    import requests
    try:
        response = requests.get(
            "https://yoomoney.ru/api/account-info",
            headers={"Authorization": f"Bearer {YOOMONEY_TOKEN}"},
            timeout=30,
        )
        if response.status_code == 200:
            data = response.json()
            await message.answer(
                f"Токен работает!\nКошелёк: {data.get('account')}\n"
                f"Баланс: {data.get('balance')} ₽"
            )
        else:
            await message.answer(f"Статус {response.status_code}: {response.text}")
    except Exception as e:
        await message.answer(f"Ошибка: {type(e).__name__}: {e}")


async def main():
    start_scheduler()  # ← Запускаем планировщик
    print("Бот запущен...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
