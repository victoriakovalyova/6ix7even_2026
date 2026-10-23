import random
from collections import Counter

from sqlalchemy import Column, ForeignKey, Integer, String, Text

import reco_vectors
from database import Base
from models import Pet, Seller, Swipe, User

# ---------- Настройки (все числа подбираются на тестах) ----------
W_VECTOR = 50          # максимум баллов за смысловое сходство описаний
W_SPECIES = 30         # вид совпал с анкетой
W_CITY = 15            # город совпал
W_AGE = 10             # возраст в нужном диапазоне
TASTE_STEP = 10        # баллов за единицу «вкуса» (лайки/дизлайки по виду, породе, окрасу)
TASTE_CAP = 30         # вкус не может дать или отнять больше этого
FEATURES = {"pet_type": 1.0, "breed": 0.5, "color": 0.3}   # важность признаков во «вкусе»
CONTRADICT_AT = -1.0   # вкус к виду из анкеты ниже этого: человек анкету опроверг
EXPLORE_EVERY = 4      # 4 рекомендации, потом 1 случайная
NOISE = 10             # случайный «шум» при выборе случайных карточек


class UserPrefs(Base):
    """Наша таблица: предпочтения пользователя из регистрации/опроса."""
    __tablename__ = "user_prefs"
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    species = Column(String)    # вид животного: cat, dog, ...
    age_min = Column(Integer)   # возраст питомца в месяцах
    age_max = Column(Integer)
    city = Column(String)       # если пусто, берём город пользователя
    about = Column(Text)        # свободный текст: «хочу спокойную кошку для квартиры»


def _norm(text):
    return (text or "").strip().lower()


def prefs_weight(n_swipes):
    """Чем больше свайпов, тем меньше доверяем анкете (но не меньше 30%)."""
    return max(0.3, 1 - 0.1 * n_swipes)


def build_taste(history):
    """history: список (направление, питомец). Лайк даёт +1, дизлайк -0.5 признакам питомца."""
    taste = Counter()
    for direction, pet in history:
        weight = 1.0 if direction == "right" else -reco_vectors.DISLIKE_WEIGHT
        for feature in FEATURES:
            value = getattr(pet, feature)
            if value:
                taste[(feature, value)] += weight
    return taste


def taste_points(pet, taste):
    return sum(taste[(f, getattr(pet, f))] * w for f, w in FEATURES.items() if getattr(pet, f))


def _scale(scores):
    """Приводит сходство к шкале 0-1 внутри списка кандидатов (иначе разброс слишком узкий)."""
    if not scores:
        return {}
    low, high = min(scores.values()), max(scores.values())
    if high - low < 1e-9:
        return {k: 0.5 for k in scores}
    return {k: (v - low) / (high - low) for k, v in scores.items()}


def _vector_scores(db, user_id, candidate_ids, about):
    """{id питомца: сходство}. Если векторы недоступны, возвращает пустой словарь."""
    try:
        vec = reco_vectors.user_vector(db, user_id)
        if vec is None and about:
            vec = reco_vectors.text_vector(about)     # холодный старт: текст «о себе»
        if vec is None:
            return {}
        return dict(reco_vectors.rank_pets_by_vector(db, vec, set(candidate_ids)))
    except Exception as error:
        print("Предупреждение: векторы недоступны, лента считается по правилам:", error)
        return {}


def get_feed(db, user_id, limit=10, explore_every=EXPLORE_EVERY, seed=None):
    """Возвращает до limit карточек: dict с ключами id, pet, city, score, source, reasons."""
    rng = random.Random(seed)
    user = db.get(User, user_id)
    if user is None:
        raise ValueError("Пользователь не найден")
    prefs = db.get(UserPrefs, user_id)
    city = _norm(prefs.city if prefs and prefs.city else user.city)

    # 1. Жёсткие фильтры
    swiped_ids = [pid for (pid,) in db.query(Swipe.pet_id).filter(Swipe.user_id == user_id)]
    rows = (db.query(Pet, Seller).join(Seller, Pet.seller_id == Seller.id)
            .filter(Pet.publication_status == "active")
            .filter(~Pet.id.in_(swiped_ids))
            .filter((Seller.user_id.is_(None)) | (Seller.user_id != user_id))   # не свои анкеты
            .all())
    if not rows:
        return []

    # 2. Что мы знаем о человеке
    history = (db.query(Swipe.direction, Pet).join(Pet, Swipe.pet_id == Pet.id)
               .filter(Swipe.user_id == user_id).all())
    taste = build_taste(history)
    n_swipes = len(history)
    liked_species = {pet.pet_type for direction, pet in history if direction == "right"}

    prefs_species = prefs.species if prefs and prefs.species else None
    contradicted = bool(prefs_species) and taste[("pet_type", prefs_species)] <= CONTRADICT_AT

    scaled = _scale(_vector_scores(db, user_id, [p.id for p, _ in rows],
                                   prefs.about if prefs else None))

    # 3. Баллы
    items = []
    for pet, seller in rows:
        reasons = []
        anketa = 0
        if prefs_species and pet.pet_type == prefs_species and not contradicted:
            anketa += W_SPECIES
            reasons.append("вид из вашей анкеты")
        if city and _norm(seller.city) == city:
            anketa += W_CITY
            reasons.append("из вашего города")
        if prefs and (prefs.age_min is not None or prefs.age_max is not None) \
                and pet.age_in_months is not None:
            low = prefs.age_min if prefs.age_min is not None else 0
            high = prefs.age_max if prefs.age_max is not None else 10**6
            if low <= pet.age_in_months <= high:
                anketa += W_AGE
                reasons.append("подходящий возраст")
        anketa *= prefs_weight(n_swipes)

        bonus = max(-TASTE_CAP, min(TASTE_CAP, TASTE_STEP * taste_points(pet, taste)))
        if bonus > 0:
            reasons.append("похож на тех, кого вы лайкали")

        vec_share = scaled.get(pet.id)             # None: у питомца нет вектора или модель недоступна
        vec_points = W_VECTOR * (vec_share if vec_share is not None else 0.5)
        if vec_share is not None and vec_share >= 0.75:
            reasons.append("похожее описание")

        items.append({"id": pet.id, "pet": pet, "city": seller.city,
                      "score": round(anketa + bonus + vec_points, 1),
                      "source": "рекомендация", "reasons": reasons})
    items.sort(key=lambda it: it["score"], reverse=True)

    # 4. «Основные» виды: из анкеты (если не опровергнута) и те, что человек лайкал
    core = {s for s in liked_species if taste[("pet_type", s)] > 0}
    if prefs_species and not contradicted:
        core.add(prefs_species)
    if not core:    # ничего не известно или анкета опровергнута: все виды без негатива
        core = {it["pet"].pet_type for it in items
                if taste[("pet_type", it["pet"].pet_type)] >= 0}

    recommended = [it for it in items if it["pet"].pet_type in core]
    pool = [it for it in items if it["pet"].pet_type not in core]
    pool.sort(key=lambda it: it["score"] + rng.uniform(-NOISE, NOISE), reverse=True)

    # 5. Смешиваем: explore_every рекомендаций, потом одна случайная
    feed = []
    while recommended or pool:
        for _ in range(explore_every):
            if recommended:
                feed.append(recommended.pop(0))
        if pool:
            item = pool.pop(0)
            item["source"] = "случайная"
            feed.append(item)
    return feed[:limit]