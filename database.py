import psycopg
from psycopg.rows import dict_row
from contextlib import contextmanager
from datetime import datetime
from config import DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT

DB_CONFIG = {
    "dbname": DB_NAME,
    "user": DB_USER,
    "password": DB_PASSWORD,
    "host": DB_HOST,
    "port": DB_PORT,
}


@contextmanager
def db(commit=True):
    # Открывает соединение, отдаёт курсор, коммитит и закрывает
    conn = psycopg.connect(**DB_CONFIG, row_factory=dict_row)
    cur = conn.cursor()
    try:
        yield cur
        if commit:
            conn.commit()
    finally:
        cur.close()
        conn.close()


def init_db():
    # Создаёт таблицу payments и индексы, если их ещё нет
    with db() as cur:
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
                next_payment_at TIMESTAMP,
                retry_count INTEGER DEFAULT 0,
                is_recurrent BOOLEAN DEFAULT FALSE,
                refunded_at TIMESTAMP,
                refund_operation_id TEXT
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_label ON payments(label)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_next ON payments(next_payment_at)")


def create_payment(user_id: int, label: str, amount: float):
    # Создаёт новую запись о платеже со статусом pending
    with db() as cur:
        cur.execute(
            "INSERT INTO payments (user_id, label, amount) VALUES ($1, $2, $3)",
            (user_id, label, amount),
        )


def get_payment_by_label(label: str):
    # Возвращает платёж по метке или None
    with db(commit=False) as cur:
        cur.execute("SELECT * FROM payments WHERE label = $1", (label,))
        return cur.fetchone()


def mark_payment_success(label: str, operation_id: str, sender: str = None):
    # Отмечает платёж как успешный и сохраняет operation_id и sender
    with db() as cur:
        cur.execute(
            "UPDATE payments SET status='success', operation_id=$1, sender=$2, paid_at=$3 WHERE label=$4",
            (operation_id, sender, datetime.now(), label),
        )


def get_user_payments(user_id: int, limit: int = 5):
    # Возвращает последние платежи пользователя
    with db(commit=False) as cur:
        cur.execute(
            "SELECT label, amount, status, created_at FROM payments WHERE user_id=$1 ORDER BY id DESC LIMIT $2",
            (user_id, limit),
        )
        return cur.fetchall()


def set_recurrent(label: str, next_payment_at: datetime):
    # Помечает платёж как подписку и задаёт дату следующего списания
    with db() as cur:
        cur.execute(
            "UPDATE payments SET next_payment_at=$1, is_recurrent=TRUE WHERE label=$2",
            (next_payment_at, label),
        )


def get_payments_due_for_retry():
    # Возвращает подписки, у которых наступил срок напоминания
    with db(commit=False) as cur:
        cur.execute("""
            SELECT user_id, label, amount, retry_count
            FROM payments
            WHERE is_recurrent=TRUE AND next_payment_at<=NOW() AND status='success'
        """)
        return cur.fetchall()


def increment_retry(label: str, next_attempt: datetime):
    # Увеличивает счётчик попыток и назначает новую дату
    with db() as cur:
        cur.execute(
            "UPDATE payments SET retry_count=retry_count+1, next_payment_at=$1 WHERE label=$2",
            (next_attempt, label),
        )


def mark_recurrent_failed(label: str):
    # Помечает подписку как проваленную после всех попыток
    with db() as cur:
        cur.execute(
            "UPDATE payments SET is_recurrent=FALSE, status='recurrent_failed' WHERE label=$1",
            (label,),
        )


def mark_payment_refunded(label: str, refund_operation_id: str):
    # Отмечает платёж как возвращённый
    with db() as cur:
        cur.execute(
            "UPDATE payments SET status='refunded', refund_operation_id=$1, refunded_at=$2 WHERE label=$3",
            (refund_operation_id, datetime.now(), label),
        )


def get_last_successful_payment(user_id: int):
    # Возвращает последний успешный невозвращённый платёж пользователя
    with db(commit=False) as cur:
        cur.execute("""
            SELECT label, amount, operation_id, sender, paid_at
            FROM payments
            WHERE user_id=$1 AND status='success' AND refunded_at IS NULL
            ORDER BY id DESC LIMIT 1
        """, (user_id,))
        return cur.fetchone()


init_db()