import asyncio
import logging
import sys
import uvicorn

try:
    from .config import API_HOST, API_PORT, BOT_TOKEN
    from .database import init_db
    from .server import app
    from .bot import bot, dp
except (ImportError, ValueError):
    from tg_bot.config import API_HOST, API_PORT, BOT_TOKEN
    from tg_bot.database import init_db
    from tg_bot.server import app
    from tg_bot.bot import bot, dp

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("AuthSystem")


async def run_server():
    """Запуск FastAPI сервера для приема запросов от лоадера"""
    config = uvicorn.Config(
        app=app,
        host=API_HOST,
        port=API_PORT,
        log_level="info",
        access_log=False,
        loop="asyncio",
        http="h11"
    )
    server = uvicorn.Server(config)
    logger.info(f"API сервер запущен на http://{API_HOST}:{API_PORT}")
    await server.serve()


async def run_bot():
    """Запуск Telegram-бота"""
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
        logger.warning(
            "ВНИМАНИЕ: Токен Telegram бота не указан в config.py или переменных окружения! "
            "Бот не запущен, но API сервер продолжит работу."
        )
        # Просто держим задачу живой, пока работает сервер
        while True:
            await asyncio.sleep(3600)

    logger.info("Запуск Telegram-бота (polling)...")
    while True:
        try:
            await dp.start_polling(
                bot,
                drop_pending_updates=True,
                handle_as_tasks=True,
                polling_timeout=10,
                allowed_updates=dp.resolve_used_update_types()
            )
            break
        except Exception as e:
            logger.error(
                f"Ошибка подключения к Telegram API: {e}\n"
                "Подсказка: если api.telegram.org блокируется сетью (таймаут семафора), "
                "укажите рабочий HTTP/SOCKS5 прокси или зеркало в tg_bot/config.py (PROXY_URL или CUSTOM_BOT_API_URL)."
            )
            await asyncio.sleep(5)


async def main():
    logger.info("Инициализация базы данных...")
    await init_db()

    logger.info("Запуск сервисов...")
    try:
        await asyncio.gather(
            run_server(),
            run_bot()
        )
    except asyncio.CancelledError:
        logger.info("Сервисы остановлены.")
    finally:
        await bot.session.close()


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Завершение работы.")

