from datetime import date, datetime, timedelta

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.utils.formatting import Bold, as_marked_section

from config import settings
from database import Database
from keyboards.main_menu import main_menu_kb, prices_message_html, portfolio_kb
from keyboards.calendar_kb import (
    booking_calendar_kb,
    CalendarCallback,
)
from keyboards.subscription_kb import subscription_kb
from scheduler_service import (
    db,
    schedule_reminder_for_booking,
    remove_reminder_job,
)
from states.booking_states import BookingStates

user_router = Router()

# Используем один экземпляр БД из scheduler_service.db
# (чтобы не дублировать инициализацию)


async def _ensure_subscribed(callback: CallbackQuery) -> bool:
    """
    Проверка подписки перед доступом к записи.
    """
    try:
        member = await callback.message.bot.get_chat_member(
            chat_id=settings.CHANNEL_ID,
            user_id=callback.from_user.id,
        )
        status = member.status
        if status in ("member", "administrator", "creator"):
            return True
    except Exception:
        pass

    await callback.message.edit_text(
        text="Для записи необходимо подписаться на канал.",
        reply_markup=subscription_kb(),
    )
    return False


@user_router.callback_query(F.data == "menu_book")
async def menu_book(callback: CallbackQuery, state: FSMContext):
    if not await _ensure_subscribed(callback):
        return

    await state.set_state(BookingStates.choosing_date)
    await callback.message.edit_text(
        text="Выберите дату (на ближайший месяц):",
        reply_markup=booking_calendar_kb(),
    )


@user_router.callback_query(F.data == "menu_my_booking")
async def menu_my_booking(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    booking = db.get_user_active_booking(callback.from_user.id)
    if not booking:
        await callback.message.edit_text(
            text="У вас нет активной записи.",
            reply_markup=main_menu_kb(
                is_admin=callback.from_user.id == settings.ADMIN_ID
            ),
        )
        return

    date_str = booking["date"]
    time_str = booking["time"]
    text = (
        "<b>Ваша текущая запись:</b>\n\n"
        f"Дата: <b>{date_str}</b>\n"
        f"Время: <b>{time_str}</b>\n\n"
        "Вы можете отменить запись:"
    )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="❌ Отменить запись", callback_data="cancel_booking_confirm"
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ В меню", callback_data="back_to_menu_from_my_booking"
                )
            ],
        ]
    )

    await callback.message.edit_text(text=text, reply_markup=kb)


@user_router.callback_query(F.data == "back_to_menu_from_my_booking")
async def back_to_menu_from_my_booking(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        text="Главное меню:",
        reply_markup=main_menu_kb(is_admin=callback.from_user.id == settings.ADMIN_ID),
    )


@user_router.callback_query(F.data == "cancel_booking_confirm")
async def cancel_booking_confirm(callback: CallbackQuery):
    result = db.cancel_booking_by_user(callback.from_user.id)
    if not result:
        await callback.answer("Активная запись не найдена.", show_alert=True)
        return

    booking_id, date_str, time_str, reminder_job_id = result

    # Удаляем задачу напоминания
    if reminder_job_id:
        remove_reminder_job(reminder_job_id)

    # Уведомление пользователя
    await callback.message.edit_text(
        text=(
            "Ваша запись отменена.\n\n"
            f"Дата: <b>{date_str}</b>\n"
            f"Время: <b>{time_str}</b>"
        ),
        reply_markup=main_menu_kb(is_admin=callback.from_user.id == settings.ADMIN_ID),
    )

    # Уведомляем администратора
    try:
        await callback.bot.send_message(
            chat_id=settings.ADMIN_ID,
            text=(
                f"<b>Запись отменена пользователем</b>\n\n"
                f"ID пользователя: <code>{callback.from_user.id}</code>\n"
                f"Дата: <b>{date_str}</b>\n"
                f"Время: <b>{time_str}</b>\n"
                f"ID записи: <code>{booking_id}</code>"
            ),
        )
    except Exception:
        pass


# ---- Обработчики календаря ----


@user_router.callback_query(CalendarCallback.filter())
async def calendar_handler(
    callback: CallbackQuery, callback_data: CalendarCallback, state: FSMContext
):
    current_state = await state.get_state()
    if current_state != BookingStates.choosing_date.state:
        await callback.answer()
        return

    today = date.today()
    max_day = today + timedelta(days=30)
    chosen_date = date(callback_data.year, callback_data.month, callback_data.day)

    if callback_data.action == "NAVIGATE":
        # Перерисовываем календарь
        from keyboards.calendar_kb import get_month_calendar

        kb = get_month_calendar(
            year=callback_data.year,
            month=callback_data.month,
            min_date=today,
            max_date=max_day,
        )
        await callback.message.edit_reply_markup(reply_markup=kb)
        await callback.answer()
        return

    if callback_data.action == "DAY":
        if chosen_date < today or chosen_date > max_day:
            await callback.answer(
                "Выберите дату в пределах ближайшего месяца.", show_alert=True
            )
            return

        date_str = chosen_date.isoformat()
        free_slots = db.get_free_slots_for_date(date_str)
        if not free_slots:
            await callback.answer(
                "На выбранную дату нет свободных слотов.", show_alert=True
            )
            return

        await state.update_data(date=date_str)
        await state.set_state(BookingStates.choosing_time)

        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=t,
                        callback_data=f"choose_time:{t}",
                    )
                ]
                for t in free_slots
            ]
            + [
                [
                    InlineKeyboardButton(
                        text="⬅️ Выбрать другую дату", callback_data="back_to_calendar"
                    )
                ]
            ]
        )

        await callback.message.edit_text(
            text=f"Вы выбрали дату: <b>{date_str}</b>\n\nВыберите время:",
            reply_markup=kb,
        )
        await callback.answer()
        return


