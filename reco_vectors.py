from datetime import datetime

import numpy as np
from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, Text

import embedders
from database import Base
from models import Pet, Swipe

DISLIKE_WEIGHT = 0.5   # дизлайк влияет вдвое слабее лайка

TYPE_RU = {"cat": "кот", "dog": "собака", "hamster": "хомяк", "fish": "рыбка",
           "parrot": "попугай", "cow": "корова", "rabbit": "кролик"}

# ВРЕМЕННО: в базе пока нет поля description, поэтому для теста берём описания отсюда.
# Когда в Pet появится description, этот словарь больше не используется.
DEMO_DESCRIPTIONS = {
    1: "Спокойная, ласковая, любит сидеть на руках, подходит для квартиры.",
    2: "Игривый, активный, любит гулять во дворе.",
    3: "Крупная, дружелюбная, любит играть с детьми.",
    4: "Крупный, ласковый, ладит с детьми и другими животными.",
    5: "Энергичный, умный, нужна большая нагрузка и просторный двор.",
    6: "Добрая, обожает детей, очень активная.",
}


class PetVector(Base):
    """Наша собственная таблица: вектор питомца для каждой модели."""
    __tablename__ = "pet_vectors"
    pet_id = Column(Integer, ForeignKey("pets.id", ondelete="CASCADE"), primary_key=True)
    model = Column(String, primary_key=True)          # какой моделью посчитан
    source_text = Column(Text, nullable=False)        # из какого текста
    vector = Column(JSON, nullable=False)
    updated_at = Column(DateTime, default=datetime.now)


def pet_text(pet):
    """Склеивает смысловые поля питомца в один текст.
    Возраст, вес, цену и город сюда не кладём: их сравниваем правилами."""
    kind = TYPE_RU.get(pet.pet_type, pet.pet_type)
    parts = [kind]
    if pet.breed:
        parts.append(f"порода {pet.breed}")
    if pet.color:
        parts.append(f"окрас {pet.color}")
    text = ", ".join(parts) + "."
    description = getattr(pet, "description", None) or DEMO_DESCRIPTIONS.get(pet.id)
    if description:
        text += " " + description
    return text


def text_vector(text):
    """Вектор произвольного текста (например, запрос пользователя)."""
    return embedders.encode([text])[0]


def sync_pet_vectors(db):
    """Считает векторы тем питомцам, у кого их нет или изменился текст.
    Возвращает, сколько питомцев обработано."""
    model = embedders.model_name()
    existing = {v.pet_id: v for v in db.query(PetVector).filter(PetVector.model == model)}

    todo = []
    for pet in db.query(Pet).all():
        text = pet_text(pet)
        row = existing.get(pet.id)
        if row is None or row.source_text != text:
            todo.append((pet, text, row))
    if not todo:
        return 0

    matrix = embedders.encode([text for _, text, _ in todo])
    for (pet, text, row), vec in zip(todo, matrix):
        if row is None:
            db.add(PetVector(pet_id=pet.id, model=model, source_text=text, vector=vec.tolist()))
        else:
            row.source_text = text
            row.vector = vec.tolist()
            row.updated_at = datetime.now()
    db.commit()
    return len(todo)


def user_vector(db, user_id):
    """Вектор вкуса: лайки (right) притягивают, дизлайки (left) отталкивают слабее.
    Если свайпов нет, возвращает None (холодный старт)."""
    rows = (db.query(Swipe.direction, PetVector.vector)
            .join(PetVector, PetVector.pet_id == Swipe.pet_id)
            .filter(Swipe.user_id == user_id, PetVector.model == embedders.model_name())
            .all())
    if not rows:
        return None
    total = np.zeros(len(rows[0][1]))
    for direction, vec in rows:
        weight = 1.0 if direction == "right" else -DISLIKE_WEIGHT
        total += weight * np.array(vec)
    norm = np.linalg.norm(total)
    return total / norm if norm > 0 else None


def rank_pets_by_vector(db, vec, pet_ids=None):
    """Список (id питомца, сходство) от самого близкого к самому далёкому."""
    result = []
    for row in db.query(PetVector).filter(PetVector.model == embedders.model_name()):
        if pet_ids is None or row.pet_id in pet_ids:
            result.append((row.pet_id, float(np.dot(vec, np.array(row.vector)))))
    result.sort(key=lambda item: item[1], reverse=True)
    return result