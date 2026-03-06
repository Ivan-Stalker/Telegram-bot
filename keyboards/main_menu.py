from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def main_menu_kb(is_admin: bool = False) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text="📅 Записаться", callback_data="menu_book"),
        ],
        [
            InlineKeyboardButton(text="❌ Моя запись", callback_data="menu_my_booking"),
        ],
        [
            InlineKeyboardButton(text="💅 Прайсы", callback_data="menu_prices"),
        ],
        [
            InlineKeyboardButton(
                text="📷 Портфолио",
                callback_data="menu_portfolio",
            ),
        ],
    ]

    if is_admin:
        buttons.append(
            [
                InlineKeyboardButton(
                    text="🛠 Админ-панель", callback_data="menu_admin_panel"
                )
            ]
        )

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def prices_message_html() -> str:
    return (
        "<b>Прайс-лист</b>\n\n"
        "Френч — <b>1000₽</b>\n"
        "Квадрат — <b>500₽</b>"
    )


def portfolio_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Смотреть портфолио",
                    url="https://ru.pinterest.com/crystalwithluv/_created/",
                )
            ]
        ]
    )