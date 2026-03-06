import os
from dataclasses import dataclass


@dataclass
class Settings:
    # Токен бота
    # Можно задать через переменную окружения BOT_TOKEN,
    # либо оставить здесь прямо в коде (как сейчас).
    BOT_TOKEN: str = os.getenv(
        "BOT_TOKEN",
        "8680673808:AAEfp5Rl6lTxeqLhrz1FyNriUK04YpYRHcw",
    )

    # ID администратора (ваш Telegram ID)
    ADMIN_ID: int = int(os.getenv("ADMIN_ID", "7630008699"))

    # Путь к базе данных SQLite
    DB_PATH: str = os.getenv("DB_PATH", "database.db")

    # Канал для расписания (куда отправлять информацию о записях)
    SCHEDULE_CHANNEL_ID: int = int(os.getenv("SCHEDULE_CHANNEL_ID", "-1003727238246"))

    # Обязательный канал для подписки
    CHANNEL_ID: int = int(os.getenv("CHANNEL_ID", "-1003727238246"))
    CHANNEL_LINK: str = os.getenv("CHANNEL_LINK", "https://t.me/raspisaniay")

    def __post_init__(self):
        token = (self.BOT_TOKEN or "").strip()
        if not token:
            raise RuntimeError(
                "Не задан BOT_TOKEN.\n"
                "Укажите токен бота в config.py (BOT_TOKEN) или задайте переменную окружения BOT_TOKEN."
            )
        self.BOT_TOKEN = token


settings = Settings()
