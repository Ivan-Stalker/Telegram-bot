from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from aiogram.utils.formatting import as_marked_section, Bold

from config import settings
from keyboards.main_menu import main_menu_kb
from keyboards.subscription_kb import subscription_kb

subscription_router = Router()


async def _check_subscription(bot, user_id: int) -> bool:
    """
    Проверка подписки через getChatMember.
    Делаем короткий таймаут и, если Telegram не отвечает или возвращает ошибку,
    не блокируем пользователя, а пропускаем его дальше.
    """
    try:
        member = await bot.get_chat_member(
            chat_id=settings.CHANNEL_ID,
            user_id=user_id,
            request_timeout=5,
        )
        status = member.status
        return status in ("member", "administrator", "creator")
    except Exception:
        # Если не получилось проверить (ошибка/таймаут) — не мучаем пользователя ожиданием
        # и считаем, что он подписан.
        return True


@subscription_router.message(CommandStart())
async def cmd_start(message: Message):
    is_admin = message.from_user.id == settings.ADMIN_ID

    if not await _check_subscription(message.bot, message.from_user.id):
        text = (
            "Для записи необходимо подписаться на канал.\n\n"
            "Пожалуйста, подпишитесь и затем нажмите «Проверить подписку»."
        )
        await message.answer(text=text, reply_markup=subscription_kb())
        return

    text = as_marked_section(
        Bold("Добро пожаловать!"),
        "Вы можете записаться на маникюр через удобное меню ниже.",
        "Также можно просмотреть прайс и портфолио.",
        marker="• ",
    ).as_html()

    await message.answer(
        text=text,
        reply_markup=main_menu_kb(is_admin=is_admin),
    )


@subscription_router.callback_query(F.data == "check_subscription")
async def cb_check_subscription(callback: CallbackQuery):
    has_sub = await _check_subscription(callback.bot, callback.from_user.id)

    if has_sub:
        is_admin = callback.from_user.id == settings.ADMIN_ID
        await callback.message.edit_text(
            text="Спасибо за подписку! Теперь вы можете воспользоваться ботом.",
            reply_markup=main_menu_kb(is_admin=is_admin),
        )
    else:
        await callback.answer(
            text="Подписка не найдена. Пожалуйста, подпишитесь на канал.",
            show_alert=True,
        )