from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from config import settings
from database import Database
from scheduler_service import db, remove_reminder_job
from states.admin_states import (
    AdminAddDayStates,
    AdminAddSlotStates,
    AdminDeleteSlotStates,
    AdminCloseDayStates,
    AdminCancelBookingStates,
    AdminViewScheduleStates,
)
from keyboards.main_menu import main_menu_kb

admin_router = Router()


def _is_admin(user_id: int) -> bool:
    return user_id == settings.ADMIN_ID


def admin_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="➕ Добавить рабочий день", callback_data="admin_add_day"
                )
            ],
            [
                InlineKeyboardButton(
                    text="➕ Добавить слот", callback_data="admin_add_slot"
                )
            ],
            [
                InlineKeyboardButton(
                    text="➖ Удалить слот", callback_data="admin_delete_slot"
                )
            ],
            [
                InlineKeyboardButton(
                    text="⛔ Закрыть день", callback_data="admin_close_day"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🚫 Отменить запись клиента",
                    callback_data="admin_cancel_booking",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📋 Расписание на дату",
                    callback_data="admin_view_schedule",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ В главное меню", callback_data="admin_back_to_menu"
                )
            ],
        ]
    )


@admin_router.callback_query(F.data == "menu_admin_panel")
async def open_admin_panel(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer("Доступ запрещён.", show_alert=True)
        return
    await state.clear()
    await callback.message.edit_text(
        text="🛠 <b>Админ-панель</b>\nВыберите действие:",
        reply_markup=admin_menu_kb(),
    )


@admin_router.callback_query(F.data == "admin_back_to_menu")
async def admin_back_to_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        text="Главное меню:",
        reply_markup=main_menu_kb(is_admin=True),
    )


# ---- Добавление рабочего дня ----


