from aiogram.fsm.state import State, StatesGroup


class OrderForm(StatesGroup):
    topic = State()
    slides = State()
    deadline = State()
    plang = State()
    design = State()
    template = State()
    extras = State()
    files = State()
    contact = State()
    confirm = State()


class QuickForm(StatesGroup):
    choosing = State()  # пересланный файл → выбор объёма и срока


class RevisionForm(StatesGroup):
    collecting = State()  # текст и скриншоты, пока клиент не нажмёт «Отправить правки»


class CoverChangeForm(StatesGroup):
    text = State()


class AskForm(StatesGroup):
    text = State()


class ReceiptForm(StatesGroup):
    waiting = State()  # чек после перевода на карту


class StaffForm(StatesGroup):
    cover = State()  # ждём картинку обложки
    price = State()
    files = State()  # ждём готовые файлы
    fix = State()  # что доработать (для Claude)
