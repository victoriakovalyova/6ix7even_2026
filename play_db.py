import random
import sys

import models
import monetization as mon
import reco_feed
import reco_vectors
from crud import create_swipe
from database import Base, SessionLocal, engine
from demo_data import DESCRIPTIONS

BATCH = 10   # как в будущем API: фронт получает ленту порциями по 10 карточек

Base.metadata.create_all(engine)
db = SessionLocal()
SCENARIOS = [
    (1, "Иван: анкета (кот, Тула), лайкал Мурку и Луну, отклонил Барсика"),
    (4, "Кошатник: холодный старт, анкета и текст «спокойная кошка, дети»"),
    (5, "Не любит котов: дизлайкнул 4 котов подряд"),
    (6, "Захотел попугая: лайкнул 2 котов и попугая Кешу"),
    (2, "Мария: продавец без анкеты, её анкеты не должны быть в ленте"),
]


def print_all_feeds():
    print("Новых векторов:", reco_vectors.sync_pet_vectors(db))
    for uid, title in SCENARIOS:
        print(f"\n=== {title} ===")
        for i, item in enumerate(mon.build_feed(db, uid, limit=12, seed=1), 1):
            pet = item["pet"]
            print(f'{i:2}. {pet.nickname:9} {pet.pet_type:8} {item["city"] or "-":7} '
                  f'{item["score"]:6.1f}  [{item["source"]}]  {", ".join(item["reasons"])}')


if len(sys.argv) > 1 and sys.argv[1] == "all":
    print_all_feeds()
    raise SystemExit
user_id = int(sys.argv[1]) if len(sys.argv) > 1 else 4
user = db.get(models.User, user_id)
if user is None:
    print("Пользователя с таким номером нет. Попробуйте 1, 4, 5 или 6.")
    raise SystemExit

MENU = """
  1 - Лайк
  2 - Дизлайк
  3 - Что лента уже поняла о моём вкусе
  4 - Моя подписка и остаток свайпов
  5 - Оформить премиум (оплата имитируется)
  0 - Выйти"""


def show_status():
    until = mon.premium_until(db, "user", user_id)
    print("\n--- Подписка ---")
    print(f"   ПРЕМИУМ до {until:%d.%m.%Y}" if until else "   Бесплатный тариф")
    print(f"   Свайпов осталось сегодня: {mon.swipes_left(db, user_id)} из {mon.daily_limit(db, user_id)}")


def show_taste():
    history = (db.query(models.Swipe.direction, models.Pet)
               .join(models.Pet, models.Swipe.pet_id == models.Pet.id)
               .filter(models.Swipe.user_id == user_id).all())
    taste = reco_feed.build_taste(history)
    items = [(key, value) for key, value in taste.items() if value]
    print("\n--- Вкус по версии ленты ---")
    if not items:
        print("   пока ничего")
        return
    items.sort(key=lambda kv: kv[1], reverse=True)
    for (feature, value), score in items:
        print(f"   {feature}: {value}   {score:+.1f}")


def show_card(item, number):
    pet = item["pet"]
    price = "Бесплатно" if not pet.price else f"{pet.price:,.0f} руб.".replace(",", " ")
    label = "РЕКЛАМА (продавец продвигает объявление)" if item["source"] == "реклама" else item["source"]
    print("\n" + "=" * 58)
    print(f"Карточка №{number}  [{label}, {item['score']} баллов]")
    print(f"{pet.nickname} - {pet.pet_type}, {pet.breed}, {pet.color}")
    print(f"Возраст: {pet.age_in_months} мес. | Город: {item['city']} | {price}")
    print(f"О питомце: {DESCRIPTIONS.get(pet.id, '-')}")
    if item["reasons"]:
        print("Почему в ленте:", ", ".join(item["reasons"]))
    print("=" * 58)


def buy_premium():
    until = mon.activate_premium(db, "user", user_id)
    print(f"\n  Премиум оформлен до {until:%d.%m.%Y} (оплата имитирована).")
    show_status()


def finish():
    show_status()
    raise SystemExit


print(f"Вы: {user.name} (id {user_id}), город {user.city}")
print("Подготовка векторов, новых:", reco_vectors.sync_pet_vectors(db))
show_status()

seed = random.randint(1, 10**6)
batch_no = 0
shown = 0
while True:
    if mon.swipes_left(db, user_id) <= 0:
        print("\nНа сегодня свайпы закончились. Премиум увеличивает дневной лимит.")
        cmd = input("1 - оформить премиум, 0 - выйти: ").strip()
        if cmd == "1":
            buy_premium()
        elif cmd == "0":
            finish()
        continue

    batch = mon.build_feed(db, user_id, limit=BATCH, seed=seed + batch_no)
    batch_no += 1
    if not batch:
        print("\nЛента закончилась: вы посмотрели всех питомцев.")
        break
    print(f"\n>>> Новая порция ленты: {len(batch)} карточек")

    for item in batch:
        if mon.swipes_left(db, user_id) <= 0:
            break
        shown += 1
        show_card(item, shown)
        print(MENU)
        while True:
            answer = input("Введите цифру и нажмите Enter: ").strip()
            if answer in ("1", "2"):
                direction = "right" if answer == "1" else "left"
                try:
                    swipe, chat = create_swipe(db, user_id, item["id"], direction)
                except ValueError as error:
                    print("  Не получилось:", error)
                    break
                mon.register_swipe(db, user_id)
                print("  Лайк" if direction == "right" else "  Дизлайк", "-", item["pet"].nickname)
                if chat is not None:
                    print(f"  Открыт чат №{chat.id}, продавец получил уведомление")
                print(f"  Свайпов осталось: {mon.swipes_left(db, user_id)}")
                break
            elif answer == "3":
                show_taste()
            elif answer == "4":
                show_status()
            elif answer == "5":
                buy_premium()
            elif answer == "0":
                finish()
            else:
                print("  Введите цифру от 0 до 5.")

db.close()