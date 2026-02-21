"""
Модуль работы с базой данных.
Содержит модели SQLAlchemy и функции для работы с пользователями, ролями, событиями и статистикой.
"""
import asyncio
from sqlalchemy import create_engine, Column, Integer, String, UniqueConstraint, ForeignKey, DateTime, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from datetime import datetime

# Импортируем настройки из config.py
from config import ADMIN_IDS, DB_NAME, logger

Base = declarative_base()


# ==========================================
# МОДЕЛИ БАЗЫ ДАННЫХ
# ==========================================

class User(Base):
    """Основная таблица пользователей"""
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, unique=True, nullable=False)
    first_name = Column(String, nullable=False)
    last_name = Column(String)
    username = Column(String)
    
    # Связи для статистики
    match_participations = relationship("MatchParticipant", back_populates="user")
    ratings_received = relationship("RoleRating", back_populates="user", foreign_keys="RoleRating.user_id")
    
    def __repr__(self):
        return f"<User(id={self.id}, tg_id={self.user_id}, name='{self.first_name}')>"


class RegistrationBase(Base):
    """Базовый класс для таблиц ролей"""
    __abstract__ = True
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, unique=True, nullable=False)
    first_name = Column(String, nullable=False)
    last_name = Column(String)
    username = Column(String)
    id_ml = Column(Integer)


# --- РОЛИ ---

class Middle(RegistrationBase):
    __tablename__ = 'middle'


class Exp(RegistrationBase):
    __tablename__ = 'exp'


class Gold(RegistrationBase):
    __tablename__ = 'gold'


class Les(RegistrationBase):
    __tablename__ = 'les'


class Roam(RegistrationBase):
    __tablename__ = 'roam'


class Moderator(RegistrationBase):
    __tablename__ = 'moderator'


# --- СОБЫТИЯ (ИВЕНТЫ) ---

class Event(Base):
    """Таблица событий/игр"""
    __tablename__ = 'events'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String, nullable=False)
    event_time = Column(String, nullable=False)
    status = Column(String, default='active')  # active, lineup_fixed, completed
    
    # Связи
    participants = relationship("EventParticipant", back_populates="event")
    matches = relationship("EventMatch", back_populates="event")
    
    def __repr__(self):
        return f"<Event(id={self.id}, title='{self.title}', time='{self.event_time}', status='{self.status}')>"


class EventParticipant(Base):
    """Таблица участников событий"""
    __tablename__ = 'event_participants'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(Integer, ForeignKey('events.id'), nullable=False)
    user_id = Column(Integer, ForeignKey('users.user_id'), nullable=False)
    status = Column(String, default='Active')
    
    # Связи
    event = relationship("Event", back_populates="participants")
    user = relationship("User")
    
    __table_args__ = (UniqueConstraint('event_id', 'user_id', name='uq_event_user'),)


# --- МИКСЫ И СТАТИСТИКА ---

