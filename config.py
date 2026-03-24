import os
import json
import base64
import firebase_admin
from firebase_admin import credentials, firestore
from dotenv import load_dotenv

# Загружаем .env файл (для локальной разработки)
load_dotenv()

# ── TELEGRAM ───────────────────────────────────────────────
BOT_TOKEN: str = os.environ['BOT_TOKEN']

# ── FIREBASE ───────────────────────────────────────────────
_raw = os.environ.get('FIREBASE_CREDENTIALS', '')
if _raw:
    cred = credentials.Certificate(json.loads(base64.b64decode(_raw).decode()))
else:
    cred = credentials.Certificate('serviceAccount.json')

firebase_admin.initialize_app(cred)
db = firestore.client()

# ── КОНСТАНТЫ ──────────────────────────────────────────────
DAYS_RU = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота', 'Воскресенье']

# Дни с тренировками (0=Пн, 2=Ср, 4=Пт) — полный набор приёмов
TRAIN_DAYS = {0, 2, 4}

MEALS_FULL  = ['Завтрак', 'Обед', 'Перекус', 'Предтрен', 'Ужин', 'Перед сном']
MEALS_SHORT = ['Завтрак', 'Обед', 'Перекус', 'Ужин', 'Перед сном']

# ── ВСТРОЕННАЯ БАЗА ПРОДУКТОВ (как на сайте) ───────────────
BUILTIN_DB = [
    {'n': 'Куриная грудь (варёная)', 'k': 140, 'b': 29,   'j': 2,   'u': 0.1},
    {'n': 'Творог 5%',               'k': 121, 'b': 16.8, 'j': 5,   'u': 1.9},
    {'n': 'Гречка варёная',          'k': 350, 'b': 12.8, 'j': 2.7, 'u': 61 },
    {'n': 'Овсянка на воде',         'k': 350, 'b': 12,   'j': 1.5, 'u': 15 },
    {'n': 'Яйцо куриное (1 шт)',     'k': 143, 'b': 13,   'j': 11,  'u': 0.7},
    {'n': 'Рис варёный',             'k': 360, 'b': 6.7,  'j': 0.6, 'u': 80 },
    {'n': 'Банан',                   'k': 92,  'b': 1.1,  'j': 0.4, 'u': 22 },
    {'n': 'Кефир 1%',                'k': 30,  'b': 3,    'j': 1,   'u': 3.8},
    {'n': 'Курица Копч.',            'k': 113, 'b': 23.6, 'j': 1.9, 'u': 0.4},
    {'n': 'Арахис',                  'k': 620, 'b': 26,   'j': 50,  'u': 14 },
]
