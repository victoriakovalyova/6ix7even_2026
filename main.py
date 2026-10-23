from typing import Optional

import bcrypt
import uuid
from fastapi import FastAPI, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

import crud
from database import SessionLocal, engine, Base
from models import User, Seller, Pet, Swipe, Chat

# Создаём таблицы в PostgreSQL, если их ещё нет
Base.metadata.create_all(bind=engine)


# --- СХЕМЫ ЗАПРОСОВ ---
class RegisterRequest(BaseModel):
    email: str
    password: str
    displayName: str
    phone: str                      # в БД phone обязателен и уникален


class LoginRequest(BaseModel):
    email: str
    password: str


class CreateAnimalRequest(BaseModel):
    name: str                       # -> pets.nickname
    category: str                   # -> pets.pet_type (cat / dog ...)
    gender: str                     # в БД обязателен (male / female)
    is_free: bool = False
    price: float = 0.0
    breed: Optional[str] = None
    age_in_months: Optional[int] = None
    description: Optional[str] = None   # в модели Pet нет такого поля (см. примечание)


class SwipeRequest(BaseModel):
    direction: str                  # left / right


class MessageRequest(BaseModel):
    text: str


# --- ПРИЛОЖЕНИЕ ---
app = FastAPI(title="petomnik API", version="1.0")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(x_user_id: int = Header(...), db: Session = Depends(get_db)) -> User:
    user = crud.get_user_by_id(db, x_user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def get_or_create_seller(db: Session, user: User) -> Seller:
    """Профиль продавца-физлица для пользователя; создаётся при первой публикации."""
    seller = (db.query(Seller)
              .filter(Seller.user_id == user.id, Seller.seller_type == 'individual')
              .first())
    if seller is None:
        seller = crud.create_seller(db, 'individual', user_id=user.id,
                                    name=user.name, email=user.email, phone=user.phone)
    return seller


def pet_to_dict(pet: Pet) -> dict:
    return {
        "id": pet.id,
        "seller_id": pet.seller_id,
        "name": pet.nickname,
        "category": pet.pet_type,
        "breed": pet.breed,
        "gender": pet.gender,
        "price": pet.price,
        "is_free": not pet.price,
        "age_in_months": pet.age_in_months,
        "status": pet.publication_status,
        "created_at": pet.publication_date,
    }


def chat_to_dict(chat: Chat) -> dict:
    return {
        "id": chat.id,
        "seller_id": chat.seller_id,
        "user_id": chat.swipe.user_id,
        "pet_id": chat.swipe.pet_id,
        "last_message_date": chat.last_message_date,
    }


def message_to_dict(m) -> dict:
    return {
        "id": m.id,
        "chat_id": m.chat_id,
        "sender_type": m.sender_type,
        "sender_id": m.sender_id,
        "text": m.text,
        "sent_date": m.sent_date,
        "is_read": m.is_read,
    }


def get_chat_role(db: Session, chat_id: int, user: User):
    """Возвращает (chat, роль пользователя в чате, id отправителя)."""
    chat = db.get(Chat, chat_id)
    if chat is None:
        raise HTTPException(status_code=404, detail="Chat not found")
    if chat.swipe.user_id == user.id:
        return chat, "user", user.id
    if chat.seller.user_id == user.id:
        return chat, "seller", chat.seller_id
    raise HTTPException(status_code=403, detail="Forbidden")


# --- АККАУНТ И ПРОФИЛЬ ---
@app.post("/api/v1/auth/register")
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    if crud.get_user_by_email(db, req.email):
        raise HTTPException(status_code=409, detail="Email already exists")

    hashed = bcrypt.hashpw(req.password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    try:
        user = crud.create_user(db, name=req.displayName, password=hashed,
                                email=req.email, phone=req.phone)
    except ValueError:
        raise HTTPException(status_code=409, detail="Email or phone already exists")
    return {"token": str(uuid.uuid4()), "userId": user.id, "displayName": user.name}


@app.post("/api/v1/auth/login")
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = crud.get_user_by_email(db, req.email)
    if not user or not bcrypt.checkpw(req.password.encode("utf-8"), user.password.encode("utf-8")):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"token": str(uuid.uuid4()), "userId": user.id, "displayName": user.name}


@app.get("/api/v1/profile/me")
def get_profile(user: User = Depends(get_current_user)):
    return {"id": user.id, "email": user.email, "phone": user.phone,
            "city": user.city, "displayName": user.name}


# --- АНКЕТЫ ЖИВОТНЫХ ---
@app.post("/api/v1/animals")
def create_animal(req: CreateAnimalRequest, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    seller = get_or_create_seller(db, user)
    price = 0.0 if req.is_free else req.price
    try:
        pet = crud.create_pet(db, seller_id=seller.id, pet_type=req.category, gender=req.gender,
                              nickname=req.name, breed=req.breed, price=price,
                              age_in_months=req.age_in_months)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return pet_to_dict(pet)


@app.patch("/api/v1/animals/{animal_id}/status")
def change_animal_status(animal_id: int, status: str, user: User = Depends(get_current_user),
                         db: Session = Depends(get_db)):
    pet = crud.get_pet_by_id(db, animal_id)
    if pet is None:
        raise HTTPException(status_code=404, detail="Animal not found")
    if pet.seller.user_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    try:
        pet = crud.set_pet_status(db, animal_id, status)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return pet_to_dict(pet)


# --- ЛЕНТА И СВАЙПЫ ---
@app.get("/api/v1/feed")
def get_feed(category: Optional[str] = None, free: Optional[bool] = None,
             user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    swiped = db.query(Swipe.pet_id).filter(Swipe.user_id == user.id)

    query = (db.query(Pet)
             .join(Seller, Pet.seller_id == Seller.id)
             .filter(Pet.publication_status == "active",
                     ~Pet.id.in_(swiped),
                     or_(Seller.user_id.is_(None), Seller.user_id != user.id)))
    if category:
        query = query.filter(Pet.pet_type == category)
    if free is True:
        query = query.filter(Pet.price == 0)
    elif free is False:
        query = query.filter(Pet.price > 0)

    pets = query.order_by(Pet.publication_date.desc()).limit(10).all()
    return [pet_to_dict(p) for p in pets]


@app.post("/api/v1/feed/{animal_id}/swipe")
def swipe(animal_id: int, req: SwipeRequest, user: User = Depends(get_current_user),
          db: Session = Depends(get_db)):
    pet = crud.get_pet_by_id(db, animal_id)
    if pet is None:
        raise HTTPException(status_code=404, detail="Animal not found")
    if pet.seller.user_id == user.id:
        raise HTTPException(status_code=400, detail="Нельзя свайпать собственную анкету")

    try:
        swipe_obj, chat = crud.create_swipe(db, user.id, animal_id, req.direction)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"status": "ok", "swipe_id": swipe_obj.id, "chat_id": chat.id if chat else None}


# --- ЧАТЫ И СООБЩЕНИЯ ---
@app.get("/api/v1/chats")
def my_chats(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    chats = {c.id: c for c in crud.get_chats_by_user(db, user.id)}
    for seller in user.sellers:
        for c in crud.get_chats_by_seller(db, seller.id):
            chats[c.id] = c
    return [chat_to_dict(c) for c in chats.values()]


@app.get("/api/v1/chats/{chat_id}/messages")
def chat_messages(chat_id: int, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    _, role, _ = get_chat_role(db, chat_id, user)
    messages = crud.get_messages(db, chat_id)
    crud.mark_chat_read(db, chat_id, role)
    return [message_to_dict(m) for m in messages]


@app.post("/api/v1/chats/{chat_id}/messages")
def post_message(chat_id: int, req: MessageRequest, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    _, role, sender_id = get_chat_role(db, chat_id, user)
    try:
        msg = crud.send_message(db, chat_id, role, sender_id, req.text)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return message_to_dict(msg)


# --- УВЕДОМЛЕНИЯ ---
@app.get("/api/v1/notifications")
def my_notifications(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    result = [("user", user.id)] + [("seller", s.id) for s in user.sellers]
    out = []
    for rtype, rid in result:
        for n in crud.get_notifications(db, rtype, rid):
            out.append({"id": n.id, "recipient_type": n.recipient_type,
                        "type": n.notification_type, "date": n.notification_date})
    return out
