from datetime import datetime, timedelta, date
import calendar

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


class CalendarCallback(CallbackData, prefix="cal"):
    action: str  # "DAY" или "NAVIGATE"
    year: int
    month: int
    day: int


def get_month_calendar(
    year: int,
    month: int,
    min_date: date,
    max_date: date,
) -> InlineKeyboardMarkup:
    """
    Строит календарь на месяц с ограничением по диапазону.
    """
    kb = []

    month_name = datetime(year, month, 1).strftime("%B %Y")
    kb.append(
        [
            InlineKeyboardButton(
                text=f"{month_name}",
                callback_data="cal_ignore",
            )
        ]
    )

    # Дни недели
    week_days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    kb.append(
        [InlineKeyboardButton(text=d, callback_data="cal_ignore") for d in week_days]
    )

    cal = calendar.Calendar(firstweekday=0)  # Пн
    for week in cal.monthdatescalendar(year, month):
        row = []
        for d in week:
            if d.month != month:
                # Пустые клетки для соседних месяцев
                row.append(
                    InlineKeyboardButton(
                        text=" ",
                        callback_data="cal_ignore",
                    )
                )
                continue

            if d < min_date or d > max_date:
                row.append(
                    InlineKeyboardButton(
                        text=str(d.day),
                        callback_data="cal_ignore",
                    )
                )
            else:
                row.append(
                    InlineKeyboardButton(
                        text=str(d.day),
                        callback_data=CalendarCallback(
                            action="DAY", year=d.year, month=d.month, day=d.day
                        ).pack(),
                    )
                )
        kb.append(row)

    # Кнопки навигации по месяцам
    prev_month = (datetime(year, month, 15) - timedelta(days=31)).date()
    next_month = (datetime(year, month, 15) + timedelta(days=31)).date()

    nav_row = []

    if prev_month >= min_date.replace(day=1):
        nav_row.append(
            InlineKeyboardButton(
                text="«",
                callback_data=CalendarCallback(
                    action="NAVIGATE",
                    year=prev_month.year,
                    month=prev_month.month,
                    day=1,
                ).pack(),
            )
        )
    else:
        nav_row.append(
            InlineKeyboardButton(
                text=" ",
                callback_data="cal_ignore",
            )
        )

    nav_row.append(
        InlineKeyboardButton(
            text="Закрыть",
            callback_data="cal_close",
        )
    )

    if next_month <= max_date.replace(day=1):
        nav_row.append(
            InlineKeyboardButton(
                text="»",
                callback_data=CalendarCallback(
                    action="NAVIGATE",
                    year=next_month.year,
                    month=next_month.month,
                    day=1,
                ).pack(),
            )
        )
    else:
        nav_row.append(
            InlineKeyboardButton(
                text=" ",
                callback_data="cal_ignore",
            )
        )

    kb.append(nav_row)

    return InlineKeyboardMarkup(inline_keyboard=kb)


def booking_calendar_kb() -> InlineKeyboardMarkup:
    today = date.today()
    max_day = today + timedelta(days=30)

    return get_month_calendar(
        year=today.year,
        month=today.month,
        min_date=today,
        max_date=max_day,
    )