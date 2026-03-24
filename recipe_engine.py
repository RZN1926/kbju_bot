"""
recipe_engine.py
~~~~~~~~~~~~~~~~
AI-генератор рецептов на основе доступных продуктов.

Архитектура:
  1. NUTRIENT_DB          — справочник КБЖУ на 100 г (сухой/сырой продукт).
  2. generate_ai_recipe() — отправляет список продуктов в LLM, получает JSON-рецепт,
                            пересчитывает КБЖУ по локальной БД (антигаллюцинация).
  3. calc_nutrition()     — честный расчёт с учётом cooked_factor.
  4. format_recipe()      — Markdown для Telegram (порция + 100 г).

Не зависит от aiogram — чистая бизнес-логика, легко тестировать.
"""
from __future__ import annotations

import json
import logging
import re
import textwrap
from dataclasses import dataclass, field
from typing import Any

try:
    from openai import AsyncOpenAI  # pip install openai>=1.0
except ImportError:
    AsyncOpenAI = None  # type: ignore

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# 1. СПРАВОЧНИК НУТРИЕНТОВ
#
#    Ключи — нижний регистр, без лишних пробелов.
#    Поля: n (название), k (ккал), b (белки г), j (жиры г), u (углеводы г) —
#          все на 100 г продукта.
#    cooked_factor — коэффициент набухания при варке (только для круп/бобовых).
#    Если cooked_factor есть — нутриенты указаны для СУХОГО продукта,
#    итоговый вес порции = weight_g × cooked_factor.
# ─────────────────────────────────────────────────────────────────────────────

