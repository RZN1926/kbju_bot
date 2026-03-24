"""Все клавиатуры бота."""
from datetime import datetime
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import DAYS_RU, TRAIN_DAYS, MEALS_FULL, MEALS_SHORT


def kb_main() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='📅 Просмотреть данные',       callback_data='menu:view')],
        [InlineKeyboardButton(text='🗂 Правка базы',               callback_data='menu:add_product')],
        [InlineKeyboardButton(text='📝 Добавить приём пищи',      callback_data='menu:choose_day')],
        [InlineKeyboardButton(text='🧑‍🍳 Конструктор рецептов',    callback_data='menu:recipe')],  # ← NEW
    ])


def kb_days(mode: str = 'view') -> InlineKeyboardMarkup:
    today_idx = datetime.now().weekday()
    rows = []
    for i, day in enumerate(DAYS_RU):
        label = f'{day} ✦' if i == today_idx else day
        rows.append([InlineKeyboardButton(text=label, callback_data=f'{mode}_day:{i}')])
    rows.append([InlineKeyboardButton(text='🏠 Главное меню', callback_data='menu:main')])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_meals(day_idx: int, mode: str = 'view') -> InlineKeyboardMarkup:
    meals = MEALS_FULL if day_idx in TRAIN_DAYS else MEALS_SHORT
    rows = [[InlineKeyboardButton(text=m, callback_data=f'{mode}_meal:{day_idx}:{m}')]
            for m in meals]
    rows.append([InlineKeyboardButton(text='◀️ Выбрать другой день', callback_data=f'menu:choose_day')])
    rows.append([InlineKeyboardButton(text='🏠 Главное меню',        callback_data='menu:main')])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_add_method(day_idx: int, meal: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='✏️ Добавить вручную',    callback_data=f'method:manual:{day_idx}:{meal}')],
        [InlineKeyboardButton(text='🔍 Поиск по базе',       callback_data=f'method:search:{day_idx}:{meal}')],
        [InlineKeyboardButton(text='◀️ Назад',               callback_data=f'entry_day:{day_idx}')],
        [InlineKeyboardButton(text='🏠 Главное меню',        callback_data='menu:main')],
    ])


def kb_search_results(products: list[dict], day_idx: int, meal: str) -> InlineKeyboardMarkup:
    rows = []
    for p in products[:10]:
        label = f"{p['n']} ({p['k']} ккал/100г)"
        rows.append([InlineKeyboardButton(
            text=label,
            callback_data=f"pick_product:{p['id']}:{day_idx}:{meal}"
        )])
    rows.append([InlineKeyboardButton(text='◀️ Назад', callback_data=f'entry_meal:{day_idx}:{meal}')])
    rows.append([InlineKeyboardButton(text='🏠 Главное меню', callback_data='menu:main')])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_confirm(day_idx: int, meal: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text='✅ Подтвердить', callback_data='confirm:save'),
            InlineKeyboardButton(text='✏️ Изменить',    callback_data='confirm:edit'),
        ],
        [InlineKeyboardButton(text='🏠 Главное меню', callback_data='menu:main')],
    ])


def kb_edit_fields() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='🔄 Изменить всё', callback_data='edit:all')],
        [
            InlineKeyboardButton(text='🔥 Ккал',  callback_data='edit:k'),
            InlineKeyboardButton(text='🥩 Белки', callback_data='edit:b'),
        ],
        [
            InlineKeyboardButton(text='🧈 Жиры', callback_data='edit:j'),
            InlineKeyboardButton(text='🍞 Углеводы', callback_data='edit:u'),
        ],
        [InlineKeyboardButton(text='◀️ Назад',        callback_data='confirm:back')],
        [InlineKeyboardButton(text='🏠 Главное меню', callback_data='menu:main')],
    ])


def kb_back_main() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='🏠 Главное меню', callback_data='menu:main')]
    ])
