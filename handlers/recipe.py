"""
handlers/recipe.py
~~~~~~~~~~~~~~~~~~
Хендлер «AI-конструктор рецептов».

Точки входа:
  - callback_data == 'menu:recipe'       (кнопка в главном меню)
  - callback_data == 'recipe:retry'      (ввести продукты заново)
  - callback_data == 'recipe:regen'      (перегенерировать с теми же продуктами)

FSM: RecipeConstructor.waiting_ingredients → showing_results.
"""
from __future__ import annotations

import logging
import os
from typing import Any

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from firebase_client import get_uid, get_personal_products
from recipe_engine import (
    format_not_found,
    format_recipe,
    generate_ai_recipe,
    match_ingredients,
    parse_ingredients,
)
from states import RecipeConstructor

log = logging.getLogger(__name__)
router = Router()

# ── Настройки AI-провайдера (читаем из переменных окружения) ─────────────────
#
#  Рекомендуемый бесплатный стек:
#
#  1. OpenRouter — самый простой старт, много бесплатных моделей:
#       AI_BASE_URL = https://openrouter.ai/api/v1
#       AI_MODEL    = google/gemma-3-12b-it:free
#                  или meta-llama/llama-3.1-8b-instruct:free
#       Регистрация: https://openrouter.ai  (ключ вида sk-or-v1-...)
#
#  2. Groq — быстрее, выше лимиты на бесплатном тире:
#       AI_BASE_URL = https://api.groq.com/openai/v1
#       AI_MODEL    = llama-3.3-70b-versatile
#                  или llama3-8b-8192
#       Регистрация: https://console.groq.com  (ключ вида gsk_...)
#
_AI_API_KEY  = os.environ.get("AI_API_KEY", "")
_AI_BASE_URL = os.environ.get("AI_BASE_URL", "https://openrouter.ai/api/v1")
_AI_MODEL    = os.environ.get("AI_MODEL",    "google/gemma-3-12b-it:free")


# ─────────────────────────────────────────────────────────────────────────────
# Клавиатуры
# ─────────────────────────────────────────────────────────────────────────────