NUTRIENT_DB: dict[str, dict] = {
    # ── Крупы (сухие) ─────────────────────────────────────────────────────────
    "гречка":        {"n": "Гречка",            "k": 313, "b": 12.6, "j": 3.3,  "u": 57.1, "cooked_factor": 2.5},
    "рис":           {"n": "Рис",               "k": 344, "b": 6.7,  "j": 0.7,  "u": 78.9, "cooked_factor": 2.8},
    "овсянка":       {"n": "Овсянка",           "k": 366, "b": 11.9, "j": 7.2,  "u": 69.3, "cooked_factor": 2.0},
    "перловка":      {"n": "Перловка",          "k": 324, "b": 9.3,  "j": 1.1,  "u": 67.5, "cooked_factor": 3.0},
    "макароны":      {"n": "Макароны",          "k": 337, "b": 11.5, "j": 1.3,  "u": 69.7, "cooked_factor": 2.5},
    "пшено":         {"n": "Пшено",             "k": 348, "b": 11.5, "j": 3.3,  "u": 69.3, "cooked_factor": 2.3},

    # ── Белковые ──────────────────────────────────────────────────────────────
    "яйцо":          {"n": "Яйцо куриное",      "k": 157, "b": 13.0, "j": 11.5, "u": 0.7},
    "яйца":          {"n": "Яйцо куриное",      "k": 157, "b": 13.0, "j": 11.5, "u": 0.7},
    "куриная грудь": {"n": "Куриная грудь",     "k": 113, "b": 23.6, "j": 1.9,  "u": 0.4},
    "курица":        {"n": "Куриная грудь",     "k": 113, "b": 23.6, "j": 1.9,  "u": 0.4},
    "тунец":         {"n": "Тунец (конс.)",     "k": 96,  "b": 22.0, "j": 0.7,  "u": 0.0},
    "говядина":      {"n": "Говядина",          "k": 218, "b": 18.5, "j": 16.0, "u": 0.0},
    "творог":        {"n": "Творог 5%",         "k": 121, "b": 16.8, "j": 5.0,  "u": 1.9},
    "котлеты":       {"n": "Котлеты куриные",   "k": 175, "b": 15.0, "j": 9.0,  "u": 8.0},
    "фарш":          {"n": "Фарш куриный",      "k": 143, "b": 17.0, "j": 8.5,  "u": 0.0},

    # ── Молочные ──────────────────────────────────────────────────────────────
    "молоко":        {"n": "Молоко 2,5%",       "k": 52,  "b": 2.9,  "j": 2.5,  "u": 4.7},
    "кефир":         {"n": "Кефир 1%",          "k": 40,  "b": 3.4,  "j": 1.0,  "u": 4.7},
    "сметана":       {"n": "Сметана 15%",       "k": 158, "b": 2.6,  "j": 15.0, "u": 3.0},
    "сыр":           {"n": "Сыр твёрдый",       "k": 360, "b": 26.0, "j": 29.0, "u": 0.0},
    "масло":         {"n": "Масло сливочное",   "k": 748, "b": 0.5,  "j": 82.5, "u": 0.8},
    "растительное масло": {"n": "Масло подсолн.", "k": 899, "b": 0.0, "j": 99.9, "u": 0.0},

    # ── Овощи / зелень ────────────────────────────────────────────────────────
    "помидор":       {"n": "Помидор",           "k": 18,  "b": 0.9,  "j": 0.2,  "u": 3.8},
    "помидоры":      {"n": "Помидор",           "k": 18,  "b": 0.9,  "j": 0.2,  "u": 3.8},
    "огурец":        {"n": "Огурец",            "k": 14,  "b": 0.8,  "j": 0.1,  "u": 2.5},
    "огурцы":        {"n": "Огурец",            "k": 14,  "b": 0.8,  "j": 0.1,  "u": 2.5},
    "капуста":       {"n": "Капуста белок.",    "k": 27,  "b": 1.8,  "j": 0.1,  "u": 4.7},
    "лук":           {"n": "Лук репчатый",      "k": 41,  "b": 1.4,  "j": 0.2,  "u": 8.2},
    "морковь":       {"n": "Морковь",           "k": 35,  "b": 1.3,  "j": 0.1,  "u": 6.9},
    "картофель":     {"n": "Картофель",         "k": 77,  "b": 2.0,  "j": 0.4,  "u": 16.3},
    "картошка":      {"n": "Картофель",         "k": 77,  "b": 2.0,  "j": 0.4,  "u": 16.3},
    "перец":         {"n": "Перец болгарский",  "k": 26,  "b": 1.3,  "j": 0.1,  "u": 5.3},
    "зелень":        {"n": "Зелень (микс)",     "k": 25,  "b": 2.0,  "j": 0.4,  "u": 3.5},
    "шпинат":        {"n": "Шпинат",            "k": 23,  "b": 2.9,  "j": 0.4,  "u": 2.0},
    "чеснок":        {"n": "Чеснок",            "k": 149, "b": 6.5,  "j": 0.5,  "u": 29.9},

    # ── Фрукты / ягоды ────────────────────────────────────────────────────────
    "банан":         {"n": "Банан",             "k": 89,  "b": 1.1,  "j": 0.3,  "u": 22.8},
    "яблоко":        {"n": "Яблоко",            "k": 47,  "b": 0.4,  "j": 0.4,  "u": 9.8},
    "яблоки":        {"n": "Яблоко",            "k": 47,  "b": 0.4,  "j": 0.4,  "u": 9.8},

    # ── Бобовые ───────────────────────────────────────────────────────────────
    "чечевица":      {"n": "Чечевица",          "k": 295, "b": 24.0, "j": 1.5,  "u": 46.3, "cooked_factor": 2.5},
    "горошек":       {"n": "Горошек зел.",      "k": 72,  "b": 5.0,  "j": 0.2,  "u": 13.3},

    # ── Разное ────────────────────────────────────────────────────────────────
    "хлеб":          {"n": "Хлеб цельнозерн.",  "k": 247, "b": 9.0,  "j": 3.1,  "u": 41.3},
    "вода":          {"n": "Вода",              "k": 0,   "b": 0.0,  "j": 0.0,  "u": 0.0},
    "специи":        {"n": "Специи",            "k": 0,   "b": 0.0,  "j": 0.0,  "u": 0.0},
    "соль":          {"n": "Соль",              "k": 0,   "b": 0.0,  "j": 0.0,  "u": 0.0},
    "соевый соус":   {"n": "Соевый соус",       "k": 55,  "b": 5.7,  "j": 0.1,  "u": 7.0},
}


# ─────────────────────────────────────────────────────────────────────────────
# 2. МОДЕЛИ ДАННЫХ
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Ingredient:
    key: str        # ключ в NUTRIENT_DB
    display: str    # красивое название для вывода
    weight_g: float # масса в рецепте (г, сырой/сухой продукт)

    @property
    def data(self) -> dict:
        return NUTRIENT_DB.get(self.key, {"n": self.display, "k": 0, "b": 0, "j": 0, "u": 0})