class EventMatch(Base):
    """Зафиксированный матч (результат микса)"""
    __tablename__ = 'event_matches'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(Integer, ForeignKey('events.id'), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Связи
    event = relationship("Event", back_populates="matches")
    participants = relationship("MatchParticipant", back_populates="match")
    
    def __repr__(self):
        return f"<EventMatch(id={self.id}, event_id={self.event_id}, created_at={self.created_at})>"


class MatchParticipant(Base):
    """Участник конкретного матча (после фиксации состава)"""
    __tablename__ = 'match_participants'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    match_id = Column(Integer, ForeignKey('event_matches.id'), nullable=False)
    user_id = Column(Integer, ForeignKey('users.user_id'), nullable=False)
    team = Column(String(10))  # 'red', 'blue', 'spectator'
    role_played = Column(String(20))  # роль, которую реально исполнял (из профиля или 'random')
    played = Column(Boolean, default=True)  # играл ли вообще (true для red/blue, false для spectators)
    
    # Связи
    match = relationship("EventMatch", back_populates="participants")
    user = relationship("User", back_populates="match_participations")
    ratings = relationship("RoleRating", back_populates="match_participant")
    
    def __repr__(self):
        return f"<MatchParticipant(id={self.id}, user_id={self.user_id}, team='{self.team}', played={self.played})>"


class RoleRating(Base):
    """Оценки за игру по ролям"""
    __tablename__ = 'role_ratings'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    match_participant_id = Column(Integer, ForeignKey('match_participants.id'), nullable=False)
    user_id = Column(Integer, ForeignKey('users.user_id'), nullable=False)  # кому оценка
    rating = Column(Integer)  # 1-5
    comment = Column(String, nullable=True)
    rated_by = Column(Integer, ForeignKey('users.user_id'))  # кто оценил (админ)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Связи
    match_participant = relationship("MatchParticipant", back_populates="ratings")
    user = relationship("User", foreign_keys=[user_id], back_populates="ratings_received")
    rater = relationship("User", foreign_keys=[rated_by])
    
    def __repr__(self):
        return f"<RoleRating(id={self.id}, user_id={self.user_id}, rating={self.rating})>"


# --- СЛОВАРИ РОЛЕЙ ---

ROLE_NAMES = {
    "middle": "Мидл",
    "gold": "Голда",
    "les": "Лес",
    "roam": "Роум",
    "exp": "Экспа",
    "moderator": "Модератор",
}

ROLE_TO_MODEL = {
    "middle": Middle,
    "gold": Gold,
    "les": Les,
    "roam": Roam,
    "exp": Exp,
    "moderator": Moderator,
}

ROLE_LIST = ["middle", "gold", "les", "roam", "exp"]  # основные роли для игры


# ==========================================
# ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ
# ==========================================

engine = create_engine(f'sqlite:///{DB_NAME}')
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)

logger.info(f"📦 База данных инициализирована: {DB_NAME}")


# ==========================================
# СИНХРОННЫЕ ФУНКЦИИ
# ==========================================

def get_all_users_sync():
    """Получает всех пользователей из базы"""
    session = Session()
    try:
        return session.query(User).all()
    finally:
        session.close()


def get_role_users_sync(role_model):
    """Получает всех пользователей указанной роли"""
    session = Session()
    try:
        return session.query(role_model).all()
    finally:
        session.close()


def find_user_by_username_sync(username: str):
    """Находит пользователя по username"""
    if not username:
        return None
    clean_username = username.lstrip('@')
    session = Session()
    try:
        return session.query(User).filter(User.username == clean_username).first()
    finally:
        session.close()


def add_user_to_role_sync(role_model, user: User, id_ml: int):
    """Добавляет пользователя в роль"""
    session = Session()
    try:
        existing = session.query(role_model).filter_by(user_id=user.user_id).first()
        if existing:
            raise ValueError("Пользователь уже зарегистрирован в этой роли")

        new_entry = role_model(
            user_id=user.user_id,
            first_name=user.first_name,
            last_name=user.last_name,
            username=user.username,
            id_ml=id_ml
        )
        session.add(new_entry)
        session.commit()
        logger.info(f"✅ Пользователь {user.user_id} добавлен в роль с ID ML: {id_ml}")
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()


def remove_user_from_role_sync(role_model, user_id: int):
    """Удаляет пользователя из роли"""
    session = Session()
    try:
        entry = session.query(role_model).filter_by(user_id=user_id).first()
        if not entry:
            raise ValueError("Пользователь не найден в этой категории")
        session.delete(entry)
        session.commit()
        logger.info(f"🗑 Пользователь {user_id} удалён из роли")
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()


def is_user_admin_sync(user_id: int) -> bool:
    """
    Проверяет, является ли пользователь администратором.
    Использует ADMIN_IDS из config.py.
    """
    return user_id in ADMIN_IDS


def save_user_sync(user_id, first_name, last_name, username):
    """Сохраняет или обновляет пользователя в базе"""
    session = Session()
    try:
        user = session.query(User).filter_by(user_id=user_id).first()
        if user:
            user.first_name = first_name
            user.last_name = last_name
            user.username = username
            logger.debug(f"📝 Пользователь {user_id} обновлён")
        else:
            user = User(
                user_id=user_id,
                first_name=first_name,
                last_name=last_name,
                username=username
            )
            session.add(user)
            logger.info(f"➕ Новый пользователь {user_id} добавлен в базу")
        session.commit()
        return user.id
    except Exception as e:
        session.rollback()
        logger.error(f"❌ Ошибка сохранения пользователя: {e}")
        raise e
    finally:
        session.close()


