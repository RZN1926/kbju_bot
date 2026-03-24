"""Хендлеры: /start, /uid, /disconnect, главное меню."""
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery

from firebase_client import get_uid, set_uid, remove_uid
from keyboards import kb_main, kb_days

router = Router()


@router.message(Command('start'))
async def cmd_start(message: Message):
    tg_id = str(message.from_user.id)
    name  = message.from_user.first_name or 'друг'

    if not get_uid(tg_id):
        await message.answer(
            f'👋 Привет, *{name}*!\n\n'
            'Я помогу трекать КБЖУ прямо в Telegram — '
            'данные синхронизируются с сайтом.\n\n'
            '🔑 Чтобы начать:\n'
            '1. Открой [сайт](https://rzn1926.github.io/my_kbju/) → войди через Google\n'
            '2. В левом верхнем углу скопируй UID\n'
            '3. Отправь мне: `/uid ТВОЙ_UID`',
            parse_mode='Markdown',
            disable_web_page_preview=True,
        )
        return

    await message.answer(
        f'👋 Привет, *{name}*! Что делаем?',
        parse_mode='Markdown',
        reply_markup=kb_main(),
    )


@router.message(Command('uid'))
async def cmd_uid(message: Message):
    tg_id = str(message.from_user.id)
    args  = message.text.split(maxsplit=1)
    if len(args) < 2 or not args[1].strip():
        await message.answer('Использование: `/uid ТВОЙ_FIREBASE_UID`', parse_mode='Markdown')
        return

    uid  = args[1].strip()
    name = message.from_user.first_name or 'друг'
    set_uid(tg_id, uid)
    await message.answer(
        f'✅ *Аккаунт подключён!* Привет, *{name}*!\n\nЧто делаем?',
        parse_mode='Markdown',
        reply_markup=kb_main(),
    )


@router.message(Command('disconnect'))
async def cmd_disconnect(message: Message):
    remove_uid(str(message.from_user.id))
    await message.answer('✅ Аккаунт отвязан. /start — подключить снова.')


@router.message(Command('menu'))
async def cmd_menu(message: Message):
    tg_id = str(message.from_user.id)
    if not get_uid(tg_id):
        await message.answer('⚠️ Сначала подключи аккаунт: /start')
        return
    await message.answer('Что делаем?', reply_markup=kb_main())


# ── Inline: главное меню ───────────────────────────────────
@router.callback_query(lambda c: c.data == 'menu:main')
async def cb_main(call: CallbackQuery):
    await call.answer()
    await call.message.edit_text('Что делаем?', reply_markup=kb_main())


@router.callback_query(lambda c: c.data == 'menu:view')
async def cb_menu_view(call: CallbackQuery):
    await call.answer()
    await call.message.edit_text('📅 Выбери день для просмотра:', reply_markup=kb_days(mode='view'))


@router.callback_query(lambda c: c.data == 'menu:choose_day')
async def cb_menu_choose_day(call: CallbackQuery):
    await call.answer()
    tg_id = str(call.from_user.id)
    if not get_uid(tg_id):
        await call.message.edit_text('⚠️ Аккаунт не подключён. /start')
        return
    await call.message.edit_text('📝 Выбери день:', reply_markup=kb_days(mode='entry'))