@dataclass
class RecipeVariant:
    title: str
    complexity: str                      # "⚡ Быстро" / "🍳 Средне" / "👨‍🍳 Посложнее"
    ingredients: list[Ingredient]
    steps: list[str]
    notes: str = ""
    suggestion: list[str] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# 3. ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ─────────────────────────────────────────────────────────────────────────────

def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def parse_ingredients(raw: str) -> list[str]:
    """Разбирает строку пользователя на отдельные ингредиенты."""
    raw = raw.replace("\n", ",").replace(";", ",").replace(" и ", ",")
    return [_normalize(p) for p in raw.split(",") if p.strip()]


def match_ingredients(
    raw_list: list[str],
    extra_db: list[dict] | None = None,
) -> tuple[list[str], list[str]]:
    """
    Сопоставляет введённые пользователем строки с ключами NUTRIENT_DB.
    extra_db — личная база продуктов из Firestore.
    Возвращает (matched_keys, unmatched_strings).
    """
    extended_db = dict(NUTRIENT_DB)
    if extra_db:
        for p in extra_db:
            extended_db[_normalize(p["n"])] = p

    matched: list[str] = []
    unmatched: list[str] = []

    for raw in raw_list:
        key = _resolve_key(raw, extended_db)
        if key:
            matched.append(key)
        else:
            unmatched.append(raw)

    # Добавляем личные продукты в глобальный NUTRIENT_DB для расчётов
    NUTRIENT_DB.update({_normalize(p["n"]): p for p in (extra_db or [])})

    return list(dict.fromkeys(matched)), unmatched


def _resolve_key(norm: str, db: dict) -> str | None:
    """Точное → частичное → по первому слову."""
    if norm in db:
        return norm
    for key in db:
        if norm in key or key in norm:
            return key
    fw = norm.split()[0] if norm.split() else norm
    for key in db:
        if key.startswith(fw) or fw in key:
            return key
    return None


# ─────────────────────────────────────────────────────────────────────────────
# 4. РАСЧЁТ КБЖУ (антигаллюцинация — только наши данные)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class NutritionCard:
    calories: float
    protein: float
    fat: float
    carbs: float
    total_weight_g: float  # итоговый вес готового блюда

    def per_100g(self) -> "NutritionCard":
        if self.total_weight_g == 0:
            return self
        f = 100 / self.total_weight_g
        return NutritionCard(
            calories=round(self.calories * f, 1),
            protein=round(self.protein * f, 1),
            fat=round(self.fat * f, 1),
            carbs=round(self.carbs * f, 1),
            total_weight_g=100,
        )


def calc_nutrition(ingredients: list[Ingredient]) -> NutritionCard:
    """
    Считает суммарное КБЖУ и итоговый вес порции.

    cooked_factor-логика:
      - weight_g = масса СУХОГО продукта
      - калорийность считается от сухого веса (честные данные)
      - total_weight_g = weight_g × cooked_factor (вес в тарелке)
    """
    total_k = total_b = total_j = total_u = total_weight = 0.0
    for ing in ingredients:
        d = ing.data
        w = ing.weight_g
        total_k      += d["k"] * w / 100
        total_b      += d["b"] * w / 100
        total_j      += d["j"] * w / 100
        total_u      += d["u"] * w / 100
        total_weight += w * d.get("cooked_factor", 1.0)

    return NutritionCard(
        calories=round(total_k, 1),
        protein=round(total_b, 1),
        fat=round(total_j, 1),
        carbs=round(total_u, 1),
        total_weight_g=round(total_weight, 1),
    )


