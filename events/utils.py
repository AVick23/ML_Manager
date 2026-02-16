"""
utils.py
Вспомогательные функции для работы с событиями: БД, форматирование, константы.
"""
from datetime import datetime, timedelta, timezone
from telegram import User as TgUser

from db import Event, EventParticipant, User, Session
from config import GROUP_ID, logger

# Константы
DATE_FORMAT = "%Y-%m-%d %H:%M"
MSK_TZ = timezone(timedelta(hours=3))

def get_group_id(context) -> int | None:
    """Безопасное получение ID группы для уведомлений"""
    if GROUP_ID:
        return GROUP_ID
    return context.bot_data.get("last_admin_group_id")

def format_user_mention(user: User) -> str:
    """Красивое упоминание пользователя для списков"""
    if user.username:
        return f"@{user.username}"
    elif user.first_name:
        return user.first_name
    return f"Игрок #{user.user_id}"

async def save_user_from_tg(tg_user: TgUser):
    """Сохраняет или обновляет пользователя в БД"""
    from db import save_user
    await save_user(
        user_id=tg_user.id,
        first_name=tg_user.first_name,
        last_name=tg_user.last_name,
        username=tg_user.username
    )

def get_event_by_id(session, event_id: int) -> Event | None:
    """Получение события по ID"""
    return session.query(Event).get(event_id)

def get_upcoming_events(session) -> list[Event]:
    """Получение списка предстоящих событий"""
    return session.query(Event).filter(
        Event.status == 'Scheduled'
    ).order_by(Event.event_time).all()

def get_event_participants(session, event_id: int):
    """Получение участников события"""
    return session.query(EventParticipant).filter_by(event_id=event_id).all()

def is_user_participant(session, event_id: int, user_id: int) -> bool:
    """Проверка, записан ли пользователь на событие"""
    return session.query(EventParticipant).filter_by(
        event_id=event_id, user_id=user_id
    ).first() is not None