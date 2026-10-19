import os

# --- Telegram Bot Settings ---
# Замените на токен вашего Telegram-бота, полученный у @BotFather
BOT_TOKEN = os.getenv("BOT_TOKEN", "8766658947:AAEXi0-nV2yJDW0oAyV34nq_-FfjOGaeYpk")

# Список Telegram ID администраторов (могут генерировать ключи, блокировать, смотреть статистику)
# Пример: ADMIN_IDS = [123456789, 987654321]
ADMIN_IDS = [1034968449]

# --- Настройки обхода блокировки api.telegram.org ---
# Если api.telegram.org блокируется провайдером ("Превышен таймаут семафора"):
# 1. Прокси (HTTP или SOCKS5):
#    Примеры:
#    PROXY_URL = "http://127.0.0.1:10809"       (порт HTTP прокси V2Ray / Clash / Hiddify)
#    PROXY_URL = "socks5://127.0.0.1:10808"     (порт SOCKS5 прокси)
#    PROXY_URL = "http://user:pass@ip:port"     (внешний прокси)
PROXY_URL = os.getenv("PROXY_URL", "").strip()

# 2. Или альтернативное зеркало Telegram API (Reverse Proxy / Cloudflare Worker):
#    Пример: CUSTOM_BOT_API_URL = "https://api.telegram-proxy.org"
CUSTOM_BOT_API_URL = os.getenv("CUSTOM_BOT_API_URL", "https://jolly-wind-4d0a.autotopkabuy222.workers.dev/").strip()
# --- API Backend Settings ---
API_HOST = os.getenv("API_HOST", "0.0.0.0")
# Определение рабочей директории:
# Если скомпилировано в EXE (PyInstaller) — используем директорию с .exe файлом.
# Если запуск из Python — используем корень репозитория.
import sys

if getattr(sys, "frozen", False):
    EXE_DIR = os.path.dirname(os.path.abspath(sys.executable))
    PROJECT_ROOT = EXE_DIR
    TG_BOT_DIR = EXE_DIR
else:
    TG_BOT_DIR = os.path.dirname(os.path.abspath(__file__))
    PROJECT_ROOT = os.path.dirname(TG_BOT_DIR)

# Автозагрузка .env если он существует рядом с exe или в корне
env_file_candidates = [
    os.path.join(PROJECT_ROOT, ".env"),
    os.path.join(TG_BOT_DIR, ".env"),
]
for env_file in env_file_candidates:
    if os.path.exists(env_file):
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip("'\"")
                        if k and k not in os.environ:
                            os.environ[k] = v
        except Exception:
            pass

API_PORT = int(os.getenv("API_PORT", 8000))

# Секретный ключ для подписи или шифрования трафика (AES-256-CBC)
CIPHER_SECRET = os.getenv("CIPHER_SECRET", "Kgggkfk")
SERVER_SECRET = os.getenv("SERVER_SECRET", CIPHER_SECRET)

# База данных SQLite (в EXE хранится рядом с .exe, в dev - в tg_bot/database.db)
if getattr(sys, "frozen", False):
    DB_PATH = os.getenv("DB_PATH", os.path.join(EXE_DIR, "database.db"))
    CHEATS_DIR = os.path.abspath(os.getenv("CHEATS_DIR", os.path.join(EXE_DIR, "cheat")))
else:
    DB_PATH = os.getenv("DB_PATH", os.path.join(TG_BOT_DIR, "database.db"))
    CHEATS_DIR = os.path.abspath(os.getenv("CHEATS_DIR", os.path.join(PROJECT_ROOT, "cheat")))

# Настройки сброса HWID (кулдаун в часах для обычных пользователей)
HWID_RESET_COOLDOWN_HOURS = 24

os.makedirs(CHEATS_DIR, exist_ok=True)

# --- Настройки цен на подписки (в рублях) ---
PRICE_1_DAY = int(os.getenv("PRICE_1_DAY", "150"))    # 1 день
PRICE_7_DAYS = int(os.getenv("PRICE_7_DAYS", "550"))   # 7 дней
PRICE_30_DAYS = int(os.getenv("PRICE_30_DAYS", "1900")) # 30 дней

PRICES = {
    1: PRICE_1_DAY,
    7: PRICE_7_DAYS,
    30: PRICE_30_DAYS
}

# --- Настройки Crypto Pay (@CryptoBot) ---
CRYPTO_PAY_TOKEN = os.getenv("CRYPTO_PAY_TOKEN", "642914:AAgFBySjoLUcpyS3KCv0P1NL2dXFQ77g9Ct")
CRYPTO_PAY_API_URL = os.getenv("CRYPTO_PAY_API_URL", "https://pay.crypt.bot/api")
