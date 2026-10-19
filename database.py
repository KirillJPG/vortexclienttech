import aiosqlite
import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple, List, Dict, Any
from .config import DB_PATH, HWID_RESET_COOLDOWN_HOURS


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def format_dt(dt: Optional[datetime]) -> Optional[str]:
    return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else None


def parse_dt(dt_str: Optional[str]) -> Optional[datetime]:
    if not dt_str:
        return None
    try:
        return datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except Exception:
        return None


async def init_db():
    """Инициализация таблиц базы данных SQLite"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS keys (
                key TEXT PRIMARY KEY,
                duration_days INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                activated_at TEXT,
                expires_at TEXT,
                hwid TEXT,
                owner_id INTEGER,
                is_banned INTEGER DEFAULT 0,
                last_hwid_reset TEXT
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                registered_at TEXT NOT NULL
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS auth_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT,
                hwid TEXT,
                ip TEXT,
                status TEXT,
                created_at TEXT NOT NULL
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS purchases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                key TEXT NOT NULL,
                duration_days INTEGER NOT NULL,
                price INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                invoice_id INTEGER,
                status TEXT DEFAULT 'completed'
            )
        """)
        await db.commit()


async def register_user(user_id: int, username: Optional[str] = None):
    """Регистрация или обновление пользователя в БД"""
    now_str = format_dt(utc_now())
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO users (user_id, username, registered_at)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET username = excluded.username
        """, (user_id, username, now_str))
        await db.commit()


async def create_key(duration_days: int = 30, owner_id: Optional[int] = None) -> str:
    """Генерация уникального ключа формата XXXX-XXXX-XXXX-XXXX с возможностью привязки к владельцу"""
    alphabet = string.ascii_uppercase + string.digits
    while True:
        parts = [''.join(secrets.choice(alphabet) for _ in range(4)) for _ in range(4)]
        key = f"KEY-{'-'.join(parts)}"

        now_str = format_dt(utc_now())
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("SELECT 1 FROM keys WHERE key = ?", (key,))
            if await cursor.fetchone() is None:
                await db.execute("""
                    INSERT INTO keys (key, duration_days, created_at, owner_id)
                    VALUES (?, ?, ?, ?)
                """, (key, duration_days, now_str, owner_id))
                await db.commit()
                return key


async def record_purchase(user_id: int, key: str, duration_days: int, price: int, invoice_id: Optional[Any] = None):
    """Запись факта покупки в историю заказов"""
    now_str = format_dt(utc_now())
    inv_val = str(invoice_id) if invoice_id is not None else None
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO purchases (user_id, key, duration_days, price, created_at, invoice_id, status)
            VALUES (?, ?, ?, ?, ?, ?, 'completed')
        """, (user_id, key, duration_days, price, now_str, inv_val))
        await db.commit()


async def is_invoice_processed(invoice_id: Any) -> bool:
    """Проверка, был ли данный счет уже обработан и выдан"""
    if invoice_id is None:
        return False
    inv_str = str(invoice_id)
    inv_int = None
    try:
        inv_int = int(invoice_id)
    except (ValueError, TypeError):
        pass

    async with aiosqlite.connect(DB_PATH) as db:
        if inv_int is not None:
            cursor = await db.execute(
                "SELECT 1 FROM purchases WHERE invoice_id = ? OR invoice_id = ?",
                (inv_int, inv_str)
            )
        else:
            cursor = await db.execute(
                "SELECT 1 FROM purchases WHERE invoice_id = ?",
                (inv_str,)
            )
        return await cursor.fetchone() is not None


