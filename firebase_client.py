"""Все операции с Firestore."""
import pathlib, json
from datetime import date
from config import db

USERS_FILE = 'users.json'


# ── UID mapping ────────────────────────────────────────────
def load_users() -> dict:
    p = pathlib.Path(USERS_FILE)
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else {}

def save_users(users: dict):
    pathlib.Path(USERS_FILE).write_text(
        json.dumps(users, ensure_ascii=False, indent=2), encoding='utf-8'
    )

def get_uid(tg_id: str) -> str | None:
    return load_users().get(tg_id)

def set_uid(tg_id: str, uid: str):
    users = load_users()
    users[tg_id] = uid
    save_users(users)

def remove_uid(tg_id: str):
    users = load_users()
    users.pop(tg_id, None)
    save_users(users)


# ── Данные о еде (формат сайта) ───────────────────────────
def get_day_data(uid: str, day_key: str) -> dict:
    """Возвращает dict приёмов за день: {'Завтрак': [...], ...}"""
    snap = db.collection('users').document(uid).get()
    if not snap.exists:
        return {}
    data = snap.to_dict().get('data', {})
    return data.get(day_key, {})

def save_entry(uid: str, day_key: str, meal: str, entry: dict):
    """Добавляет одну запись в нужный приём пищи."""
    snap = db.collection('users').document(uid).get()
    data = snap.to_dict().get('data', {}) if snap.exists else {}
    data.setdefault(day_key, {}).setdefault(meal, [])
    data[day_key][meal].append(entry)
    db.collection('users').document(uid).set({'data': data}, merge=True)


# ── Личная база продуктов ──────────────────────────────────
def get_personal_products(uid: str) -> list[dict]:
    """Возвращает список продуктов из личной базы."""
    docs = db.collection('users').document(uid).collection('personal_products').stream()
    return [{'id': d.id, **d.to_dict()} for d in docs]

def add_personal_product(uid: str, product: dict):
    """Сохраняет новый продукт в личную базу."""
    db.collection('users').document(uid).collection('personal_products').add(product)

def delete_personal_product(uid: str, doc_id: str):
    """Удаляет продукт из личной базы по id документа."""
    db.collection('users').document(uid).collection('personal_products').document(doc_id).delete()