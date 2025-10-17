from sqlalchemy import Column, Integer, String, Boolean, UniqueConstraint
from sqlalchemy.orm import declarative_base


Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, unique=True, nullable=False)
    first_name = Column(String, nullable=False)
    last_name = Column(String)
    username = Column(String)
    admin = Column(Boolean, default=False)
    
    __table_args__ = (UniqueConstraint('user_id', name='uq_user_id'),)
    
    def __repr__(self):
        return f"<User(id={self.id}, tg_id={self.user_id}, name='{self.first_name}', admin={self.admin})>"
    
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