import json
import os
import sys
from datetime import date, datetime

import models
import monetization as mon
import reco_feed
import reco_vectors  # noqa: F401  (нужно, чтобы создалась таблица pet_vectors)
from database import Base, SessionLocal, engine
from demo_data import EXTRA_PETS

DATA_PATH = os.path.join(os.path.dirname(__file__), "data.json")

DATETIME_FIELDS = {"date_creation", "publication_date", "date",
                   "last_message_date", "sent_date", "notification_date"}

TABLES = [("users", models.User), ("sellers", models.Seller), ("pets", models.Pet),
          ("swipes", models.Swipe), ("chats", models.Chat),
          ("messages", models.Message), ("notifications", models.Notification)]

# Тестовые пользователи: (id, имя, email, телефон)
TEST_USERS = [
    (4, "Кошатник",        "koshatnik@example.com", "+7-900-555-55-04"),
    (5, "Не любит котов",  "nocats@example.com",    "+7-900-555-55-05"),
    (6, "Захотел попугая", "parrot@example.com",    "+7-900-555-55-06"),
]

# Предпочтения из опроса (таблица user_prefs)
PREFS = {
    1: dict(species="cat", age_min=3, age_max=24),
    4: dict(species="cat", age_min=3, age_max=24,
            about="Хочу спокойную кошку для квартиры, у нас маленькие дети"),
    5: dict(species="cat", age_min=3, age_max=24),
    6: dict(species="cat", age_min=3, age_max=24),
}

# Свайпы: (пользователь, питомец, направление)
SWIPES = [
    (5, 7, "left"), (5, 8, "left"), (5, 9, "left"), (5, 10, "left"),   # дизлайкает котов подряд
    (6, 7, "right"), (6, 8, "right"), (6, 17, "right"),                # лайкает котов и попугая
]


def convert(row):
    out = {}
    for key, value in row.items():
        if value is None:
            out[key] = None
        elif key in DATETIME_FIELDS:
            out[key] = datetime.fromisoformat(value)
        elif key == "birthday_date":
            out[key] = date.fromisoformat(value)
        else:
            out[key] = value
    return out


def load_base_data(db):
    """Данные команды из data.json."""
    if db.query(models.User).count() > 0:
        print("Базовые данные уже есть, пропускаю.")
        return
    with open(DATA_PATH, encoding="utf-8") as f:
        data = json.load(f)
    for key, model in TABLES:
        for row in data[key]:
            db.add(model(**convert(row)))
    db.commit()
    print("Базовые данные из data.json загружены.")


def load_extra_data(db):
    """Больше питомцев, тестовые пользователи, их предпочтения и свайпы."""
    if db.get(models.Seller, 4) is None:
        db.add(models.Seller(id=4, seller_type="individual", name="Анна", city="Москва",
                             email="anna@example.com", phone="+7-900-555-55-00"))
    for p in EXTRA_PETS:
        if db.get(models.Pet, p["id"]) is None:
            db.add(models.Pet(**{k: v for k, v in p.items() if k != "description"}))
    for uid, name, email, phone in TEST_USERS:
        if db.get(models.User, uid) is None:
            db.add(models.User(id=uid, name=name, password="hash_test", email=email,
                               phone=phone, city="Тула"))
    db.commit()

    for uid, fields in PREFS.items():
        if db.get(reco_feed.UserPrefs, uid) is None:
            db.add(reco_feed.UserPrefs(user_id=uid, **fields))
    for uid, pid, direction in SWIPES:
        if not db.query(models.Swipe).filter_by(user_id=uid, pet_id=pid).first():
            db.add(models.Swipe(user_id=uid, pet_id=pid, direction=direction))
    db.commit()
    print("Тестовые питомцы, пользователи и свайпы добавлены.")


def setup_premium(db):
    """Питомник (продавец 2) оформляет премиум: его питомцы продвигаются."""
    if not mon.is_premium(db, "seller", 2):
        mon.activate_premium(db, "seller", 2)
    until = mon.premium_until(db, "seller", 2)
    print(f"Питомник (продавец 2): премиум до {until:%d.%m.%Y}, его питомцы продвигаются.")


def reset_usage(db):
    """Сбрасывает счётчики свайпов и премиум клиентов (премиум продавцов остаётся)."""
    db.query(mon.SwipeUsage).delete()
    db.query(mon.Subscription).filter(mon.Subscription.owner_type == "user").delete()
    db.commit()
    print("Счётчики свайпов и премиум клиентов сброшены.")


if __name__ == "__main__":
    Base.metadata.create_all(engine)
    db = SessionLocal()
    if len(sys.argv) > 1 and sys.argv[1] == "reset":
        reset_usage(db)
    else:
        load_base_data(db)
        load_extra_data(db)
        setup_premium(db)
    db.close()