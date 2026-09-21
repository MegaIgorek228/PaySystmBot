from urllib.parse import urlencode
from config import YOOMONEY_RECEIVER


def create_payment_link(user_id: int, amount: float, label: str) -> str:
    # Генерирует ссылку на форму оплаты YooMoney без HTTP-запроса
    params = {
        "receiver": YOOMONEY_RECEIVER,
        "quickpay-form": "shop",
        "targets": f"Оплата подписки (user {user_id})",
        "paymentType": "AC",
        "sum": f"{amount:.2f}",
        "label": label,
    }
    return "https://yoomoney.ru/quickpay/confirm.xml?" + urlencode(params)