"""states.py — все FSM-состояния бота."""
from aiogram.fsm.state import State, StatesGroup


class AddProduct(StatesGroup):
    """FSM: добавление продукта в личную базу."""
    name = State()
    k    = State()
    b    = State()
    j    = State()
    u    = State()


class AddEntry(StatesGroup):
    """FSM: добавление записи о еде за день."""
    # ручной ввод
    name   = State()
    amount = State()
    k      = State()
    b      = State()
    j      = State()
    u      = State()
    # поиск по базе
    search_query  = State()
    search_weight = State()
    # редактирование поля
    edit_field = State()


class RecipeConstructor(StatesGroup):
    """FSM: умный конструктор рецептов."""
    waiting_ingredients = State()   # ждём список продуктов
    showing_results     = State()   # показываем результаты (для пагинации)
