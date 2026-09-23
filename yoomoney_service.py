import requests
from urllib.parse import urlencode
from config import YOOMONEY_RECEIVER, YOOMONEY_TOKEN


def create_payment_link(user_id: int, amount: float, label: str) -> str:
    """Генерирует ссылку на форму оплаты YooMoney."""
    params = {
        "receiver": YOOMONEY_RECEIVER,
        "quickpay-form": "shop",
        "targets": f"Оплата подписки (user {user_id})",
        "paymentType": "AC",
        "sum": f"{amount:.2f}",
        "label": label,
    }
    return "https://yoomoney.ru/quickpay/confirm.xml?" + urlencode(params)


def make_refund(to_wallet: str, amount: float, comment: str) -> dict:
    """
    Возврат через YooMoney Wallet API.
    Двухшаговый процесс: request-payment → process-payment.
    """
    headers = {"Authorization": f"Bearer {YOOMONEY_TOKEN}"}

    # Шаг 1: request-payment
    try:
        r1 = requests.post(
            "https://yoomoney.ru/api/request-payment",
            headers=headers,
            data={
                "pattern_id": "p2p",
                "to": to_wallet,
                "amount": f"{amount:.2f}",
                "comment": comment,
                "message": comment,
            },
            timeout=30,
        )
    except Exception as e:
        return {"success": False, "operation_id": None, "error": f"Сеть: {e}"}

    if r1.status_code != 200:
        return {"success": False, "operation_id": None, "error": f"HTTP {r1.status_code}: {r1.text}"}

    data1 = r1.json()
    if data1.get("status") != "success":
        return {"success": False, "operation_id": None,
                "error": data1.get("error", "Ошибка request-payment")}

    request_id = data1.get("request_id")

    # Шаг 2: process-payment
    try:
        r2 = requests.post(
            "https://yoomoney.ru/api/process-payment",
            headers=headers,
            data={"request_id": request_id},
            timeout=30,
        )
    except Exception as e:
        return {"success": False, "operation_id": None, "error": f"Сеть: {e}"}

    if r2.status_code != 200:
        return {"success": False, "operation_id": None, "error": f"HTTP {r2.status_code}: {r2.text}"}

    data2 = r2.json()
    if data2.get("status") != "success":
        return {"success": False, "operation_id": None,
                "error": data2.get("error", "Ошибка process-payment")}

    return {"success": True, "operation_id": data2.get("operation_id"), "error": None}