async def redeem_key(key: str, user_id: int) -> Tuple[bool, str]:
    """Привязка ключа к Telegram-аккаунту пользователя"""
    key = key.strip()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM keys WHERE key = ?", (key,))
        row = await cursor.fetchone()

        if not row:
            return False, "Ключ не найден."

        if row["is_banned"]:
            return False, "Этот ключ заблокирован."

        if row["owner_id"] is not None:
            if row["owner_id"] == user_id:
                return False, "Вы уже активировали этот ключ в своем аккаунте."
            return False, "Этот ключ уже привязан к другому Telegram-аккаунту."

        await db.execute("UPDATE keys SET owner_id = ? WHERE key = ?", (user_id, key))
        await db.commit()
        return True, f"Ключ успешно привязан к вашему аккаунту! Длительность: {row['duration_days']} дн."


async def authenticate(key: str, hwid: str, ip: str = "") -> Tuple[bool, str, Dict[str, Any]]:
    """
    Проверка авторизации лоадера по ключу и HWID.
    Логика:
    - Если ключ не существует -> ошибка
    - Если заблокирован -> ошибка
    - Если ключ еще не активирован на устройстве -> привязываем текущий HWID и рассчитываем срок
    - Если ключ активирован -> сверяем HWID и срок действия
    """
    key = key.strip()
    hwid = hwid.strip().lower()
    now = utc_now()
    now_str = format_dt(now)

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM keys WHERE key = ?", (key,))
        row = await cursor.fetchone()

        async def log_attempt(status: str):
            await db.execute("""
                INSERT INTO auth_logs (key, hwid, ip, status, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (key, hwid, ip, status, now_str))
            await db.commit()

        if not row:
            await log_attempt("KEY_NOT_FOUND")
            return False, "KEY_NOT_FOUND", {}

        if row["is_banned"]:
            await log_attempt("KEY_BANNED")
            return False, "KEY_BANNED", {}

        # Первый запуск - активация и привязка HWID
        if row["activated_at"] is None:
            expires_at = now + timedelta(days=row["duration_days"])
            exp_str = format_dt(expires_at)

            await db.execute("""
                UPDATE keys
                SET activated_at = ?, expires_at = ?, hwid = ?
                WHERE key = ?
            """, (now_str, exp_str, hwid, key))
            await log_attempt("FIRST_ACTIVATION_SUCCESS")

            return True, "AUTH_SUCCESS", {
                "expires_at": exp_str,
                "first_activation": True,
                "days_left": row["duration_days"]
            }

        # Проверка срока действия
        expires_at = parse_dt(row["expires_at"])
        if expires_at and now > expires_at:
            await log_attempt("KEY_EXPIRED")
            return False, "KEY_EXPIRED", {"expired_at": row["expires_at"]}

        # Проверка HWID
        bound_hwid = (row["hwid"] or "").strip().lower()

        # Если HWID был сброшен (пустой) -> привязываем новый
        if not bound_hwid:
            await db.execute("UPDATE keys SET hwid = ? WHERE key = ?", (hwid, key))
            await log_attempt("HWID_REBOUND_SUCCESS")
            days_left = max(0, (expires_at - now).days) if expires_at else 0
            return True, "AUTH_SUCCESS", {
                "expires_at": row["expires_at"],
                "rebound": True,
                "days_left": days_left
            }

        if bound_hwid != hwid:
            await log_attempt("HWID_MISMATCH")
            return False, "HWID_MISMATCH", {
                "bound_hwid_prefix": bound_hwid[:8] + "..." if bound_hwid else ""
            }

        days_left = max(0, (expires_at - now).days) if expires_at else 0
        await log_attempt("AUTH_SUCCESS")
        return True, "AUTH_SUCCESS", {
            "expires_at": row["expires_at"],
            "days_left": days_left
        }


async def verify_license(key: str, hwid: str) -> Tuple[bool, str]:
    """Быстрая проверка лицензии и HWID без повторной активации и записи в логи"""
    key = key.strip()
    hwid = hwid.strip().lower()
    now = utc_now()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM keys WHERE key = ?", (key,))
        row = await cursor.fetchone()
        if not row:
            return False, "KEY_NOT_FOUND"
        if row["is_banned"]:
            return False, "KEY_BANNED"
        if not row["activated_at"]:
            return False, "KEY_NOT_ACTIVATED"
        expires_at = parse_dt(row["expires_at"])
        if expires_at and now > expires_at:
            return False, "KEY_EXPIRED"
        bound_hwid = (row["hwid"] or "").strip().lower()
        if bound_hwid != hwid:
            return False, "HWID_MISMATCH"
        return True, "OK"


async def check_hwid_subscription(hwid: str, ip: str = "") -> Tuple[bool, str, Dict[str, Any]]:
    """
    Проверка наличия активной подписки по HWID устройства.
    Ищет все ключи, привязанные к данному HWID.
    """
    hwid = hwid.strip().lower()
    now = utc_now()
    now_str = format_dt(now)

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT * FROM keys 
            WHERE LOWER(hwid) = ?
            ORDER BY datetime(expires_at) DESC
        """, (hwid,))
        rows = await cursor.fetchall()

        async def log_attempt(status: str, key: str = ""):
            await db.execute("""
                INSERT INTO auth_logs (key, hwid, ip, status, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (key, hwid, ip, status, now_str))
            await db.commit()

        if not rows:
            await log_attempt("HWID_NO_SUBSCRIPTION")
            return False, "NO_SUBSCRIPTION", {}

        has_banned = False
        has_expired = False
        active_key_row = None

        for row in rows:
            if row["is_banned"]:
                has_banned = True
                continue
            exp_str = row["expires_at"]
            if not exp_str:
                continue
            expires_at = parse_dt(exp_str)
            if expires_at and now <= expires_at:
                active_key_row = row
                break
            else:
                has_expired = True

        if active_key_row is not None:
            expires_at = parse_dt(active_key_row["expires_at"])
            days_left = max(0, (expires_at - now).days) if expires_at else 0
            await log_attempt("HWID_AUTH_SUCCESS", active_key_row["key"])
            return True, "AUTH_SUCCESS", {
                "key": active_key_row["key"],
                "expires_at": active_key_row["expires_at"],
                "days_left": days_left
            }

        if has_banned and not has_expired:
            await log_attempt("KEY_BANNED")
            return False, "KEY_BANNED", {}

        if has_expired:
            await log_attempt("KEY_EXPIRED")
            return False, "KEY_EXPIRED", {}

        await log_attempt("HWID_NO_SUBSCRIPTION")
        return False, "NO_SUBSCRIPTION", {}


async def verify_hwid_subscription(hwid: str) -> Tuple[bool, str, Dict[str, Any]]:
    """Быстрая проверка подписки по HWID без спама в auth_logs"""
    hwid = hwid.strip().lower()
    now = utc_now()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT * FROM keys 
            WHERE LOWER(hwid) = ?
            ORDER BY datetime(expires_at) DESC
        """, (hwid,))
        rows = await cursor.fetchall()
        if not rows:
            return False, "NO_SUBSCRIPTION", {}

        has_banned = False
        has_expired = False
        for row in rows:
            if row["is_banned"]:
                has_banned = True
                continue
            exp_str = row["expires_at"]
            if not exp_str:
                continue
            expires_at = parse_dt(exp_str)
            if expires_at and now <= expires_at:
                days_left = max(0, (expires_at - now).days) if expires_at else 0
                return True, "OK", {
                    "key": row["key"],
                    "expires_at": row["expires_at"],
                    "days_left": days_left
                }
            else:
                has_expired = True

        if has_banned and not has_expired:
            return False, "KEY_BANNED", {}
        if has_expired:
            return False, "KEY_EXPIRED", {}
        return False, "NO_SUBSCRIPTION", {}


