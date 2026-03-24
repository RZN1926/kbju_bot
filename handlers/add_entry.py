"""Хендлеры: добавление приёма пищи."""
from datetime import datetime, timedelta

from aiogram import Router
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from states import AddEntry
from config import DAYS_RU, BUILTIN_DB, MEALS_FULL, MEALS_SHORT, TRAIN_DAYS
from firebase_client import get_uid, get_personal_products, save_entry, get_day_data
from keyboards import (
    kb_meals, kb_add_method, kb_search_results,
    kb_confirm, kb_edit_fields, kb_back_main,
)

router = Router()


# ── Утилиты ────────────────────────────────────────────────

def day_key_from_idx(day_idx: int) -> str:
    today     = datetime.now().date()
    today_idx = today.weekday()
    return (today + timedelta(days=day_idx - today_idx)).isoformat()


def fmt1(n: float) -> str:
    v = round(n * 10) / 10
    return str(int(v)) if v == int(v) else str(v)


def _num(text: str) -> float | None:
    try:
        v = float(text.replace(',', '.'))
        return v if v >= 0 else None
    except ValueError:
        return None


def entry_summary(d: dict) -> str:
    return (
        f"📋 *Запись*\n\n"
        f"🏷 {d['name']} — {d['amount']}г\n"
        f"🔥 Ккал: *{round(d['k'])}*\n"
        f"🥩 Белки: *{round(d['b'], 1)}г*\n"
        f"🧈 Жиры: *{round(d['j'], 1)}г*\n"
        f"🍞 Углев: *{round(d['u'], 1)}г*"
    )


def day_summary_text(day_idx: int, uid: str, header: str) -> str:
    """Возвращает текст с детальной сводкой за день."""
    day_key  = day_key_from_idx(day_idx)
    day_data = get_day_data(uid, day_key)
    meals    = MEALS_FULL if day_idx in TRAIN_DAYS else MEALS_SHORT

    total_k = total_b = total_j = total_u = 0.0
    lines    = [header]
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
                f"  • {e['name']} {e.get('amount', '?')}г\n"
                f"   🔥{round(e.get('k', 0))} Б{fmt1(e.get('b', 0))} Ж{fmt1(e.get('j', 0))} У{fmt1(e.get('u', 0))}\n"
            )
        lines.append(f"  _итого: {round(mk)} ккал | Б{fmt1(mb)} Ж{fmt1(mj)} У{fmt1(mu)}_\n\n")
        total_k += mk; total_b += mb; total_j += mj; total_u += mu

    if has_data:
        lines.append(
            f'📊 *День итого:*\n'
            f'🔥 {round(total_k)} ккал | Б {fmt1(total_b)}г | Ж {fmt1(total_j)}г | У {fmt1(total_u)}г'
        )
    else:
        lines.append('_Записей пока нет_')

    return '\n'.join(lines)


def get_all_products(uid: str) -> list[dict]:
    builtin  = [{'id': f'b_{i}', **p} for i, p in enumerate(BUILTIN_DB)]
    personal = get_personal_products(uid)
    return builtin + personal


# ── 1. Выбор дня ───────────────────────────────────────────

