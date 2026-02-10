import asyncio
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, String, UniqueConstraint
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()

# Список админов из .env
ADMIN_IDS = [int(uid.strip()) for uid in os.getenv("ADMIN_IDS", "").split(",") if uid.strip()]

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, unique=True, nullable=False)
    first_name = Column(String, nullable=False)
    last_name = Column(String)
    username = Column(String)
    # Поле admin УДАЛЕНО отсюда
    
    def __repr__(self):
        return f"<User(id={self.id}, tg_id={self.user_id}, name='{self.first_name}')>"
    
class RegistrationBase(Base):
    __abstract__ = True
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, unique=True, nullable=False)
    first_name = Column(String, nullable=False)
    last_name = Column(String)
    username = Column(String)
    id_ml = Column(Integer)  
    
class Middle(RegistrationBase):
    __tablename__ = 'middle'

class Gold(RegistrationBase):
    __tablename__ = 'gold'

class Les(RegistrationBase):
    __tablename__ = 'les'

class Roam(RegistrationBase):
    __tablename__ = 'roam'

class Adk(RegistrationBase):
    __tablename__ = 'adk'

class Moderator(RegistrationBase):
    __tablename__ = 'moderator'

ROLE_NAMES = {
    "middle": "Мидл",
    "gold": "Голда",
    "les": "Лес",
    "roam": "Роум",
    "adk": "АДК",
    "moderator": "Модератор",
}

ROLE_TO_MODEL = {
    "middle": Middle,
    "gold": Gold,
    "les": Les,
    "roam": Roam,
    "adk": Adk,
    "moderator": Moderator,
}

DB_NAME = "bot_users.db"
engine = create_engine(f'sqlite:///{DB_NAME}')
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)

# --- Синхронные функции ---

def get_all_users_sync():
    session = Session()
    try:
        return session.query(User).all()
    finally:
        session.close()

def get_role_users_sync(role_model):
    session = Session()
    try:
        return session.query(role_model).all()
    finally:
        session.close()

def find_user_by_username_sync(username: str):
    if not username:
        return None
    clean_username = username.lstrip('@')
    session = Session()
    try:
        return session.query(User).filter(User.username == clean_username).first()
    finally:
        session.close()

def add_user_to_role_sync(role_model, user: User, id_ml: int):
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
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()

def remove_user_from_role_sync(role_model, user_id: int):
    session = Session()
    try:
        entry = session.query(role_model).filter_by(user_id=user_id).first()
        if not entry:
            raise ValueError("Пользователь не найден в этой категории")
        session.delete(entry)
        session.commit()
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()

def is_user_admin_sync(user_id: int) -> bool:
    # Проверяем наличие ID в константе ADMIN_IDS
    return user_id in ADMIN_IDS

def save_user_sync(user_id, first_name, last_name, username):
    # УБРАЛИ параметр is_admin
    session = Session()
    try:
        user = session.query(User).filter_by(user_id=user_id).first()
        if user:
            user.first_name = first_name
            user.last_name = last_name
            user.username = username
        else:
            user = User(
                user_id=user_id,
                first_name=first_name,
                last_name=last_name,
                username=username
            )
            session.add(user)
        session.commit()
        return user.id
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()

# --- Асинхронные обертки ---

async def get_all_users():
    return await asyncio.to_thread(get_all_users_sync)

async def get_role_users(role_key: str):
    model = ROLE_TO_MODEL[role_key]
    return await asyncio.to_thread(get_role_users_sync, model)

async def find_user_by_username(username: str):
    return await asyncio.to_thread(find_user_by_username_sync, username)

async def add_user_to_role(role_key: str, user: User, id_ml: int):
    model = ROLE_TO_MODEL[role_key]
    return await asyncio.to_thread(add_user_to_role_sync, model, user, id_ml)

async def remove_user_from_role(role_key: str, user_id: int):
    model = ROLE_TO_MODEL[role_key]
    return await asyncio.to_thread(remove_user_from_role_sync, model, user_id)

async def is_user_admin(user_id: int) -> bool:
    return await asyncio.to_thread(is_user_admin_sync, user_id)

async def save_user(*args, **kwargs):
    return await asyncio.to_thread(save_user_sync, *args, **kwargs)