async def reset_hwid(key: str, user_id: Optional[int] = None, is_admin: bool = False) -> Tuple[bool, str]:
    """Сброс привязки HWID"""
    key = key.strip()
    now = utc_now()
    now_str = format_dt(now)

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM keys WHERE key = ?", (key,))
        row = await cursor.fetchone()

        if not row:
            return False, "Ключ не найден."

        if not is_admin:
            if row["owner_id"] != user_id:
                return False, "Вы не являетесь владельцем этого ключа."

            # Проверка кулдауна
            last_reset_str = row["last_hwid_reset"]
            if last_reset_str:
                last_reset = parse_dt(last_reset_str)
                if last_reset and (now - last_reset) < timedelta(hours=HWID_RESET_COOLDOWN_HOURS):
                    remain = timedelta(hours=HWID_RESET_COOLDOWN_HOURS) - (now - last_reset)
                    hours = int(remain.total_seconds() // 3600)
                    mins = int((remain.total_seconds() % 3600) // 60)
                    return False, f"Кулдаун на сброс HWID! Попробуйте через {hours}ч. {mins}мин."

        if not row["hwid"]:
            return False, "HWID для этого ключа и так не привязан."

        await db.execute("""
            UPDATE keys
            SET hwid = NULL, last_hwid_reset = ?
            WHERE key = ?
        """, (now_str, key))
        await db.commit()

        return True, "HWID успешно сброшен. При следующем запуске лоадер привяжет новое устройство."


async def ban_key(key: str, ban_status: bool = True) -> Tuple[bool, str]:
    """Блокировка / разблокировка ключа"""
    key = key.strip()
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT 1 FROM keys WHERE key = ?", (key,))
        if not await cursor.fetchone():
            return False, "Ключ не найден."

        val = 1 if ban_status else 0
        await db.execute("UPDATE keys SET is_banned = ? WHERE key = ?", (val, key))
        await db.commit()
        status_text = "заблокирован" if ban_status else "разблокирован"
        return True, f"Ключ успешно {status_text}."


async def get_user_keys(user_id: int) -> List[Dict[str, Any]]:
    """Получение всех ключей пользователя"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM keys WHERE owner_id = ?", (user_id,))
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_key_details(key: str) -> Optional[Dict[str, Any]]:
    """Получение подробной информации о ключе"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM keys WHERE key = ?", (key.strip(),))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_statistics() -> Dict[str, Any]:
    """Статистика для администратора"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        c1 = await db.execute("SELECT COUNT(*) as cnt FROM keys")
        total_keys = (await c1.fetchone())["cnt"]

        c2 = await db.execute("SELECT COUNT(*) as cnt FROM keys WHERE activated_at IS NOT NULL AND is_banned = 0")
        active_keys = (await c2.fetchone())["cnt"]

        c3 = await db.execute("SELECT COUNT(*) as cnt FROM users")
        total_users = (await c3.fetchone())["cnt"]

        c4 = await db.execute("SELECT COUNT(*) as cnt FROM auth_logs WHERE status = 'AUTH_SUCCESS'")
        auth_success_count = (await c4.fetchone())["cnt"]

        c5 = await db.execute("SELECT COUNT(*) as cnt, COALESCE(SUM(price), 0) as rev FROM purchases")
        purch_row = await c5.fetchone()
        total_purchases = purch_row["cnt"]
        total_revenue = purch_row["rev"]

        return {
            "total_keys": total_keys,
            "active_keys": active_keys,
            "total_users": total_users,
            "successful_auths": auth_success_count,
            "total_purchases": total_purchases,
            "total_revenue": total_revenue
        }


async def count_all_keys() -> int:
    """Общее количество ключей в базе данных"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM keys")
        row = await cursor.fetchone()
        return row[0] if row else 0


async def get_all_keys_with_users(limit: int = 5, offset: int = 0) -> List[Dict[str, Any]]:
    """Получение списка ключей с привязанными пользователями и HWID"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        query = """
            SELECT 
                k.key,
                k.duration_days,
                k.created_at,
                k.activated_at,
                k.expires_at,
                k.hwid,
                k.owner_id,
                k.is_banned,
                k.last_hwid_reset,
                u.username
            FROM keys k
            LEFT JOIN users u ON k.owner_id = u.user_id
            ORDER BY k.created_at DESC
            LIMIT ? OFFSET ?
        """
        cursor = await db.execute(query, (limit, offset))
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


