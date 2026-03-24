"""Хендлеры: просмотр данных за день — все приёмы сразу."""
from datetime import datetime, timedelta
from aiogram import Router
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from config import DAYS_RU, MEALS_FULL, MEALS_SHORT, TRAIN_DAYS
from firebase_client import get_uid, get_day_data
from keyboards import kb_days

router = Router()


def day_key_from_idx(day_idx: int) -> str:
    today     = datetime.now().date()
    today_idx = today.weekday()
    return (today + timedelta(days=day_idx - today_idx)).isoformat()

def fmt1(n: float) -> str:
    v = round(n * 10) / 10
    return str(int(v)) if v == int(v) else str(v)


@router.callback_query(lambda c: c.data and c.data.startswith('view_day:'))
async def cb_view_day(call: CallbackQuery):
    await call.answer()
    day_idx  = int(call.data.split(':')[1])
    tg_id    = str(call.from_user.id)
    uid      = get_uid(tg_id)

    if not uid:
        await call.message.edit_text('⚠️ Аккаунт не подключён. /start')
        return

    day_key  = day_key_from_idx(day_idx)
    day_data = get_day_data(uid, day_key)
    day_name = DAYS_RU[day_idx]
    meals    = MEALS_FULL if day_idx in TRAIN_DAYS else MEALS_SHORT

    # Считаем общий итог за день
    total_k = total_b = total_j = total_u = 0.0
    lines = [f'📅 *{day_name}* · `{day_key}`\n']
    has_data = False

    for meal in meals:
        entries = day_data.get(meal, [])
        if not entries:
            continue
        has_data = True
        mk = mb = mj = mu = 0.0
        lines.append(f'*{meal}*')
        for e in entries:
            mk += e.get('k', 0); mb += e.get('b', 0)
            mj += e.get('j', 0); mu += e.get('u', 0)
            lines.append(
                f"  • {e['name']} {e.get('amount','?')}г\n" 
                f"   🔥{round(e.get('k',0))} Б{fmt1(e.get('b',0))} Ж{fmt1(e.get('j',0))} У{fmt1(e.get('u',0))}\n"
            )
        lines.append(f"  _итого: {round(mk)} ккал | Б{fmt1(mb)} Ж{fmt1(mj)} У{fmt1(mu)}_\n\n")
        total_k += mk; total_b += mb; total_j += mj; total_u += mu

    if not has_data:
        lines.append('_Записей пока нет._')
    else:
        lines.append(
            f'📊 *День итого:*\n'
            f'🔥 {round(total_k)} ккал | Б {fmt1(total_b)}г | Ж {fmt1(total_j)}г | У {fmt1(total_u)}г'
        )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='◀️ Выбрать другой день', callback_data='menu:view')],
        [InlineKeyboardButton(text='🏠 Главное меню',        callback_data='menu:main')],
    ])
    await call.message.edit_text('\n'.join(lines), parse_mode='Markdown', reply_markup=kb)
