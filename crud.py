from sqlalchemy.orm import Session
from datetime import datetime
from sqlalchemy.exc import IntegrityError
from models import User, Seller, Pet, Swipe, Chat, Message, Notification


def create_user(db: Session, name: str, password: str, email: str, phone: str):
    user = User(name=name, password=password, email=email, phone=phone)
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ValueError('Пользователя с таким email или телефоном не существует')
    db.refresh(user)
    return user

def get_user_by_id(db: Session, user_id: int):
    return db.get(User, user_id)

def get_user_by_email(db: Session, email: str):
    return db.query(User).filter(User.email == email).first()

def create_seller(db: Session, seller_type: str, user_id : int =None,
                  name: str =None, email: str =None, phone: str =None):
    if seller_type not in ('individual', 'company'):
        raise ValueError("seller_type: individual или company")
    seller = Seller(seller_type=seller_type, user_id=user_id, name=name, email=email, phone=phone)
    db.add(seller)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ValueError('Не удалось создать продавца')
    db.refresh(seller)
    return seller

def get_seller_by_id(db: Session, seller_id: int):
    return db.get(Seller, seller_id)

def create_pet(db: Session, seller_id: int, pet_type: str, gender: str, nickname: str =None, breed: str =None,
               price: float =0.0, age_in_months: int =None):
    if db.get(Seller, seller_id) is None:
        raise ValueError('Продавца с таким id не существует')
    pet = Pet(seller_id=seller_id, pet_type=pet_type, gender=gender, nickname=nickname, breed=breed, price=price, age_in_months=age_in_months)
    db.add(pet)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ValueError('Не удалось создать анкету питомца')
    db.refresh(pet)
    return pet

def get_pet_by_id(db: Session, pet_id: int):
    return db.get(Pet, pet_id)

def get_pets_forms(db: Session, user_id: int):      #Активные несвайпнутые анкеты
    swiped_user = db.query(Swipe.pet_id).filter(Swipe.user_id == user_id)
    return db.query(Pet).filter(Pet.publication_status == 'active', ~Pet.id.in_(swiped_user)).all()

def set_pet_status(db: Session, pet_id: int, status: str):
    if status not in ('active', 'archived', 'sold'):
        raise ValueError('status: active, archived или sold')
    pet = db.get(Pet, pet_id)
    if pet is None:
        raise ValueError('Питомец не найден')
    pet.publication_status = status
    db.commit()
    return pet

def create_swipe(db: Session, user_id: int, pet_id: int, direction: str):
    if direction not in ('left', 'right'):
        raise ValueError("direction: left или right")
    pet = db.get(Pet, pet_id)
    if pet is None:
        raise ValueError('Питомец не найден')
    if db.query(Swipe).filter(Swipe.user_id == user_id, Swipe.pet_id == pet_id).first() is not None:
        raise ValueError('Этот питомец уже был свайпнут')
    swipe = Swipe(user_id=user_id, pet_id=pet_id, direction=direction)
    db.add(swipe)
    chat = None
    try:
        db.flush()
        if direction == 'right':
            chat = Chat(seller_id=pet.seller_id, swipe_id=swipe.id)
            db.add(chat)
            db.add(Notification(recipient_type='seller', recipient_id=pet.seller_id, notification_type='new_chat'))
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ValueError('Этот питомец уже был свайпнут')
    db.refresh(swipe)
    return swipe, chat

def get_chats_by_user(db: Session, user_id: int):
    return (db.query(Chat).join(Swipe, Chat.swipe_id == Swipe.id)
            .filter(Swipe.user_id == user_id).all())

def get_chats_by_seller(db: Session, seller_id: int):
    return db.query(Chat).filter(Chat.seller_id == seller_id).all()

def send_message(db: Session, chat_id: int, sender_type: str, sender_id: int, text: str):
    if sender_type not in ('user', 'seller'):
        raise ValueError("sender_type: 'user' или 'seller'")
    chat = db.get(Chat, chat_id)
    if chat is None:
        raise ValueError('Чат не найден')
    msg = Message(chat_id=chat_id, sender_type=sender_type,
                  sender_id=sender_id, text=text)
    db.add(msg)
    chat.last_message_date = datetime.now()
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ValueError('Не удалось отправить сообщение')
    db.refresh(msg)
    return msg

def get_messages(db: Session, chat_id: int):
    return (db.query(Message).filter(Message.chat_id == chat_id)
            .order_by(Message.sent_date).all())

def mark_chat_read(db: Session, chat_id, reader_type):
    if reader_type not in ('user', 'seller'):
        raise ValueError("reader_type: 'user' или 'seller'")
    messages = (db.query(Message).filter(Message.chat_id == chat_id, Message.sender_type != reader_type).all())
    for m in messages:
        m.is_read = True
    db.commit()

def get_notifications(db: Session, recipient_type, recipient_id):
    return (db.query(Notification).filter(Notification.recipient_type == recipient_type,
                                          Notification.recipient_id == recipient_id).all())