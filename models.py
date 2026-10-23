from sqlalchemy import ForeignKey, String, Integer, Boolean, DateTime, Column, Float, Text, UniqueConstraint, Date, \
    CheckConstraint
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    password = Column(String, nullable=False)
    email = Column(String, nullable=False, unique=True, index=True)
    phone = Column(String, nullable=False, unique=True)
    birthday_date = Column(Date)
    city = Column(String)
    account_status = Column(String, default='active')
    date_creation = Column(DateTime, default=datetime.now)
    #Связи
    sellers = relationship('Seller', back_populates='user', cascade="all, delete")
    swipes = relationship('Swipe', back_populates='user', cascade="all, delete")

class Seller(Base):
    __tablename__ = 'sellers'
    __table_args__ = (CheckConstraint("seller_type IN ('individual', 'company')", name='sellers_check'),)
    id = Column(Integer, primary_key=True, index=True)
    seller_type = Column(String, nullable=False) # физлицо / юрлицо
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=True, index=True)
    name = Column(String)
    email = Column(String)
    phone = Column(String)
    inn = Column(String)
    city = Column(String)
    address = Column(Text)
    account_status = Column(String, default='active')
    date_creation = Column(DateTime, default=datetime.now)
    #Связи
    user = relationship('User', back_populates='sellers')
    pets = relationship('Pet', back_populates='seller', cascade="all, delete")
    chats = relationship('Chat', back_populates='seller', cascade="all, delete")

class Pet(Base):
    __tablename__ = 'pets'
    id = Column(Integer, primary_key=True, index = True)
    seller_id = Column(Integer, ForeignKey('sellers.id', ondelete='CASCADE'), nullable=False, index=True)
    pet_type = Column(String, nullable=False)
    nickname = Column(String)
    breed = Column(String)
    gender = Column(String, nullable=False)
    price = Column(Float, default=0.0)
    age_in_months = Column(Integer)
    color = Column(String)
    weight = Column(Float)
    vaccinations = Column(Boolean, default=False)
    documents = Column(Boolean, default=False)
    publication_status = Column(String, default='active') #, index=True)
    publication_date = Column(DateTime, default=datetime.now)
    #Связи
    seller = relationship('Seller', back_populates='pets')
    swipes = relationship('Swipe', back_populates='pet', cascade='all, delete')

class Swipe(Base):
    __tablename__ = 'swipes'
    id = Column(Integer, primary_key=True, index = True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    pet_id = Column(Integer, ForeignKey('pets.id', ondelete='CASCADE'), nullable=False, index=True)
    direction = Column(String, nullable=False) # left / right
    date = Column(DateTime, default=datetime.now)
    # Защита от дублирования свайпов: пользователь может свайпнуть питомца только 1 раз
    __table_args__ = (
        UniqueConstraint("user_id", "pet_id", name="uix_user_pet_swipe"),
        CheckConstraint("direction IN ('left', 'right')", name='swipe_direction_check'),
    )
    # Связи
    user = relationship('User', back_populates='swipes')
    pet = relationship('Pet', back_populates='swipes')
    chat = relationship('Chat', back_populates='swipe', uselist=False, cascade="all, delete")

class Chat(Base):
    __tablename__ = 'chats'
    id = Column(Integer, primary_key=True, index = True)
    seller_id = Column(Integer, ForeignKey('sellers.id', ondelete='CASCADE'), nullable=False, index=True)
    swipe_id = Column(Integer, ForeignKey('swipes.id', ondelete='CASCADE'), nullable=False, unique=True)
    last_message_date = Column(DateTime, default=datetime.now)
    date_creation = Column(DateTime, default=datetime.now)
    #Связи
    seller = relationship('Seller', back_populates='chats')
    swipe = relationship('Swipe', back_populates='chat')
    messages = relationship('Message', back_populates='chat', cascade="all, delete")

class Message(Base):
    __tablename__ = 'messages'
    __table_args__ = (CheckConstraint("sender_type IN ('user', 'seller')", name='sender_check'),)
    id = Column(Integer, primary_key=True, index = True)
    chat_id = Column(Integer, ForeignKey('chats.id', ondelete='CASCADE'), nullable=False, index=True)
    sender_type = Column(String, nullable=False) #user / seller
    sender_id = Column(Integer, nullable=False)
    text = Column(String, nullable=False)
    sent_date = Column(DateTime, default=datetime.now)
    is_read = Column(Boolean, default=False)
    #Связи
    chat = relationship('Chat', back_populates='messages')

class Notification(Base):
    __tablename__ = 'notifications'
    __table_args__ = (CheckConstraint("recipient_type IN ('user', 'seller')", name='recipient_check'),)
    id = Column(Integer, primary_key=True, index = True)
    recipient_type = Column(String, nullable=False) #user / seller
    recipient_id = Column(Integer, nullable=False)
    notification_type = Column(String, nullable=False)
    notification_date = Column(DateTime, default=datetime.now)