# ─────────────────────────────────────────────────────────────────────────────
# 5. СИСТЕМНЫЙ ПРОМПТ ДЛЯ LLM
# ─────────────────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = textwrap.dedent("""
    Ты — кулинарный ассистент. Получаешь список продуктов и придумываешь
    один вкусный и реалистичный рецепт из них.

    СТРОГИЕ ПРАВИЛА:
    1. Отвечай ТОЛЬКО валидным JSON. Никакого текста до или после.
    2. Используй ТОЛЬКО продукты из предоставленного списка.
       Базовые добавки (соль, вода, специи, растительное масло) можно
       добавлять свободно — они есть на любой кухне.
    3. weight_g — целое число граммов.
       Для круп и бобовых (гречка, рис, овсянка, перловка, макароны,
       чечевица) указывай вес СУХОГО продукта и ставь "dry": true.
    4. steps — конкретные шаги, 4–7 штук, без воды.
    5. complexity: "quick" (до 15 мин), "medium" (15–40 мин), "hard" (40+ мин).
    6. Поле nutrition НЕ заполняй — КБЖУ посчитает серверный код.

    ФОРМАТ (строго соблюдай):
    {
      "title": "Название блюда",
      "complexity": "quick|medium|hard",
      "tip": "Краткая кулинарная подсказка или пустая строка",
      "ingredients": [
        {"name": "Название", "weight_g": 150, "dry": false}
      ],
      "steps": ["Шаг 1", "Шаг 2"]
    }