@user_router.callback_query(F.data == "cal_close")
async def calendar_close(callback: CallbackQuery, state: FSMContext):
    """
    Закрытие календаря и выход в главное меню.
    """
    await state.clear()
    await callback.message.edit_text(
        text="Главное меню:",
        reply_markup=main_menu_kb(is_admin=callback.from_user.id == settings.ADMIN_ID),
    )
    await callback.answer()


@user_router.callback_query(F.data == "back_to_calendar")
async def back_to_calendar(callback: CallbackQuery, state: FSMContext):
    await state.set_state(BookingStates.choosing_date)
    await callback.message.edit_text(
        text="Выберите дату (на ближайший месяц):",
        reply_markup=booking_calendar_kb(),
    )


@user_router.callback_query(F.data.startswith("choose_time:"))
async def choose_time(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    date_str = data.get("date")
    if not date_str:
        await callback.answer("Сначала выберите дату.", show_alert=True)
        return

    time_str = callback.data.split(":", 1)[1]
    free_slots = db.get_free_slots_for_date(date_str)
    if time_str not in free_slots:
        await callback.answer("Этот слот уже недоступен. Выберите другой.", show_alert=True)
        # Обновим список слотов
        if free_slots:
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text=t,
                            callback_data=f"choose_time:{t}",
                        )
                    ]
                    for t in free_slots
                ]
                + [
                    [
                        InlineKeyboardButton(
                            text="⬅️ Выбрать другую дату",
                            callback_data="back_to_calendar",
                        )
                    ]
                ]
            )
            await callback.message.edit_reply_markup(reply_markup=kb)
        else:
            await callback.message.edit_text(
                text=(
                    f"На дату <b>{date_str}</b> больше нет свободных слотов.\n"
                    "Выберите другую дату:"
                ),
                reply_markup=booking_calendar_kb(),
            )
            await state.set_state(BookingStates.choosing_date)
        return

    await state.update_data(time=time_str)
    await state.set_state(BookingStates.entering_name)

    await callback.message.edit_text(
        text=(
            f"Вы выбрали:\n\n"
            f"Дата: <b>{date_str}</b>\n"
            f"Время: <b>{time_str}</b>\n\n"
            "Пожалуйста, отправьте ваше <b>имя</b>."
        )
    )
    await callback.answer()


@user_router.message(BookingStates.entering_name)
async def booking_enter_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if len(name) < 2:
        await message.answer("Имя слишком короткое, попробуйте ещё раз.")
        return

    await state.update_data(name=name)
    await state.set_state(BookingStates.entering_phone)
    await message.answer("Теперь отправьте, пожалуйста, ваш <b>номер телефона</b>.")


@user_router.message(BookingStates.entering_phone, F.text)
@user_router.message(BookingStates.entering_phone, F.contact)
async def booking_enter_phone(message: Message, state: FSMContext):
    if message.contact:
        phone = (message.contact.phone_number or "").strip()
        if phone and not phone.startswith("+"):
            phone = "+" + phone
    else:
        phone = (message.text or "").strip()
    if len(phone) < 5:
        await message.answer("Некорректный номер телефона, попробуйте ещё раз.")
        return

    await state.update_data(phone=phone)
    data = await state.get_data()

    date_str = data.get("date")
    time_str = data.get("time")
    name = data.get("name")
    if not date_str or not time_str or not name:
        await state.clear()
        await message.answer(
            "Данные записи потеряны. Пожалуйста, начните запись заново.",
            reply_markup=main_menu_kb(is_admin=message.from_user.id == settings.ADMIN_ID),
        )
        return

    text = (
        "<b>Подтверждение записи</b>\n\n"
        f"Имя: <b>{name}</b>\n"
        f"Телефон: <b>{phone}</b>\n"
        f"Дата: <b>{date_str}</b>\n"
        f"Время: <b>{time_str}</b>\n\n"
        "Подтвердить запись?"
    )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Подтвердить", callback_data="booking_confirm"
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отменить", callback_data="booking_cancel_flow"
                )
            ],
        ]
    )

    await state.set_state(BookingStates.confirming)
    try:
        await message.answer(text=text, reply_markup=kb)
    except Exception:
        await state.clear()
        await message.answer(
            "Не удалось отправить подтверждение. Начните запись заново.",
            reply_markup=main_menu_kb(is_admin=message.from_user.id == settings.ADMIN_ID),
        )


