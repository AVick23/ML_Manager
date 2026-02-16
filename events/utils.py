"""
utils.py
Вспомогательные функции.
"""
from datetime import datetime, timedelta, timezone
from telegram import User as TgUser
import html

from db import Event, EventParticipant, User, Session
from config import GROUP_ID, logger

DATE_FORMAT = "%Y-%m-%d %H:%M"
MSK_TZ = timezone(timedelta(hours=3))

def get_group_id(context) -> int | None:
    if GROUP_ID:
        return GROUP_ID
    return context.bot_data.get("last_admin_group_id")

def format_user_mention(user: User) -> str:
    """Создает кликабельное упоминание в HTML формате"""
    if not user:
        return "Неизвестный"
    
    name = html.escape(user.first_name or "Игрок")
    if user.username:
        return f"<a href='tg://resolve?domain={user.username}'>{name}</a>"
    else:
        # Упоминание по ID работает только если юзер писал боту в ЛС
        return f"<a href='tg://user?id={user.user_id}'>{name}</a>"

async def save_user_from_tg(tg_user: TgUser):
    from db import save_user
    await save_user(
        user_id=tg_user.id,
        first_name=tg_user.first_name,
        last_name=tg_user.last_name,
        username=tg_user.username
    )

def get_event_by_id(session, event_id: int) -> Event | None:
    return session.query(Event).get(event_id)

def get_upcoming_events(session) -> list[Event]:
    return session.query(Event).filter(
        Event.status == 'Scheduled'
    ).order_by(Event.event_time).all()

def get_event_participants(session, event_id: int):
    return session.query(EventParticipant).filter_by(event_id=event_id).all()

def is_user_participant(session, event_id: int, user_id: int) -> bool:
    return session.query(EventParticipant).filter_by(
        event_id=event_id, user_id=user_id
    ).first() is not None