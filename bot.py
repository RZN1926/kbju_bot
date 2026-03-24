"""Точка входа. Регистрируем все роутеры."""
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN
from handlers import start, view, add_product, add_entry, recipe   # ← добавили recipe

logging.basicConfig(
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    level=logging.INFO,
)


async def main():
    bot = Bot(token=BOT_TOKEN)
    dp  = Dispatcher(storage=MemoryStorage())

    # Порядок важен: сначала FSM-роутеры, потом общие
    dp.include_router(add_entry.router)
    dp.include_router(add_product.router)
    dp.include_router(recipe.router)       # ← новый роутер
    dp.include_router(view.router)
    dp.include_router(start.router)

    logging.info('КБЖУ-бот запущен!')
    await dp.start_polling(bot, drop_pending_updates=True)


if __name__ == '__main__':
    asyncio.run(main())
