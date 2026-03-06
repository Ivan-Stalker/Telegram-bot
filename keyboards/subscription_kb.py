from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import settings


def subscription_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📣 Подписаться",
                    url=settings.CHANNEL_LINK,
                )
            ],
            [
                InlineKeyboardButton(
                    text="✅ Проверить подписку",
                    callback_data="check_subscription",
                )
            ],
        ]
    )