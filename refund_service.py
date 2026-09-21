import requests
from config import YOOMONEY_TOKEN


def make_refund(to_wallet: str, amount: float, comment: str) -> dict:
    headers = {"Authorization": f"Bearer {YOOMONEY_TOKEN}"}

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
        return {
            "success": False,
            "operation_id": None,
            "error": data1.get("error", "Неизвестная ошибка на шаге request-payment"),
        }

    request_id = data1.get("request_id")

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
        return {
            "success": False,
            "operation_id": None,
            "error": data2.get("error", "Неизвестная ошибка на шаге process-payment"),
        }

    return {
        "success": True,
        "operation_id": data2.get("operation_id"),
        "error": None,
    }