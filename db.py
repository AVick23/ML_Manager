"""
Модуль работы с базой данных.
Содержит модели SQLAlchemy и функции для работы с пользователями и ролями.
"""
import asyncio
from sqlalchemy import create_engine, Column, Integer, String, UniqueConstraint
from sqlalchemy.orm import declarative_base, sessionmaker

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


# --- СОБЫТИЯ (CRM) ---

class Event(Base):
    """Таблица событий/игр"""
    __tablename__ = 'events'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String, nullable=False)
    event_time = Column(String, nullable=False)
    status = Column(String, default='Scheduled')
    
    def __repr__(self):
        return f"<Event(id={self.id}, title='{self.title}', time='{self.event_time}')>"


class EventParticipant(Base):
    """Таблица участников событий"""
    __tablename__ = 'event_participants'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(Integer, nullable=False)
    user_id = Column(Integer, nullable=False)
    status = Column(String, default='Active')
    
    __table_args__ = (UniqueConstraint('event_id', 'user_id', name='uq_event_user'),)


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