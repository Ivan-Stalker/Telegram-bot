from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot

from database import Database
from config import settings


scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
db = Database(settings.DB_PATH)


async def send_reminder(bot: Bot, chat_id: int, time_str: str):
    """
    Отправка напоминания пользователю.
    """
    text = (
        f"Напоминаем, что вы записаны на наращивание ресниц завтра в {time_str}.\n"
        f"Ждём вас ❤️"
    )
    await bot.send_message(chat_id=chat_id, text=text)


def schedule_reminder_for_booking(
    bot: Bot,
    booking_id: int,
    chat_id: int,
    date_str: str,
    time_str: str,
) -> str:
    """
    Планирует напоминание за 24 часа до записи (если возможно).
    Возвращает reminder_job_id (можно сохранить в БД).
    """
    appointment_dt = datetime.fromisoformat(f"{date_str} {time_str}")
    reminder_dt = appointment_dt - timedelta(days=1)
    now = datetime.now()

    # Если до записи меньше 24 часов — не создаём напоминание
    if reminder_dt <= now:
        return ""

    job_id = f"reminder_{booking_id}"
    scheduler.add_job(
        send_reminder,
        trigger="date",
        run_date=reminder_dt,
        id=job_id,
        replace_existing=True,
        kwargs={
            "bot": bot,
            "chat_id": chat_id,
            "time_str": time_str,
        },
    )
    return job_id


def remove_reminder_job(job_id: str):
    if not job_id:
        return
    try:
        scheduler.remove_job(job_id)
    except Exception:
        # Работа могла уже выполниться или не быть созданной — это не критично
        pass


async def restore_all_reminders(bot: Bot):
    """
    Восстанавливает все будущие напоминания при старте бота.
    """
    rows = db.get_future_bookings_with_reminders()
    for row in rows:
        booking_id = row["id"]
        chat_id = row["chat_id"]
        date_str = row["date"]
        time_str = row["time"]
        reminder_at = datetime.fromisoformat(row["reminder_at"])
        now = datetime.now()
        if reminder_at <= now:
            continue

        job_id = f"reminder_{booking_id}"
        scheduler.add_job(
            send_reminder,
            trigger="date",
            run_date=reminder_at,
            id=job_id,
            replace_existing=True,
            kwargs={
                "bot": bot,
                "chat_id": chat_id,
                "time_str": time_str,
            },
        )
