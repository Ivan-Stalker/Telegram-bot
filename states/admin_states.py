from aiogram.fsm.state import StatesGroup, State


class AdminAddDayStates(StatesGroup):
    waiting_for_date = State()


class AdminAddSlotStates(StatesGroup):
    waiting_for_date = State()
    waiting_for_time = State()


class AdminDeleteSlotStates(StatesGroup):
    waiting_for_date = State()
    waiting_for_time = State()


class AdminCloseDayStates(StatesGroup):
    waiting_for_date = State()


class AdminCancelBookingStates(StatesGroup):
    waiting_for_booking_id = State()


class AdminViewScheduleStates(StatesGroup):
    waiting_for_date = State()