@router.callback_query(lambda c: c.data and c.data.startswith('entry_day:'))
async def cb_entry_day(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.clear()
    day_idx  = int(call.data.split(':')[1])
    day_name = DAYS_RU[day_idx]
    uid      = get_uid(str(call.from_user.id))
    await state.update_data(day_idx=day_idx)

    text = day_summary_text(
        day_idx, uid,
        header=f'📝 *{day_name}* — выбери приём пищи:\n',
    )
    await call.message.edit_text(
        text,
        parse_mode='Markdown',
        reply_markup=kb_meals(day_idx, mode='entry'),
    )


# ── 2. Выбор приёма пищи ───────────────────────────────────

@router.callback_query(lambda c: c.data and c.data.startswith('entry_meal:'))
async def cb_entry_meal(call: CallbackQuery, state: FSMContext):
    await call.answer()
    _, day_idx_s, meal = call.data.split(':', 2)
    day_idx = int(day_idx_s)
    await state.update_data(day_idx=day_idx, meal=meal)
    await call.message.edit_text(
        f'Как добавить продукт в *{meal}*?',
        parse_mode='Markdown',
        reply_markup=kb_add_method(day_idx, meal),
    )


# ── 3a. Ручной ввод ────────────────────────────────────────

@router.callback_query(lambda c: c.data and c.data.startswith('method:manual:'))
async def cb_method_manual(call: CallbackQuery, state: FSMContext):
    await call.answer()
    parts   = call.data.split(':')
    day_idx = int(parts[2])
    meal    = parts[3]
    await state.update_data(day_idx=day_idx, meal=meal)
    await state.set_state(AddEntry.name)
    await call.message.edit_text(
        '✏️ Введи название продукта:',
        reply_markup=kb_back_main(),
    )


@router.message(AddEntry.name)
async def ae_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await state.set_state(AddEntry.amount)
    await message.answer('⚖️ Введи вес (г):', reply_markup=kb_back_main())


@router.message(AddEntry.amount)
async def ae_amount(message: Message, state: FSMContext):
    v = _num(message.text)
    if v is None or v <= 0:
        await message.answer('⚠️ Введи число больше 0', reply_markup=kb_back_main())
        return
    await state.update_data(amount=v)
    await state.set_state(AddEntry.k)
    await message.answer('🔥 Ккал на 100г:', reply_markup=kb_back_main())


@router.message(AddEntry.k)
async def ae_k(message: Message, state: FSMContext):
    v = _num(message.text)
    if v is None:
        await message.answer('⚠️ Введи число', reply_markup=kb_back_main())
        return
    data = await state.get_data()
    await state.update_data(k=round(v * data['amount'] / 100, 1))
    await state.set_state(AddEntry.b)
    await message.answer('🥩 Белки на 100г:', reply_markup=kb_back_main())


@router.message(AddEntry.b)
async def ae_b(message: Message, state: FSMContext):
    v = _num(message.text)
    if v is None:
        await message.answer('⚠️ Введи число', reply_markup=kb_back_main())
        return
    data = await state.get_data()
    await state.update_data(b=round(v * data['amount'] / 100, 1))
    await state.set_state(AddEntry.j)
    await message.answer('🧈 Жиры на 100г:', reply_markup=kb_back_main())


@router.message(AddEntry.j)
async def ae_j(message: Message, state: FSMContext):
    v = _num(message.text)
    if v is None:
        await message.answer('⚠️ Введи число', reply_markup=kb_back_main())
        return
    data = await state.get_data()
    await state.update_data(j=round(v * data['amount'] / 100, 1))
    await state.set_state(AddEntry.u)
    await message.answer('🍞 Углеводы на 100г:', reply_markup=kb_back_main())


@router.message(AddEntry.u)
async def ae_u(message: Message, state: FSMContext):
    v = _num(message.text)
    if v is None:
        await message.answer('⚠️ Введи число', reply_markup=kb_back_main())
        return
    data = await state.get_data()
    await state.update_data(u=round(v * data['amount'] / 100, 1))
    await state.set_state(None)
    full = await state.get_data()
    await message.answer(
        entry_summary(full),
        parse_mode='Markdown',
        reply_markup=kb_confirm(full['day_idx'], full['meal']),
    )


# ── 3b. Поиск по базе ──────────────────────────────────────

@router.callback_query(lambda c: c.data and c.data.startswith('method:search:'))
async def cb_method_search(call: CallbackQuery, state: FSMContext):
    await call.answer()
    parts   = call.data.split(':')
    day_idx = int(parts[2])
    meal    = parts[3]
    await state.update_data(day_idx=day_idx, meal=meal)
    await state.set_state(AddEntry.search_query)
    await call.message.edit_text(
        '🔍 Введи название для поиска:',
        reply_markup=kb_back_main(),
    )


@router.message(AddEntry.search_query)
async def ae_search_query(message: Message, state: FSMContext):
    query   = message.text.strip().lower()
    data    = await state.get_data()
    uid     = get_uid(str(message.from_user.id))
    results = [p for p in get_all_products(uid) if query in p['n'].lower()]

    if not results:
        await message.answer(
            '😕 Ничего не найдено. Попробуй другой запрос.',
            reply_markup=kb_back_main(),
        )
        return

    await state.set_state(None)
    await message.answer(
        f'🔍 Найдено {len(results[:10])} продуктов:',
        reply_markup=kb_search_results(results, data['day_idx'], data['meal']),
    )


@router.callback_query(lambda c: c.data and c.data.startswith('pick_product:'))
async def cb_pick_product(call: CallbackQuery, state: FSMContext):
    await call.answer()
    parts   = call.data.split(':')
    prod_id = parts[1]
    day_idx = int(parts[2])
    meal    = parts[3]

    uid      = get_uid(str(call.from_user.id))
    products = get_all_products(uid)
    product  = next((p for p in products if p['id'] == prod_id), None)

    if not product:
        await call.message.edit_text('⚠️ Продукт не найден.', reply_markup=kb_back_main())
        return

    await state.update_data(day_idx=day_idx, meal=meal, _product=product)
    await state.set_state(AddEntry.search_weight)
    await call.message.edit_text(
        f'📦 *{product["n"]}*\n{product["k"]} ккал / 100г\n\nВведи вес (г):',
        parse_mode='Markdown',
        reply_markup=kb_back_main(),
    )


@router.message(AddEntry.search_weight)
async def ae_search_weight(message: Message, state: FSMContext):
    v = _num(message.text)
    if v is None or v <= 0:
        await message.answer('⚠️ Введи число больше 0', reply_markup=kb_back_main())
        return

    data    = await state.get_data()
    p       = data['_product']
    amount  = v
    entry_d = {
        'name':   p['n'],
        'amount': amount,
        'k': round(p['k'] * amount / 100, 1),
        'b': round(p['b'] * amount / 100, 1),
        'j': round(p['j'] * amount / 100, 1),
        'u': round(p['u'] * amount / 100, 1),
    }
    await state.update_data(**entry_d)
    await state.set_state(None)
    full = await state.get_data()
    await message.answer(
        entry_summary(entry_d),
        parse_mode='Markdown',
        reply_markup=kb_confirm(full['day_idx'], full['meal']),
    )


# ── 4. Подтверждение ───────────────────────────────────────

@router.callback_query(lambda c: c.data == 'confirm:save')
async def cb_confirm_save(call: CallbackQuery, state: FSMContext):
    await call.answer()
    data    = await state.get_data()
    uid     = get_uid(str(call.from_user.id))
    day_key = day_key_from_idx(data['day_idx'])
    entry   = {k: data[k] for k in ('name', 'amount', 'k', 'b', 'j', 'u')}
    save_entry(uid, day_key, data['meal'], entry)
    await state.clear()
    await call.message.edit_text(
        f'✅ Записано!\n\n{entry_summary(entry)}',
        parse_mode='Markdown',
        reply_markup=kb_back_main(),
    )


@router.callback_query(lambda c: c.data == 'confirm:edit')
async def cb_confirm_edit(call: CallbackQuery):
    await call.answer()
    await call.message.edit_text('✏️ Что изменить?', reply_markup=kb_edit_fields())


@router.callback_query(lambda c: c.data == 'confirm:back')
async def cb_confirm_back(call: CallbackQuery, state: FSMContext):
    await call.answer()
    data = await state.get_data()
    await call.message.edit_text(
        entry_summary(data),
        parse_mode='Markdown',
        reply_markup=kb_confirm(data['day_idx'], data['meal']),
    )


# ── 5. Редактирование отдельного поля ──────────────────────

@router.callback_query(lambda c: c.data and c.data.startswith('edit:'))
async def cb_edit_field(call: CallbackQuery, state: FSMContext):
    await call.answer()
    field = call.data.split(':')[1]

    if field == 'all':
        await state.set_state(AddEntry.name)
        await call.message.edit_text('🔄 Введи название заново:', reply_markup=kb_back_main())
        return

    data   = await state.get_data()
    labels = {'k': '🔥 Ккал', 'b': '🥩 Белки', 'j': '🧈 Жиры', 'u': '🍞 Углеводы'}
    await state.update_data(_edit_field=field)
    await state.set_state(AddEntry.edit_field)
    await call.message.edit_text(
        f"Текущее *{labels[field]}*: `{data.get(field, '?')}`\n\n"
        f"Введи новое значение (для {data.get('amount', '?')}г):",
        parse_mode='Markdown',
        reply_markup=kb_back_main(),
    )


@router.message(AddEntry.edit_field)
async def ae_edit_field(message: Message, state: FSMContext):
    v = _num(message.text)
    if v is None:
        await message.answer('⚠️ Введи число', reply_markup=kb_back_main())
        return
    data  = await state.get_data()
    field = data['_edit_field']
    await state.update_data(**{field: v})
    await state.set_state(None)
    full = await state.get_data()
    await message.answer(
        entry_summary(full),
        parse_mode='Markdown',
        reply_markup=kb_confirm(full['day_idx'], full['meal']),
    )
