"""Хендлеры: Правка базы — добавление и удаление личных продуктов."""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext


from states import AddProduct
from firebase_client import get_uid, add_personal_product, get_personal_products, delete_personal_product
from keyboards import kb_main, kb_back_main

router = Router()


def _num(text: str) -> float | None:
    try:
        v = float(text.replace(',', '.'))
        return v if v >= 0 else None
    except ValueError:
        return None

def product_summary(d: dict) -> str:
    return (
        f"📋 *Новый продукт*\n\n"
        f"🏷 Название: *{d['name']}*\n"
        f"🔥 Ккал/100г: *{d['k']}*\n"
        f"🥩 Белки/100г: *{d['b']}г*\n"
        f"🧈 Жиры/100г: *{d['j']}г*\n"
        f"🍞 Углев/100г: *{d['u']}г*"
    )

def kb_catalog_main() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='➕ Добавить продукт', callback_data='ap:start_add')],
        [InlineKeyboardButton(text='🗑 Удалить продукт',  callback_data='ap:start_del')],
        [InlineKeyboardButton(text='◀️ Главное меню',     callback_data='menu:main')],
    ])

def kb_product_confirm() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='✅ Подтвердить', callback_data='ap:save')],
        [InlineKeyboardButton(text='✏️ Изменить',   callback_data='ap:edit')],
        [InlineKeyboardButton(text='❌ Отмена',      callback_data='menu:add_product')],
    ])

def kb_product_edit() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='🔄 Изменить всё', callback_data='ap_edit:all')],
        [InlineKeyboardButton(text='🔥 Калории',      callback_data='ap_edit:k')],
        [InlineKeyboardButton(text='🥩 Белки',        callback_data='ap_edit:b')],
        [InlineKeyboardButton(text='🧈 Жиры',         callback_data='ap_edit:j')],
        [InlineKeyboardButton(text='🍞 Углеводы',     callback_data='ap_edit:u')],
        [InlineKeyboardButton(text='◀️ Назад',        callback_data='ap:back')],
    ])


# ── Вход в Правку базы ─────────────────────────────────────
@router.callback_query(lambda c: c.data == 'menu:add_product')
async def cb_catalog(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.clear()
    tg_id = str(call.from_user.id)
    uid   = get_uid(tg_id)
    if not uid:
        await call.message.edit_text('⚠️ Аккаунт не подключён. /start')
        return

    products = get_personal_products(uid)
    if products:
        lines = '\n'.join(
            f"  • *{p['n']}*\n"
            f"    🔥 {p['k']} ккал | Б {p['b']}г | Ж {p['j']}г | У {p['u']}г"
            for p in products
        )
        text = f"🗂 *Правка базы*\n\n*Твои продукты ({len(products)}):*\n{lines}\n\nЧто хочешь сделать?"
    else:
        text = '🗂 *Правка базы*\n\n_Личная база пуста_\n\nЧто хочешь сделать?'

    await call.message.edit_text(text, parse_mode='Markdown', reply_markup=kb_catalog_main())


# ════════════════════════════════════════════════════════════
# ДОБАВЛЕНИЕ
# ════════════════════════════════════════════════════════════
@router.callback_query(lambda c: c.data == 'ap:start_add')
async def cb_add_start(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.set_state(AddProduct.name)
    await call.message.edit_text(
        '➕ *Добавление продукта*\n\nВведи название:',
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text='❌ Отмена', callback_data='menu:add_product')
        ]])
    )

@router.message(AddProduct.name)
async def ap_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await state.set_state(AddProduct.k)
    await message.answer('🔥 Калории на 100г (ккал):')

@router.message(AddProduct.k)
async def ap_k(message: Message, state: FSMContext):
    v = _num(message.text)
    if v is None:
        await message.answer('⚠️ Введи число, например: `350`', parse_mode='Markdown'); return
    await state.update_data(k=v); await state.set_state(AddProduct.b)
    await message.answer('🥩 Белки на 100г (г):')

@router.message(AddProduct.b)
async def ap_b(message: Message, state: FSMContext):
    v = _num(message.text)
    if v is None:
        await message.answer('⚠️ Введи число', parse_mode='Markdown'); return
    await state.update_data(b=v); await state.set_state(AddProduct.j)
    await message.answer('🧈 Жиры на 100г (г):')

@router.message(AddProduct.j)
async def ap_j(message: Message, state: FSMContext):
    v = _num(message.text)
    if v is None:
        await message.answer('⚠️ Введи число', parse_mode='Markdown'); return
    await state.update_data(j=v); await state.set_state(AddProduct.u)
    await message.answer('🍞 Углеводы на 100г (г):')