@admin_router.callback_query(F.data == "admin_add_day")
async def admin_add_day_start(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer("Доступ запрещён.", show_alert=True)
        return

    await state.set_state(AdminAddDayStates.waiting_for_date)
    await callback.message.edit_text(
        text=(
            "Введите дату рабочего дня в формате <b>ГГГГ-ММ-ДД</b>.\n"
            "Например: <code>2026-03-10</code>"
        )
    )


@admin_router.message(AdminAddDayStates.waiting_for_date)
async def admin_add_day_finish(message: Message, state: FSMContext):
    date_str = message.text.strip()
    try:
        from datetime import datetime

        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        await message.answer("Некорректная дата. Введите в формате ГГГГ-ММ-ДД.")
        return

    db.add_work_day(date_str)
    await state.clear()
    await message.answer(
        text=f"Рабочий день <b>{date_str}</b> добавлен.",
        reply_markup=admin_menu_kb(),
    )


# ---- Добавление слота ----


@admin_router.callback_query(F.data == "admin_add_slot")
async def admin_add_slot_start(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer("Доступ запрещён.", show_alert=True)
        return

    await state.set_state(AdminAddSlotStates.waiting_for_date)
    await callback.message.edit_text(
        text=(
            "Добавление слота.\n"
            "Введите дату в формате <b>ГГГГ-ММ-ДД</b>."
        )
    )


@admin_router.message(AdminAddSlotStates.waiting_for_date)
async def admin_add_slot_date(message: Message, state: FSMContext):
    date_str = message.text.strip()
    try:
        from datetime import datetime

        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        await message.answer("Некорректная дата. Введите в формате ГГГГ-ММ-ДД.")
        return

    await state.update_data(date=date_str)
    await state.set_state(AdminAddSlotStates.waiting_for_time)
    await message.answer("Введите время слота в формате <b>ЧЧ:ММ</b> (например, 10:30).")


@admin_router.message(AdminAddSlotStates.waiting_for_time)
async def admin_add_slot_time(message: Message, state: FSMContext):
    time_str = message.text.strip()
    try:
        from datetime import datetime

        datetime.strptime(time_str, "%H:%M")
    except ValueError:
        await message.answer("Некорректное время. Введите в формате ЧЧ:ММ.")
        return

    data = await state.get_data()
    date_str = data["date"]

    created = db.add_time_slot(date_str=date_str, time_str=time_str)
    await state.clear()
    if created:
        await message.answer(
            text=f"Слот <b>{date_str} {time_str}</b> добавлен.",
            reply_markup=admin_menu_kb(),
        )
    else:
        await message.answer(
            text="Не удалось добавить слот. Возможно, день закрыт или слот уже существует.",
            reply_markup=admin_menu_kb(),
        )


# ---- Удаление слота ----


@admin_router.callback_query(F.data == "admin_delete_slot")
async def admin_delete_slot_start(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer("Доступ запрещён.", show_alert=True)
        return

    await state.set_state(AdminDeleteSlotStates.waiting_for_date)
    await callback.message.edit_text(
        text="Удаление слота.\nВведите дату в формате <b>ГГГГ-ММ-ДД</b>."
    )


@admin_router.message(AdminDeleteSlotStates.waiting_for_date)
async def admin_delete_slot_date(message: Message, state: FSMContext):
    date_str = message.text.strip()
    try:
        from datetime import datetime

        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        await message.answer("Некорректная дата. Введите в формате ГГГГ-ММ-ДД.")
        return

    slots = db.get_all_slots_for_date(date_str)
    if not slots:
        await state.clear()
        await message.answer(
            text=f"На дату <b>{date_str}</b> слотов не найдено.",
            reply_markup=admin_menu_kb(),
        )
        return

    await state.update_data(date=date_str)
    await state.set_state(AdminDeleteSlotStates.waiting_for_time)

    text_lines = [f"Слоты на <b>{date_str}</b>:"]
    for s in slots:
        status = "свободен" if s["is_available"] else "занят/недоступен"
        text_lines.append(f"• {s['time']} — {status}")

    await message.answer(
        text="\n".join(text_lines)
        + "\n\nВведите время слота, который нужно удалить (ЧЧ:ММ).",
    )


@admin_router.message(AdminDeleteSlotStates.waiting_for_time)
async def admin_delete_slot_time(message: Message, state: FSMContext):
    time_str = message.text.strip()
    data = await state.get_data()
    date_str = data["date"]

    deleted = db.delete_time_slot(date_str=date_str, time_str=time_str)
    await state.clear()
    if deleted:
        await message.answer(
            text=f"Слот <b>{date_str} {time_str}</b> удалён.",
            reply_markup=admin_menu_kb(),
        )
    else:
        await message.answer(
            text=(
                "Не удалось удалить слот.\n"
                "Возможно, на этот слот есть активная запись или он не существует."
            ),
            reply_markup=admin_menu_kb(),
        )


# ---- Закрытие дня ----


@admin_router.callback_query(F.data == "admin_close_day")
async def admin_close_day_start(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer("Доступ запрещён.", show_alert=True)
        return

    await state.set_state(AdminCloseDayStates.waiting_for_date)
    await callback.message.edit_text(
        text=(
            "Закрытие дня.\n"
            "Введите дату в формате <b>ГГГГ-ММ-ДД</b>.\n"
            "Все активные записи будут отменены."
        )
    )


@admin_router.message(AdminCloseDayStates.waiting_for_date)
async def admin_close_day_finish(message: Message, state: FSMContext):
    date_str = message.text.strip()
    try:
        from datetime import datetime

        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        await message.answer("Некорректная дата. Введите в формате ГГГГ-ММ-ДД.")
        return

    bookings = db.close_work_day(date_str)
    cancelled_count = 0
    for b in bookings:
        booking_id = b["id"]
        reminder_job_id = db.cancel_booking_by_id(
            booking_id=booking_id, new_status="cancelled_by_admin_day_closed"
        )
        if reminder_job_id:
            remove_reminder_job(reminder_job_id)

        cancelled_count += 1

        # Уведомим клиента
        try:
            await message.bot.send_message(
                chat_id=b["tg_id"],
                text=(
                    "К сожалению, ваш день был отменён мастером.\n\n"
                    f"Дата: <b>{b['date']}</b>\n"
                    f"Время: <b>{b['time']}</b>"
                ),
            )
        except Exception:
            pass

    await state.clear()
    await message.answer(
        text=(
            f"День <b>{date_str}</b> закрыт.\n"
            f"Отменено активных записей: <b>{cancelled_count}</b>."
        ),
        reply_markup=admin_menu_kb(),
    )


# ---- Отмена записи клиента ----


@admin_router.callback_query(F.data == "admin_cancel_booking")
async def admin_cancel_booking_start(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer("Доступ запрещён.", show_alert=True)
        return

    await state.set_state(AdminCancelBookingStates.waiting_for_booking_id)
    await callback.message.edit_text(
        text=(
            "Отмена записи клиента.\n"
            "Введите <b>ID записи</b> (можно взять из уведомлений бота)."
        )
    )


@admin_router.message(AdminCancelBookingStates.waiting_for_booking_id)
async def admin_cancel_booking_finish(message: Message, state: FSMContext):
    text = message.text.strip()
    if not text.isdigit():
        await message.answer("Некорректный ID. Введите целое число.")
        return

    booking_id = int(text)
    reminder_job_id = db.cancel_booking_by_id(
        booking_id=booking_id, new_status="cancelled_by_admin"
    )
    if not reminder_job_id:
        await state.clear()
        await message.answer(
            text="Активная запись с таким ID не найдена.",
            reply_markup=admin_menu_kb(),
        )
        return

    remove_reminder_job(reminder_job_id)
    await state.clear()
    await message.answer(
        text=f"Запись с ID <b>{booking_id}</b> отменена.",
        reply_markup=admin_menu_kb(),
    )


# ---- Просмотр расписания ----


@admin_router.callback_query(F.data == "admin_view_schedule")
async def admin_view_schedule_start(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer("Доступ запрещён.", show_alert=True)
        return

    await state.set_state(AdminViewScheduleStates.waiting_for_date)
    await callback.message.edit_text(
        text="Просмотр расписания.\nВведите дату в формате <b>ГГГГ-ММ-ДД</b>."
    )


@admin_router.message(AdminViewScheduleStates.waiting_for_date)
async def admin_view_schedule_finish(message: Message, state: FSMContext):
    date_str = message.text.strip()
    try:
        from datetime import datetime

        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        await message.answer("Некорректная дата. Введите в формате ГГГГ-ММ-ДД.")
        return

    rows = db.get_schedule_for_date(date_str)
    await state.clear()

    if not rows:
        await message.answer(
            text=f"На дату <b>{date_str}</b> расписание отсутствует.",
            reply_markup=admin_menu_kb(),
        )
        return

    lines = [f"<b>Расписание на {date_str}</b>:"]
    for r in rows:
        time_str = r["time"]
        is_available = r["is_available"]
        booking_status = r["booking_status"]
        if booking_status == "active":
            lines.append(
                f"• {time_str} — <b>занято</b> ({r['name']}, {r['phone']}, id={r['tg_id']})"
            )
        else:
            if is_available:
                lines.append(f"• {time_str} — <b>свободно</b>")
            else:
                lines.append(f"• {time_str} — <i>недоступно</i>")

    await message.answer(
        text="\n".join(lines),
        reply_markup=admin_menu_kb(),
    )