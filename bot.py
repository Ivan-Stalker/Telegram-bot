import asyncio

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import settings
from scheduler_service import scheduler, restore_all_reminders
from handlers.subscription import subscription_router
from handlers.user_booking import user_router
from handlers.admin_panel import admin_router
from database import Database


async def main():
    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    # Инициализируем БД (создаст таблицы при первом запуске)
    Database(settings.DB_PATH)

    # Роутеры
    dp.include_router(subscription_router)
    dp.include_router(user_router)
    dp.include_router(admin_router)

    # Запускаем планировщик и восстанавливаем задачи
    scheduler.start()
    await restore_all_reminders(bot)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())