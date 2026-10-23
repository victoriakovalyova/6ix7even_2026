from datetime import date, datetime, timedelta

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, String, and_

import reco_feed
from database import Base
from models import Pet

# ---------- Настройки тарифов ----------
FREE_DAILY_SWIPES = 10      # свайпов в день на бесплатном тарифе
PREMIUM_DAILY_SWIPES = 50   # свайпов в день на премиуме
PREMIUM_DAYS = 30           # на сколько дней оформляется подписка
PROMO_EVERY = 6             # каждая 6-я карточка в ленте рекламная


class Subscription(Base):
    """Премиум клиента (owner_type='user') или продавца (owner_type='seller')."""
    __tablename__ = "subscriptions"
    owner_type = Column(String, primary_key=True)
    owner_id = Column(Integer, primary_key=True)
    premium_until = Column(DateTime)


class SwipeUsage(Base):
    """Сколько свайпов пользователь сделал в конкретный день."""
    __tablename__ = "swipe_usage"
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    day = Column(Date, primary_key=True)
    count = Column(Integer, default=0)


# ---------- Подписка ----------

def premium_until(db, owner_type, owner_id):
    """Дата окончания премиума или None, если его нет или он закончился."""
    sub = db.get(Subscription, (owner_type, owner_id))
    if sub and sub.premium_until and sub.premium_until > datetime.now():
        return sub.premium_until
    return None


def is_premium(db, owner_type, owner_id):
    return premium_until(db, owner_type, owner_id) is not None


def activate_premium(db, owner_type, owner_id, days=PREMIUM_DAYS):
    """Оформляет или продлевает премиум (оплата имитируется). Возвращает дату окончания."""
    now = datetime.now()
    sub = db.get(Subscription, (owner_type, owner_id))
    if sub is None:
        sub = Subscription(owner_type=owner_type, owner_id=owner_id,
                           premium_until=now + timedelta(days=days))
        db.add(sub)
    else:
        start = sub.premium_until if sub.premium_until and sub.premium_until > now else now
        sub.premium_until = start + timedelta(days=days)
    db.commit()
    return sub.premium_until


def cancel_premium(db, owner_type, owner_id):
    sub = db.get(Subscription, (owner_type, owner_id))
    if sub:
        sub.premium_until = None
        db.commit()


# ---------- Лимит свайпов ----------

def daily_limit(db, user_id):
    return PREMIUM_DAILY_SWIPES if is_premium(db, "user", user_id) else FREE_DAILY_SWIPES


def swipes_used(db, user_id):
    row = db.get(SwipeUsage, (user_id, date.today()))
    return row.count if row else 0


def swipes_left(db, user_id):
    return max(0, daily_limit(db, user_id) - swipes_used(db, user_id))


def register_swipe(db, user_id):
    """Засчитывает свайп. Возвращает False, если лимит на сегодня исчерпан."""
    if swipes_left(db, user_id) <= 0:
        return False
    row = db.get(SwipeUsage, (user_id, date.today()))
    if row is None:
        row = SwipeUsage(user_id=user_id, day=date.today(), count=0)
        db.add(row)
    row.count += 1
    db.commit()
    return True


# ---------- Реклама ----------

def promoted_pet_ids(db):
    """Активные питомцы тех продавцов, у которых сейчас действует премиум."""
    rows = (db.query(Pet.id)
            .join(Subscription, and_(Subscription.owner_type == "seller",
                                     Subscription.owner_id == Pet.seller_id))
            .filter(Subscription.premium_until > datetime.now(),
                    Pet.publication_status == "active")
            .all())
    return {pet_id for (pet_id,) in rows}


def eligible_promoted(feed, promoted_ids):
    """Все продвигаемые питомцы из ленты. Показываются ВСЕ (продавец заплатил),
    но самые подходящие человеку идут первыми."""
    promo = [p for p in feed if p["id"] in promoted_ids]
    promo.sort(key=lambda p: p["score"], reverse=True)
    return promo


def apply_promotion(feed, promoted_ids, every=PROMO_EVERY):
    """Возвращает ленту, где каждая every-я карточка рекламная."""
    promo = eligible_promoted(feed, promoted_ids)
    promo_ids = {p["id"] for p in promo}
    organic = [p for p in feed if p["id"] not in promo_ids]

    result = []
    while organic or promo:
        for _ in range(every - 1):
            if organic:
                result.append(organic.pop(0))
        if promo:
            item = promo.pop(0)
            item["source"] = "реклама"
            result.append(item)
    return result


def build_feed(db, user_id, limit=10, seed=None):
    """Органическая лента + рекламные слоты. Именно это потом вернёт GET /feed."""
    feed = reco_feed.get_feed(db, user_id, limit=10**6, seed=seed)   # сначала вся лента
    feed = apply_promotion(feed, promoted_pet_ids(db))                # потом реклама
    return feed[:limit]                                               # и только потом порция