@user_router.message(BookingStates.entering_phone)
async def booking_enter_phone_fallback(message: Message, state: FSMContext):
    """Если прислали не текст и не контакт (например фото) — просим номер снова."""
    await message.answer(
        "Пожалуйста, отправьте номер телефона <b>текстом</b> (например 89001234567) "
        "или нажмите кнопку «Поделиться контактом»."
    )


@user_router.callback_query(F.data == "booking_cancel_flow")
async def booking_cancel_flow(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        text="Запись отменена.",
        reply_markup=main_menu_kb(is_admin=callback.from_user.id == settings.ADMIN_ID),
    )


@user_router.callback_query(F.data == "booking_confirm")
async def booking_confirm(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    date_str = data["date"]
    time_str = data["time"]
    name = data["name"]
    phone = data["phone"]

    tg_id = callback.from_user.id
    chat_id = callback.message.chat.id

    # Обновляем данные пользователя
    db.update_user_info(tg_id=tg_id, name=name, phone=phone)

    # Расчёт времени напоминания
    appointment_dt = datetime.fromisoformat(f"{date_str} {time_str}")
    reminder_dt = appointment_dt - timedelta(days=1)
    now = datetime.now()
    reminder_at = reminder_dt if reminder_dt > now else None

    # Создаём запись
    booking_id = db.create_booking(
        tg_id=tg_id,
        chat_id=chat_id,
        date_str=date_str,
        time_str=time_str,
        reminder_at=reminder_at,
        reminder_job_id="",  # временно
    )

    if not booking_id:
        await callback.message.edit_text(
            text=(
                "Не удалось создать запись.\n"
                "Возможные причины:\n"
                "• У вас уже есть активная запись\n"
                "• Слот уже занят\n"
                "• День был закрыт\n\n"
                "Попробуйте выбрать другой слот."
            ),
            reply_markup=main_menu_kb(
                is_admin=callback.from_user.id == settings.ADMIN_ID
            ),
        )
        await state.clear()
        return

    # Планируем напоминание (если нужно)
    reminder_job_id = ""
    if reminder_at:
        reminder_job_id = schedule_reminder_for_booking(
            bot=callback.bot,
            booking_id=booking_id,
            chat_id=chat_id,
            date_str=date_str,
            time_str=time_str,
        )

    # Обновляем reminder_job_id в БД (если создано напоминание)
    if reminder_job_id:
        conn = db._connect()
        cur = conn.cursor()
        cur.execute(
            "UPDATE bookings SET reminder_job_id = ? WHERE id = ?",
            (reminder_job_id, booking_id),
        )
        conn.commit()
        conn.close()

    await state.clear()

    # Сообщение пользователю
    await callback.message.edit_text(
        text=(
            "<b>Запись успешно создана!</b>\n\n"
            f"Имя: <b>{name}</b>\n"
            f"Телефон: <b>{phone}</b>\n"
            f"Дата: <b>{date_str}</b>\n"
            f"Время: <b>{time_str}</b>"
        ),
        reply_markup=main_menu_kb(is_admin=callback.from_user.id == settings.ADMIN_ID),
    )

    # Уведомление администратору
    admin_text = (
        "<b>Новая запись</b>\n\n"
        f"ID записи: <code>{booking_id}</code>\n"
        f"Пользователь: <code>{tg_id}</code>\n"
        f"Имя: <b>{name}</b>\n"
        f"Телефон: <b>{phone}</b>\n"
        f"Дата: <b>{date_str}</b>\n"
        f"Время: <b>{time_str}</b>"
    )
    try:
        await callback.bot.send_message(chat_id=settings.ADMIN_ID, text=admin_text)
    except Exception:
        pass

    # Сообщение в канал с расписанием
    channel_text = (
        "<b>Новая запись в расписании</b>\n\n"
        f"Дата: <b>{date_str}</b>\n"
        f"Время: <b>{time_str}</b>\n"
        f"Имя клиента: <b>{name}</b>\n"
        f"Телефон: <b>{phone}</b>"
    )
    try:
        await callback.bot.send_message(
            chat_id=settings.SCHEDULE_CHANNEL_ID,
            text=channel_text,
        )
    except Exception:
        pass


# ---- Кнопки Прайсы и Портфолио (без FSM) ----


@user_router.callback_query(F.data == "menu_prices")
async def menu_prices(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer(
        text=prices_message_html(),
        parse_mode="HTML",
    )


@user_router.callback_query(F.data == "menu_portfolio")
async def menu_portfolio(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer(
        text="Моё портфолио:",
        reply_markup=portfolio_kb(),
    )