def kb_recipe_result() -> InlineKeyboardMarkup:
    """Клавиатура после показа рецепта."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔁 Другой рецепт из тех же продуктов", callback_data="recipe:regen")],
        [InlineKeyboardButton(text="🔄 Ввести другие продукты",            callback_data="recipe:retry")],
        [InlineKeyboardButton(text="🏠 Главное меню",                      callback_data="menu:main")],
    ])


def kb_recipe_enter() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="menu:main")]
    ])


def kb_recipe_error() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Попробовать ещё раз", callback_data="recipe:retry")],
        [InlineKeyboardButton(text="🏠 Главное меню",        callback_data="menu:main")],
    ])


# ─────────────────────────────────────────────────────────────────────────────
# Точки входа
# ─────────────────────────────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data == "menu:recipe")
async def cb_recipe_enter(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    await state.clear()
    await state.set_state(RecipeConstructor.waiting_ingredients)
    await call.message.edit_text(
        "🧑‍🍳 *AI-конструктор рецептов*\n\n"
        "Напиши продукты, которые у тебя есть, через запятую:\n\n"
        "_Например: куриная грудь, гречка, помидоры, сыр_",
        parse_mode="Markdown",
        reply_markup=kb_recipe_enter(),
    )


@router.callback_query(lambda c: c.data == "recipe:retry")
async def cb_recipe_retry(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    await state.clear()
    await state.set_state(RecipeConstructor.waiting_ingredients)
    await call.message.edit_text(
        "🔄 *Введи другие продукты:*\n\n"
        "_Перечисли через запятую, например: яйца, творог, кефир_",
        parse_mode="Markdown",
        reply_markup=kb_recipe_enter(),
    )


@router.callback_query(lambda c: c.data == "recipe:regen")
async def cb_recipe_regen(call: CallbackQuery, state: FSMContext) -> None:
    """Перегенерировать рецепт с теми же продуктами (другая идея от ИИ)."""
    await call.answer()
    data = await state.get_data()
    matched: list[str] = data.get("matched_products", [])
    personal: list[dict] = data.get("personal_products", [])

    if not matched:
        await call.message.edit_text(
            "⚠️ Сессия истекла. Введи продукты заново.",
            reply_markup=kb_recipe_error(),
        )
        return

    await call.message.edit_text("⏳ Генерирую новый рецепт…", parse_mode="Markdown")
    await _run_ai_and_reply(call.message, state, matched, personal, edit=True)


# ─────────────────────────────────────────────────────────────────────────────
# Обработка ввода ингредиентов
# ─────────────────────────────────────────────────────────────────────────────

@router.message(RecipeConstructor.waiting_ingredients)
async def msg_ingredients(message: Message, state: FSMContext) -> None:
    """
    Пользователь ввёл список продуктов.
    1. Парсим и матчим с NUTRIENT_DB + личной базой
    2. Отправляем в AI, получаем рецепт
    3. Верифицируем КБЖУ по нашей БД
    4. Отображаем результат
    """
    raw_text = message.text or ""
    thinking_msg = await message.answer("⏳ Подбираю рецепт с помощью AI…")

    try:
        tg_id = str(message.from_user.id)
        uid   = get_uid(tg_id)

        personal_products: list[dict] = []
        if uid:
            try:
                personal_products = get_personal_products(uid)
            except Exception:
                log.warning("Не удалось загрузить личную базу uid=%s", uid)

        raw_list = parse_ingredients(raw_text)
        matched, unmatched = match_ingredients(raw_list, extra_db=personal_products)

        if not matched:
            await thinking_msg.delete()
            await message.answer(
                format_not_found(unmatched) if unmatched
                else "😕 Не смог распознать ни одного продукта. Попробуй написать иначе.",
                parse_mode="Markdown",
                reply_markup=kb_recipe_error(),
            )
            await state.clear()
            return

        # Сохраняем продукты в FSM (для перегенерации)
        await state.update_data(matched_products=matched, personal_products=personal_products)
        await state.set_state(RecipeConstructor.showing_results)

        await thinking_msg.delete()
        status_msg = await message.answer("🤖 AI придумывает рецепт…")

        await _run_ai_and_reply(status_msg, state, matched, personal_products,
                                unmatched=unmatched, edit=True)

    except Exception as exc:
        log.exception("Ошибка в обработчике рецептов: %s", exc)
        try:
            await thinking_msg.delete()
        except Exception:
            pass
        await message.answer(
            "❌ Не удалось связаться с AI. Попробуй позже.",
            reply_markup=kb_recipe_error(),
        )
        await state.clear()


# ─────────────────────────────────────────────────────────────────────────────
# Вспомогательная функция: запрос к AI и вывод ответа
# ─────────────────────────────────────────────────────────────────────────────

async def _run_ai_and_reply(
    target_message: Message,
    state: FSMContext,
    matched: list[str],
    personal_products: list[dict],
    *,
    unmatched: list[str] | None = None,
    edit: bool = False,
) -> None:
    """
    Вызывает generate_ai_recipe, форматирует ответ и редактирует/отправляет сообщение.
    При ошибке AI показывает понятное сообщение.
    """
    if not _AI_API_KEY:
        text = (
            "⚠️ *AI не настроен.*\n\n"
            "Добавь в `.env` переменную:\n"
            "`AI_API_KEY=sk-or-v1-...`\n\n"
            "Получи бесплатный ключ на [openrouter.ai](https://openrouter.ai)"
        )
        if edit:
            await target_message.edit_text(text, parse_mode="Markdown",
                                           reply_markup=kb_recipe_error())
        else:
            await target_message.answer(text, parse_mode="Markdown",
                                        reply_markup=kb_recipe_error())
        return

    try:
        variant = await generate_ai_recipe(
            available_products=matched,
            api_key=_AI_API_KEY,
            base_url=_AI_BASE_URL,
            model=_AI_MODEL,
            extra_nutrient_db=personal_products or None,
        )
    except Exception as exc:
        log.exception("Ошибка AI-генерации: %s", exc)
        error_text = (
            "❌ *AI не смог сгенерировать рецепт.*\n\n"
            f"_Причина: {str(exc)[:200]}_\n\n"
            "Попробуй ещё раз — иногда модель возвращает неверный формат."
        )
        if edit:
            await target_message.edit_text(error_text, parse_mode="Markdown",
                                           reply_markup=kb_recipe_error())
        else:
            await target_message.answer(error_text, parse_mode="Markdown",
                                        reply_markup=kb_recipe_error())
        return

    # Предупреждение о нераспознанных продуктах
    prefix = ""
    if unmatched:
        prefix = f"⚠️ _Не распознано: {', '.join(unmatched)}_\n\n"

    text = prefix + format_recipe(variant)

    if edit:
        await target_message.edit_text(text, parse_mode="Markdown",
                                       reply_markup=kb_recipe_result())
    else:
        await target_message.answer(text, parse_mode="Markdown",
                                    reply_markup=kb_recipe_result())


# ─────────────────────────────────────────────────────────────────────────────
# Сериализация RecipeVariant для FSM (если понадобится хранить результат)
# ─────────────────────────────────────────────────────────────────────────────

def _serialize_variants(variants: list) -> list[dict]:
    return [
        {
            "title": v.title,
            "complexity": v.complexity,
            "ingredients": [
                {"key": i.key, "display": i.display, "weight_g": i.weight_g}
                for i in v.ingredients
            ],
            "steps": v.steps,
            "notes": v.notes,
            "suggestion": v.suggestion,
        }
        for v in variants
    ]


def _deserialize_variants(raw: list[dict]) -> list:
    from recipe_engine import Ingredient, RecipeVariant
    return [
        RecipeVariant(
            title=r["title"],
            complexity=r["complexity"],
            ingredients=[
                Ingredient(i["key"], i["display"], float(i["weight_g"]))
                for i in r["ingredients"]
            ],
            steps=r["steps"],
            notes=r.get("notes", ""),
            suggestion=r.get("suggestion", []),
        )
        for r in raw
    ]