""").strip()


# ─────────────────────────────────────────────────────────────────────────────
# 6. ГЛАВНАЯ ФУНКЦИЯ — AI-ГЕНЕРАЦИЯ С ВЕРИФИКАЦИЕЙ КБЖУ
# ─────────────────────────────────────────────────────────────────────────────

async def generate_ai_recipe(
    available_products: list[str],
    db_session: Any = None,            # зарезервировано для SQL-интеграции
    *,
    api_key: str,
    base_url: str = "https://openrouter.ai/api/v1",
    model: str = "google/gemma-3-12b-it:free",
    extra_nutrient_db: list[dict] | None = None,
) -> RecipeVariant:
    """
    Генерирует рецепт через LLM и верифицирует КБЖУ по локальной БД.

    Аргументы:
        available_products  — нормализованные ключи NUTRIENT_DB
                              (результат match_ingredients).
        db_session          — зарезервировано (SQLAlchemy / Firestore).
        api_key             — ключ провайдера (OpenRouter / Groq / OpenAI).
        base_url            — base URL OpenAI-совместимого эндпоинта.
        model               — название модели.
        extra_nutrient_db   — личные продукты из Firestore
                              (список dict: n, k, b, j, u).

    Возвращает RecipeVariant с пересчитанным КБЖУ.
    Бросает исключение при сетевой ошибке или невалидном ответе LLM.

    Рекомендуемый бесплатный стек (2025–2026):
      - OpenRouter  base_url="https://openrouter.ai/api/v1"
          Бесплатные модели: "google/gemma-3-12b-it:free",
                             "meta-llama/llama-3.1-8b-instruct:free"
      - Groq        base_url="https://api.groq.com/openai/v1"
          Бесплатно с лимитами: "llama-3.3-70b-versatile"
                                 "llama3-8b-8192"
    """
    if AsyncOpenAI is None:
        raise ImportError("Установи библиотеку openai: pip install openai>=1.0")

    # Расширяем справочник личными продуктами пользователя
    active_db: dict[str, dict] = dict(NUTRIENT_DB)
    if extra_nutrient_db:
        for p in extra_nutrient_db:
            active_db[_normalize(p["n"])] = p

    # Красивые названия для промпта
    product_names = [
        active_db[k]["n"] if k in active_db else k.capitalize()
        for k in available_products
    ]
    product_list_str = ", ".join(product_names)
    log.info("AI-рецепт: модель=%s | продукты=[%s]", model, product_list_str)

    # ── Запрос к LLM ──────────────────────────────────────────────────────────
    client = AsyncOpenAI(api_key=api_key, base_url=base_url)
    
    # Объединяем системный промпт и данные пользователя в один текст
    combined_content = (
        f"{_SYSTEM_PROMPT}\n\n"
        f"Данные для обработки:\n"
        f"Продукты: {product_list_str}"
    )

    response = await client.chat.completions.create(
        model=model,
        temperature=0.7,
        max_tokens=1200,
        response_format={"type": "json_object"},
        messages=[
            # Используем только роль "user", это работает везде
            {"role": "user", "content": combined_content},
        ],
    )
    raw_content: str = response.choices[0].message.content or ""
    log.debug("LLM ответ: %.300s", raw_content)

    # ── Парсинг JSON ──────────────────────────────────────────────────────────
    # Некоторые модели оборачивают JSON в ```json ... ``` — вырезаем
    clean = re.sub(r"```(?:json)?\s*|\s*```", "", raw_content).strip()
    try:
        data = json.loads(clean)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"LLM вернул невалидный JSON: {exc}\nОтвет: {raw_content[:400]}"
        ) from exc

    # ── Сборка ингредиентов + верификация КБЖУ ────────────────────────────────
    ingredients: list[Ingredient] = []
    unknown_products: list[str] = []

    for item in data.get("ingredients", []):
        name: str     = item.get("name", "")
        weight_g: float = float(item.get("weight_g", 100))

        norm = _normalize(name)
        db_key = _resolve_key(norm, active_db)

        if db_key:
            # ✅ Продукт в БД — КБЖУ берём из нашего справочника (не от LLM)
            entry = active_db[db_key]
            ingredients.append(Ingredient(key=db_key, display=entry["n"], weight_g=weight_g))
        else:
            # ⚠️ Продукта нет в БД — добавляем с нулевым КБЖУ, рецепт не теряем
            log.warning("Продукт не найден в БД: %r", name)
            unknown_products.append(name)
            active_db[norm] = {"n": name, "k": 0, "b": 0, "j": 0, "u": 0}
            ingredients.append(Ingredient(key=norm, display=name, weight_g=weight_g))

    if not ingredients:
        raise ValueError("LLM не вернул ни одного ингредиента.")

    # ── Примечание о недостающих данных ──────────────────────────────────────
    notes = data.get("tip", "")
    if unknown_products:
        warn = "⚠️ Нет данных КБЖУ для: " + ", ".join(unknown_products)
        notes = f"{notes}\n{warn}".strip() if notes else warn

    complexity_map = {
        "quick":  "⚡ Быстро",
        "medium": "🍳 Средне",
        "hard":   "👨‍🍳 Посложнее",
    }

    return RecipeVariant(
        title=data.get("title", "Рецепт от шефа"),
        complexity=complexity_map.get(data.get("complexity", "medium"), "🍳 Средне"),
        ingredients=ingredients,
        steps=data.get("steps", []),
        notes=notes,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 7. ФОРМАТИРОВАНИЕ ОТВЕТА ДЛЯ TELEGRAM
# ─────────────────────────────────────────────────────────────────────────────

def format_recipe(variant: RecipeVariant) -> str:
    """Возвращает Markdown-сообщение для Telegram с КБЖУ на порцию и на 100 г."""
    card    = calc_nutrition(variant.ingredients)
    per100  = card.per_100g()

    # Строки ингредиентов с указанием варёного веса для круп
    ing_lines: list[str] = []
    for ing in variant.ingredients:
        d  = ing.data
        cf = d.get("cooked_factor", 1.0)
        cooked_w = round(ing.weight_g * cf)
        if cf > 1.0:
            ing_lines.append(
                f"  • {ing.display} — {int(ing.weight_g)} г сухой / ~{cooked_w} г готовой"
            )
        else:
            ing_lines.append(f"  • {ing.display} — {int(ing.weight_g)} г")

    step_lines = [f"  {i + 1}. {s}" for i, s in enumerate(variant.steps)]
    notes_block = f"\n{variant.notes}\n" if variant.notes else ""

    return (
        f"🍽 *{variant.title}*  {variant.complexity}\n"
        f"{'─' * 30}\n\n"
        f"📦 *Ингредиенты:*\n"
        + "\n".join(ing_lines)
        + "\n\n"
        + "👨‍🍳 *Приготовление:*\n"
        + "\n".join(step_lines)
        + f"\n{notes_block}"
        + f"\n{'─' * 30}\n"
        + f"📊 *КБЖУ на 100 г:*\n"
        + f"  🔥 Калории: *{per100.calories} ккал*\n"
        + f"  🥩 Белки:   *{per100.protein} г*\n"
        + f"  🧈 Жиры:    *{per100.fat} г*\n"
        + f"  🍞 Углеводы: *{per100.carbs} г*"
    )


def format_not_found(unmatched: list[str]) -> str:
    listed = "\n".join(f"  ❓ {p}" for p in unmatched)
    return (
        f"⚠️ *Не удалось распознать продукты:*\n{listed}\n\n"
        f"_Попробуй написать иначе, например: яйца, гречка, творог_"
    )