@router.message(AddProduct.u)
async def ap_u(message: Message, state: FSMContext):
    v = _num(message.text)
    if v is None:
        await message.answer('⚠️ Введи число', parse_mode='Markdown'); return
    data = await state.get_data()
    await state.update_data(u=v)
    await state.set_state(None)
    await message.answer(product_summary({**data, 'u': v}), parse_mode='Markdown', reply_markup=kb_product_confirm())

@router.callback_query(lambda c: c.data == 'ap:save')
async def ap_save(call: CallbackQuery, state: FSMContext):
    await call.answer()
    data = await state.get_data()
    uid  = get_uid(str(call.from_user.id))
    add_personal_product(uid, {'n': data['name'], 'k': data['k'], 'b': data['b'], 'j': data['j'], 'u': data['u']})
    await state.clear()
    await call.message.edit_text(
        f"✅ *{data['name']}* добавлен в базу!\n🔥 {data['k']} ккал | Б {data['b']}г | Ж {data['j']}г | У {data['u']}г",
        parse_mode='Markdown', reply_markup=kb_catalog_main(),
    )

@router.callback_query(lambda c: c.data == 'ap:edit')
async def ap_edit(call: CallbackQuery):
    await call.answer()
    await call.message.edit_text('✏️ Что изменить?', reply_markup=kb_product_edit())

@router.callback_query(lambda c: c.data == 'ap:back')
async def ap_back(call: CallbackQuery, state: FSMContext):
    await call.answer()
    data = await state.get_data()
    await call.message.edit_text(product_summary(data), parse_mode='Markdown', reply_markup=kb_product_confirm())

@router.callback_query(lambda c: c.data and c.data.startswith('ap_edit:'))
async def ap_edit_field(call: CallbackQuery, state: FSMContext):
    await call.answer()
    field = call.data.split(':')[1]
    if field == 'all':
        await state.set_state(AddProduct.name)
        await call.message.edit_text('🔄 Введи название заново:', parse_mode='Markdown')
        return
    labels    = {'k': '🔥 Калории', 'b': '🥩 Белки', 'j': '🧈 Жиры', 'u': '🍞 Углеводы'}
    state_map = {'k': AddProduct.k, 'b': AddProduct.b, 'j': AddProduct.j, 'u': AddProduct.u}
    data = await state.get_data()
    await state.set_state(state_map[field])
    await call.message.edit_text(
        f"Текущее *{labels[field]}*: `{data.get(field, '?')}`\n\nВведи новое значение:",
        parse_mode='Markdown',
    )


# ════════════════════════════════════════════════════════════
# УДАЛЕНИЕ
# ════════════════════════════════════════════════════════════
@router.callback_query(lambda c: c.data == 'ap:start_del')
async def cb_del_start(call: CallbackQuery):
    await call.answer()
    uid      = get_uid(str(call.from_user.id))
    products = get_personal_products(uid)

    if not products:
        await call.message.edit_text(
            '😕 Личная база пуста — нечего удалять.',
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text='◀️ Назад', callback_data='menu:add_product')
            ]])
        )
        return

    rows = []
    for p in products:
        rows.append([InlineKeyboardButton(
            text=f"🗑 {p['n']} · {p['k']} ккал",
            callback_data=f"ap_del:{p['id']}"
        )])
    rows.append([InlineKeyboardButton(text='◀️ Назад', callback_data='menu:add_product')])
    await call.message.edit_text(
        '🗑 *Выбери продукт для удаления:*',
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )

@router.callback_query(F.data.startswith('ap_del:'))   # ← только этот префикс
async def cb_del_confirm(call: CallbackQuery):
    await call.answer()
    doc_id   = call.data.split(':', 1)[1]
    uid      = get_uid(str(call.from_user.id))
    products = get_personal_products(uid)
    product  = next((p for p in products if p['id'] == doc_id), None)
    name     = product['n'] if product else '?'

    await call.message.edit_text(
        f"🗑 Удалить *{name}* из базы?",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='✅ Да, удалить', callback_data=f'ap_del_ok:{doc_id}')],
            [InlineKeyboardButton(text='❌ Отмена',      callback_data='ap:start_del')],
        ])
    )

@router.callback_query(lambda c: c.data and c.data.startswith('ap_del_ok:'))
async def cb_del_ok(call: CallbackQuery):
    await call.answer()
    doc_id   = call.data.split(':', 1)[1]
    uid      = get_uid(str(call.from_user.id))
    products = get_personal_products(uid)
    product  = next((p for p in products if p['id'] == doc_id), None)
    name     = product['n'] if product else '?'

    delete_personal_product(uid, doc_id)
    await call.message.edit_text(
        f"✅ *{name}* удалён из базы.",
        parse_mode='Markdown',
        reply_markup=kb_catalog_main(),
    )