def get_user_role_sync(user_id: int):
    """
    Получает основную роль пользователя (если есть).
    Возвращает ключ роли или None.
    """
    session = Session()
    try:
        for role_key, model in ROLE_TO_MODEL.items():
            entry = session.query(model).filter_by(user_id=user_id).first()
            if entry:
                return role_key
        return None
    finally:
        session.close()


def get_user_statistics_sync(user_id: int):
    """
    Получает статистику пользователя:
    - количество сыгранных матчей
    - средняя оценка
    - оценки по ролям
    """
    session = Session()
    try:
        # Количество сыгранных матчей (где played=True)
        played_matches = session.query(MatchParticipant).filter_by(
            user_id=user_id, 
            played=True
        ).count()
        
        # Средняя оценка по всем ролям
        from sqlalchemy import func
        avg_rating = session.query(func.avg(RoleRating.rating)).filter(
            RoleRating.user_id == user_id
        ).scalar()
        avg_rating = round(avg_rating, 1) if avg_rating else None
        
        # Оценки по ролям (группировка по role_played)
        role_stats = {}
        for role in ROLE_LIST + [None]:  # включая игры без роли
            # Получаем все оценки для этой роли
            query = session.query(RoleRating).join(MatchParticipant).filter(
                RoleRating.user_id == user_id
            )
            if role:
                query = query.filter(MatchParticipant.role_played == role)
            else:
                query = query.filter(MatchParticipant.role_played.is_(None))
            
            ratings = [r.rating for r in query.all()]
            if ratings:
                role_stats[role or 'unknown'] = {
                    'count': len(ratings),
                    'avg': round(sum(ratings) / len(ratings), 1)
                }
        
        # Количество матчей, где был зрителем
        spectator_count = session.query(MatchParticipant).filter_by(
            user_id=user_id,
            team='spectator'
        ).count()
        
        return {
            'played_matches': played_matches,
            'avg_rating': avg_rating,
            'role_stats': role_stats,
            'spectator_count': spectator_count
        }
    finally:
        session.close()


def get_event_with_lineup_sync(event_id: int):
    """
    Проверяет, есть ли у события зафиксированный состав (матч)
    """
    session = Session()
    try:
        return session.query(EventMatch).filter_by(event_id=event_id).first() is not None
    finally:
        session.close()


# ==========================================
# АСИНХРОННЫЕ ОБЁРТКИ
# ==========================================

async def get_all_users():
    """Асинхронная обёртка для get_all_users_sync"""
    return await asyncio.to_thread(get_all_users_sync)


async def get_role_users(role_key: str):
    """Асинхронная обёртка для получения пользователей роли"""
    model = ROLE_TO_MODEL[role_key]
    return await asyncio.to_thread(get_role_users_sync, model)


async def find_user_by_username(username: str):
    """Асинхронная обёртка для поиска по username"""
    return await asyncio.to_thread(find_user_by_username_sync, username)


async def add_user_to_role(role_key: str, user: User, id_ml: int):
    """Асинхронная обёртка для добавления в роль"""
    model = ROLE_TO_MODEL[role_key]
    return await asyncio.to_thread(add_user_to_role_sync, model, user, id_ml)


async def remove_user_from_role(role_key: str, user_id: int):
    """Асинхронная обёртка для удаления из роли"""
    model = ROLE_TO_MODEL[role_key]
    return await asyncio.to_thread(remove_user_from_role_sync, model, user_id)


async def is_user_admin(user_id: int) -> bool:
    """Асинхронная обёртка для проверки админа"""
    return await asyncio.to_thread(is_user_admin_sync, user_id)


async def save_user(*args, **kwargs):
    """Асинхронная обёртка для сохранения пользователя"""
    return await asyncio.to_thread(save_user_sync, *args, **kwargs)


async def get_user_role(user_id: int):
    """Асинхронная обёртка для получения роли пользователя"""
    return await asyncio.to_thread(get_user_role_sync, user_id)


async def get_user_statistics(user_id: int):
    """Асинхронная обёртка для получения статистики пользователя"""
    return await asyncio.to_thread(get_user_statistics_sync, user_id)


async def get_event_with_lineup(event_id: int):
    """Асинхронная обёртка для проверки наличия состава"""
    return await asyncio.to_thread(get_event_with_lineup_sync, event_id)