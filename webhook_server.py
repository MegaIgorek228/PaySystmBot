import hashlib
import hmac
from urllib.parse import quote
import requests as req
from flask import Flask, request
from config import BOT_TOKEN, YOOMONEY_NOTIFICATION_SECRET
from database import get_payment_by_label, mark_payment_success

app = Flask(__name__)


def check_signature(data: dict) -> bool:
    if data.get("test_notification") == "true":
        return True

    params = {k: v for k, v in data.items() if k != "sign"}
    sign_string = "&".join(
        f"{k}={quote(str(params[k]), safe='')}" for k in sorted(params.keys())
    )

    expected = hmac.new(
        YOOMONEY_NOTIFICATION_SECRET.encode(),
        sign_string.encode(),
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected, data.get("sign", ""))


def send_telegram_message(chat_id: int, text: str):
    try:
        r = req.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=10,
        )
        if r.status_code != 200:
            print(f"Telegram ответил: {r.status_code} {r.text}")
    except Exception as e:
        print(f"Не удалось отправить в Telegram: {e}")


@app.route("/yoomoney/notification", methods=["POST"])
def yoomoney_notification():
    data = request.form.to_dict()
    print("=== Получено уведомление от YooMoney ===")
    print(data)

    if not check_signature(data):
        print("НЕВЕРНАЯ ПОДПИСЬ")
        return "Invalid signature", 403

    if data.get("test_notification") == "true":
        print("Тестовое уведомление — пропускаем.")
        return "OK", 200

    amount = float(data.get("amount", 0))
    label = data.get("label", "")
    operation_id = data.get("operation_id", "")

    payment = get_payment_by_label(label)
    if not payment:
        print(f"!!! Платёж с label={label} не найден в БД")
        return "OK", 200

    sender = data.get("sender", "")
    mark_payment_success(label, operation_id, sender)

    user_id = payment["user_id"]
    send_telegram_message(
        user_id,
        f"Платёж получен!\n\n"
        f"Сумма: {amount} ₽\n"
        f"Заказ: {label}\n"
        f"Операция: {operation_id}",
    )

    print(f"Уведомление отправлено пользователю {user_id}")
    return "OK", 200


@app.route("/", methods=["GET"])
def index():
    return "All nice"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)