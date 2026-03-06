import sqlite3
from datetime import datetime, timedelta
from typing import Optional, List, Tuple

from config import settings


class Database:
    def __init__(self, path: str):
        self.path = path
        self._init_db()

    def _connect(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        conn = self._connect()
        cur = conn.cursor()

        # Пользователи
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tg_id INTEGER UNIQUE NOT NULL,
                name TEXT,
                phone TEXT
            );
            """
        )

        # Рабочие дни
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS work_days (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT UNIQUE NOT NULL,
                is_closed INTEGER DEFAULT 0
            );
            """
        )

        # Временные слоты
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS time_slots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                day_id INTEGER NOT NULL,
                time TEXT NOT NULL,
                is_available INTEGER DEFAULT 1,
                UNIQUE(day_id, time),
                FOREIGN KEY(day_id) REFERENCES work_days(id) ON DELETE CASCADE
            );
            """
        )

        # Записи клиентов
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                day_id INTEGER NOT NULL,
                time_slot_id INTEGER NOT NULL,
                appointment_dt TEXT NOT NULL,
                status TEXT DEFAULT 'active',
                reminder_at TEXT,
                reminder_job_id TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id),
                FOREIGN KEY(day_id) REFERENCES work_days(id),
                FOREIGN KEY(time_slot_id) REFERENCES time_slots(id)
            );
            """
        )

        conn.commit()
        conn.close()

    # ---- Пользователи ----

    def get_or_create_user(self, tg_id: int) -> int:
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("SELECT id FROM users WHERE tg_id = ?", (tg_id,))
        row = cur.fetchone()
        if row:
            user_id = row["id"]
        else:
            cur.execute(
                "INSERT INTO users (tg_id) VALUES (?)",
                (tg_id,),
            )
            user_id = cur.lastrowid
            conn.commit()
        conn.close()
        return user_id

    def update_user_info(self, tg_id: int, name: str, phone: str):
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            "UPDATE users SET name = ?, phone = ? WHERE tg_id = ?",
            (name, phone, tg_id),
        )
        conn.commit()
        conn.close()

    def get_user_active_booking(self, tg_id: int) -> Optional[sqlite3.Row]:
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT b.*, wd.date, ts.time
            FROM bookings b
            JOIN users u ON b.user_id = u.id
            JOIN work_days wd ON b.day_id = wd.id
            JOIN time_slots ts ON b.time_slot_id = ts.id
            WHERE u.tg_id = ? AND b.status = 'active'
            ORDER BY b.appointment_dt ASC
            LIMIT 1
            """,
            (tg_id,),
        )
        row = cur.fetchone()
        conn.close()
        return row

    # ---- Рабочие дни и слоты ----

    def add_work_day(self, date_str: str):
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT OR IGNORE INTO work_days (date, is_closed)
            VALUES (?, 0)
            """,
            (date_str,),
        )
        conn.commit()
        conn.close()

    def close_work_day(self, date_str: str) -> List[sqlite3.Row]:
        """
        Полностью закрыть день:
        - отмечаем день закрытым
        - находим все активные записи этого дня (для уведомления)
        - делаем слоты недоступными (записи сами будут отменены отдельно)
        Возвращает список активных записей (до обновления статуса).
        """
        conn = self._connect()
        cur = conn.cursor()

        cur.execute("SELECT id FROM work_days WHERE date = ?", (date_str,))
        day_row = cur.fetchone()
        if not day_row:
            conn.close()
            return []

        day_id = day_row["id"]

        cur.execute(
            """
            SELECT b.*, u.tg_id, wd.date, ts.time
            FROM bookings b
            JOIN users u ON b.user_id = u.id
            JOIN work_days wd ON b.day_id = wd.id
            JOIN time_slots ts ON b.time_slot_id = ts.id
            WHERE b.day_id = ? AND b.status = 'active'
            """,
            (day_id,),
        )
        bookings = cur.fetchall()

        cur.execute(
            "UPDATE work_days SET is_closed = 1 WHERE id = ?",
            (day_id,),
        )
        cur.execute(
            "UPDATE time_slots SET is_available = 0 WHERE day_id = ?",
            (day_id,),
        )

        conn.commit()
        conn.close()
        return bookings

    def get_day_id(self, date_str: str) -> Optional[int]:
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("SELECT id FROM work_days WHERE date = ?", (date_str,))
        row = cur.fetchone()
        conn.close()
        if row:
            return row["id"]
        return None

    def add_time_slot(self, date_str: str, time_str: str) -> bool:
        """
        Добавляет слот (день создаётся при необходимости).
        Возвращает True, если слот создан, False — если уже существовал.
        """
        self.add_work_day(date_str)
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("SELECT id, is_closed FROM work_days WHERE date = ?", (date_str,))
        day = cur.fetchone()
        if not day or day["is_closed"]:
            conn.close()
            return False

        day_id = day["id"]
        try:
            cur.execute(
                """
                INSERT INTO time_slots (day_id, time, is_available)
                VALUES (?, ?, 1)
                """,
                (day_id, time_str),
            )
            conn.commit()
            result = True
        except sqlite3.IntegrityError:
            result = False

        conn.close()
        return result

    def delete_time_slot(self, date_str: str, time_str: str) -> bool:
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("SELECT id FROM work_days WHERE date = ?", (date_str,))
        day = cur.fetchone()
        if not day:
            conn.close()
            return False
        day_id = day["id"]

        # Проверяем наличие активной записи на этот слот
        cur.execute(
            """
            SELECT b.id
            FROM bookings b
            JOIN time_slots ts ON b.time_slot_id = ts.id
            WHERE b.day_id = ? AND ts.time = ? AND b.status = 'active'
            """,
            (day_id, time_str),
        )
        if cur.fetchone():
            conn.close()
            return False

        cur.execute(
            """
            DELETE FROM time_slots
            WHERE day_id = ? AND time = ?
            """,
            (day_id, time_str),
        )
        deleted = cur.rowcount > 0
        conn.commit()
        conn.close()
        return deleted

    def get_available_days_in_range(
        self, start_date: datetime, end_date: datetime
    ) -> List[str]:
        """
        Список дат (строкой YYYY-MM-DD), где есть хотя бы один свободный слот.
        """
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT DISTINCT wd.date
            FROM work_days wd
            JOIN time_slots ts ON ts.day_id = wd.id
            WHERE wd.is_closed = 0
              AND ts.is_available = 1
              AND DATE(wd.date) BETWEEN DATE(?) AND DATE(?)
            """,
            (start_date.date().isoformat(), end_date.date().isoformat()),
        )
        rows = cur.fetchall()
        conn.close()
        return [r["date"] for r in rows]

    def get_free_slots_for_date(self, date_str: str) -> List[str]:
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT ts.time
            FROM time_slots ts
            JOIN work_days wd ON ts.day_id = wd.id
            WHERE wd.date = ? AND wd.is_closed = 0 AND ts.is_available = 1
            ORDER BY ts.time
            """,
            (date_str,),
        )
        rows = cur.fetchall()
        conn.close()
        return [r["time"] for r in rows]

    def get_all_slots_for_date(self, date_str: str) -> List[sqlite3.Row]:
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT ts.*, wd.date
            FROM time_slots ts
            JOIN work_days wd ON ts.day_id = wd.id
            WHERE wd.date = ?
            ORDER BY ts.time
            """,
            (date_str,),
        )
        rows = cur.fetchall()
        conn.close()
        return rows

    # ---- Записи ----

    def create_booking(
        self,
        tg_id: int,
        chat_id: int,
        date_str: str,
        time_str: str,
        reminder_at: Optional[datetime],
        reminder_job_id: Optional[str],
    ) -> Optional[int]:
        """
        Создаёт запись, если:
        - у пользователя нет другой активной записи
        - слот свободен
        Возвращает ID записи или None.
        """
        conn = self._connect()
        cur = conn.cursor()

        # Проверка существующей активной записи
        cur.execute(
            """
            SELECT b.id
            FROM bookings b
            JOIN users u ON b.user_id = u.id
            WHERE u.tg_id = ? AND b.status = 'active'
            """,
            (tg_id,),
        )
        if cur.fetchone():
            conn.close()
            return None

        # Получаем или создаём пользователя
        cur.execute("SELECT id FROM users WHERE tg_id = ?", (tg_id,))
        user_row = cur.fetchone()
        if user_row:
            user_id = user_row["id"]
        else:
            cur.execute(
                "INSERT INTO users (tg_id) VALUES (?)",
                (tg_id,),
            )
            user_id = cur.lastrowid

        # Получаем день и слот
        cur.execute("SELECT id, is_closed FROM work_days WHERE date = ?", (date_str,))
        day = cur.fetchone()
        if not day or day["is_closed"]:
            conn.close()
            return None
        day_id = day["id"]

        cur.execute(
            """
            SELECT id, is_available
            FROM time_slots
            WHERE day_id = ? AND time = ?
            """,
            (day_id, time_str),
        )
        slot = cur.fetchone()
        if not slot or not slot["is_available"]:
            conn.close()
            return None
        time_slot_id = slot["id"]

        appointment_dt = datetime.fromisoformat(f"{date_str} {time_str}")
        created_at = datetime.now()
        reminder_at_str = reminder_at.isoformat() if reminder_at else None

        # Создаём запись
        cur.execute(
            """
            INSERT INTO bookings (
                user_id, chat_id, day_id, time_slot_id,
                appointment_dt, status,
                reminder_at, reminder_job_id,
                created_at
            ) VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?)
            """,
            (
                user_id,
                chat_id,
                day_id,
                time_slot_id,
                appointment_dt.isoformat(),
                reminder_at_str,
                reminder_job_id,
                created_at.isoformat(),
            ),
        )
        booking_id = cur.lastrowid

        # Делаем слот недоступным
        cur.execute(
            "UPDATE time_slots SET is_available = 0 WHERE id = ?",
            (time_slot_id,),
        )

        conn.commit()
        conn.close()
        return booking_id

    def cancel_booking_by_user(self, tg_id: int) -> Optional[Tuple[int, str, str, str]]:
        """
        Отмена записи пользователем.
        Возвращает (booking_id, date_str, time_str, reminder_job_id) или None.
        """
        conn = self._connect()
        cur = conn.cursor()

        cur.execute(
            """
            SELECT b.id, b.day_id, b.time_slot_id, b.reminder_job_id,
                   wd.date, ts.time
            FROM bookings b
            JOIN users u ON b.user_id = u.id
            JOIN work_days wd ON b.day_id = wd.id
            JOIN time_slots ts ON b.time_slot_id = ts.id
            WHERE u.tg_id = ? AND b.status = 'active'
            """,
            (tg_id,),
        )
        row = cur.fetchone()
        if not row:
            conn.close()
            return None

        booking_id = row["id"]
        day_id = row["day_id"]
        time_slot_id = row["time_slot_id"]
        reminder_job_id = row["reminder_job_id"]
        date_str = row["date"]
        time_str = row["time"]

        # Отменяем запись и освобождаем слот
        cur.execute(
            "UPDATE bookings SET status = 'cancelled_by_user' WHERE id = ?",
            (booking_id,),
        )
        cur.execute(
            "UPDATE time_slots SET is_available = 1 WHERE id = ?",
            (time_slot_id,),
        )

        conn.commit()
        conn.close()
        return booking_id, date_str, time_str, reminder_job_id

    def cancel_booking_by_id(self, booking_id: int, new_status: str) -> Optional[str]:
        """
        Отмена записи по ID (для админа / закрытия дня).
        Возвращает reminder_job_id или None.
        """
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT b.id, b.time_slot_id, b.reminder_job_id
            FROM bookings b
            WHERE b.id = ? AND b.status = 'active'
            """,
            (booking_id,),
        )
        row = cur.fetchone()
        if not row:
            conn.close()
            return None

        time_slot_id = row["time_slot_id"]
        reminder_job_id = row["reminder_job_id"]

        cur.execute(
            "UPDATE bookings SET status = ? WHERE id = ?",
            (new_status, booking_id),
        )
        cur.execute(
            "UPDATE time_slots SET is_available = 1 WHERE id = ?",
            (time_slot_id,),
        )

        conn.commit()
        conn.close()
        return reminder_job_id

    def get_future_bookings_with_reminders(self) -> List[sqlite3.Row]:
        """
        Все будущие активные записи, у которых reminder_at ещё не был.
        """
        now = datetime.now().isoformat()
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT b.*, u.tg_id, wd.date, ts.time
            FROM bookings b
            JOIN users u ON b.user_id = u.id
            JOIN work_days wd ON b.day_id = wd.id
            JOIN time_slots ts ON b.time_slot_id = ts.id
            WHERE b.status = 'active'
              AND b.reminder_at IS NOT NULL
              AND b.reminder_at > ?
            """,
            (now,),
        )
        rows = cur.fetchall()
        conn.close()
        return rows

    def get_schedule_for_date(self, date_str: str) -> List[sqlite3.Row]:
        """
        Возвращает все слоты и информацию о записях на выбранную дату.
        """
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT ts.time,
                   ts.is_available,
                   b.status AS booking_status,
                   u.tg_id,
                   u.name,
                   u.phone
            FROM time_slots ts
            JOIN work_days wd ON ts.day_id = wd.id
            LEFT JOIN bookings b ON b.time_slot_id = ts.id
                                   AND b.status = 'active'
            LEFT JOIN users u ON b.user_id = u.id
            WHERE wd.date = ?
            ORDER BY ts.time
            """,
            (date_str,),
        )
        rows = cur.fetchall()
        conn.close()
        return rows
