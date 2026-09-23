import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
from config import DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT

DB_CONFIG = {
    "dbname": DB_NAME,
    "user": DB_USER,
    "password": DB_PASSWORD,
    "host": DB_HOST,
    "port": DB_PORT,
}



def get_conn():
    return psycopg2.connect(**DB_CONFIG)


def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            label TEXT UNIQUE NOT NULL,
            amount NUMERIC(10, 2) NOT NULL,
            status TEXT DEFAULT 'pending',
            operation_id TEXT,
            sender TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            paid_at TIMESTAMP,
            recurrent_token TEXT,
            next_payment_at TIMESTAMP,
            retry_count INTEGER DEFAULT 0,
            is_recurrent BOOLEAN DEFAULT FALSE,
            refunded_at TIMESTAMP,
            refund_operation_id TEXT
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_label ON payments(label)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_next_payment ON payments(next_payment_at)")
    conn.commit()
    cur.close()
    conn.close()


def create_payment(user_id: int, label: str, amount: float):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO payments (user_id, label, amount) VALUES (%s, %s, %s)",
        (user_id, label, amount),
    )
    conn.commit()
    cur.close()
    conn.close()


def get_payment_by_label(label: str) -> dict | None:
    conn = get_conn()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute(
        "SELECT user_id, label, amount, status, operation_id FROM payments WHERE label = %s",
        (label,),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    return dict(row) if row else None


def mark_payment_success(label: str, operation_id: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE payments SET status = 'success', operation_id = %s, paid_at = %s WHERE label = %s",
        (operation_id, datetime.now(), label),
    )
    conn.commit()
    cur.close()
    conn.close()


def get_user_payments(user_id: int, limit: int = 5) -> list[dict]:
    conn = get_conn()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute(
        "SELECT label, amount, status, created_at FROM payments WHERE user_id = %s ORDER BY id DESC LIMIT %s",
        (user_id, limit),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(r) for r in rows]


def set_recurrent(label: str, next_payment_at: datetime, is_recurrent: bool = True):
    # Помечает платёж как рекуррентный и назначает дату следующего списания
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE payments SET next_payment_at = %s, is_recurrent = %s WHERE label = %s",
        (next_payment_at, is_recurrent, label),
    )
    conn.commit()
    cur.close()
    conn.close()


def get_payments_due_for_retry() -> list[dict]:
    # Возвращает платежи, у которых наступила дата следующего списания
    conn = get_conn()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT user_id, label, amount, retry_count, is_recurrent
        FROM payments
        WHERE is_recurrent = TRUE
          AND next_payment_at <= NOW()
          AND status = 'success'
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(r) for r in rows]


def increment_retry(label: str, next_attempt: datetime):
    # Увеличивает счётчик попыток и назначает новую дату
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE payments SET retry_count = retry_count + 1, next_payment_at = %s WHERE label = %s",
        (next_attempt, label),
    )
    conn.commit()
    cur.close()
    conn.close()


def mark_recurrent_failed(label: str):
    # Помечает рекуррентный платёж как проваленный после всех попыток
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE payments SET is_recurrent = FALSE, status = 'recurrent_failed' WHERE label = %s",
        (label,),
    )
    conn.commit()
    cur.close()
    conn.close()


def mark_payment_success(label: str, operation_id: str, sender: str = None):
    # Отмечает платёж как успешный + сохраняет отправителя
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE payments SET status = 'success', operation_id = %s, sender = %s, paid_at = %s WHERE label = %s",
        (operation_id, sender, datetime.now(), label),
    )
    conn.commit()
    cur.close()
    conn.close()


def mark_payment_refunded(label: str, refund_operation_id: str):
    # Помечает платёж как возвращённый
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE payments SET status = 'refunded', refund_operation_id = %s, refunded_at = %s WHERE label = %s",
        (refund_operation_id, datetime.now(), label),
    )
    conn.commit()
    cur.close()
    conn.close()


def get_last_successful_payment(user_id: int) -> dict | None:
    # Возвращает последний успешный платёж пользователя, который ещё не возвращён
    conn = get_conn()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT label, amount, operation_id, sender, paid_at
        FROM payments
        WHERE user_id = %s 
          AND status = 'success'
          AND refunded_at IS NULL
        ORDER BY id DESC
        LIMIT 1
    """, (user_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return dict(row) if row else None


init_db()
