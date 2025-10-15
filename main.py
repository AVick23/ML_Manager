import asyncio
from sqlalchemy import Column, Integer, String, Boolean, create_engine, UniqueConstraint
from sqlalchemy.orm import declarative_base, sessionmaker
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ChatMemberHandler,
    ContextTypes
)

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

DB_NAME = "bot_users.db"
engine = create_engine(f'sqlite:///{DB_NAME}')
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)

def escape_markdown_v2(text: str) -> str:
    """Экранирует все специальные символы для MarkdownV2 по спецификации Telegram"""
    if not text:
        return ""
    escape_chars = "_*[]()~`>#+-=|{}.!"
    for char in escape_chars:
        text = text.replace(char, f"\\{char}")
    return text

def get_all_users_sync():
    session = Session()
    try:
        return session.query(User).all()
    finally:
        session.close()

async def get_all_users():
    return await asyncio.to_thread(get_all_users_sync)

def is_user_admin_sync(user_id: int) -> bool:
    """Проверяет, является ли пользователь админом в БД"""
    session = Session()
    try:
        user = session.query(User).filter_by(user_id=user_id).first()
        return user is not None and user.admin
    finally:
        session.close()

async def is_user_admin(user_id: int) -> bool:
    return await asyncio.to_thread(is_user_admin_sync, user_id)

def save_user_sync(user_id, first_name, last_name, username, is_admin=None):
    session = Session()
    try:
        user = session.query(User).filter_by(user_id=user_id).first()
        if user:
            user.first_name = first_name
            user.last_name = last_name
            user.username = username
            if is_admin is not None:
                user.admin = is_admin
        else:
            admin_val = is_admin if is_admin is not None else False
            user = User(
                user_id=user_id,
                first_name=first_name,
                last_name=last_name,
                username=username,
                admin=admin_val
            )
            session.add(user)
        session.commit()
        return user.id
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()

async def save_user(*args, **kwargs):
    return await asyncio.to_thread(save_user_sync, *args, **kwargs)

async def on_chat_member_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.chat_member:
        return

    result = update.chat_member
    new_member = result.new_chat_member
    old_member = result.old_chat_member

    if new_member.user.id == context.bot.id:
        if new_member.status == "member" and (old_member is None or old_member.status == "left"):
            user = result.from_user
            await save_user(
                user_id=user.id,
                first_name=user.first_name,
                last_name=user.last_name,
                username=user.username,
                is_admin=True
            )
            username_str = f"@{user.username}" if user.username else "без username"
            await update.effective_chat.send_message(
                f"✅ Пользователь {user.first_name} ({username_str}) добавил меня в группу. "
                f"Он автоматически назначен админом!"
            )
        return

    if new_member.status not in ["left", "kicked"]:
        user = new_member.user
        is_admin = new_member.status == "administrator"
        await save_user(
            user_id=user.id,
            first_name=user.first_name,
            last_name=user.last_name,
            username=user.username,
            is_admin=is_admin
        )

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return
    await update.message.reply_text(
        "Привет! Я бот, который записывает данные пользователей в группах.\n"
        "Когда я добавлен в группу, я автоматически назначаю админом того, кто меня добавил.\n"
        "Все пользователи, пишущие в группе, записываются в базу данных."
    )

async def handle_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type not in ["group", "supergroup"]:
        return
    user = update.message.from_user
    await save_user(
        user_id=user.id,
        first_name=user.first_name,
        last_name=user.last_name,
        username=user.username,
        is_admin=None
    )

async def all_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /all - выводит всех пользователей из БД с нумерацией"""
    user_id = update.effective_user.id

    # 🔒 ПРОВЕРКА: Только админы в БД могут использовать /all
    if not await is_user_admin(user_id):
        await update.message.reply_text(
            "❌ У вас нет прав на использование этой команды. "
            "Только администраторы бота могут просматривать список пользователей."
        )
        return

    # ✅ Пользователь — админ, продолжаем
    users = await get_all_users()
    if not users:
        await update.message.reply_text("Нет зарегистрированных пользователей.")
        return

    total = len(users)
    admin_count = sum(1 for user in users if user.admin)
    
    # Формируем заголовок с экранированием скобок
    header = f"👥 *Список пользователей (всего: {total}, админов: {admin_count})*"
    header = header.replace('(', '\\(').replace(')', '\\)')
    message = f"{header}\n\n"
    
    for idx, user in enumerate(users):
        # Экранируем все поля для MarkdownV2
        first_name = escape_markdown_v2(user.first_name)
        last_name = escape_markdown_v2(user.last_name) if user.last_name else ""
        username = escape_markdown_v2(user.username) if user.username else ""
        admin_status = "✅ Админ" if user.admin else "❌ Не админ"
        
        # Формируем имя пользователя
        full_name = f"{first_name} {last_name}".strip()
        if not full_name:
            full_name = "Не указано имя"
        
        # Формируем строку для пользователя
        if username:
            user_str = f"{idx+1}. `{user.user_id}` | {full_name} (@{username}) - {admin_status}"
        else:
            user_str = f"{idx+1}. `{user.user_id}` | {full_name} - {admin_status}"
        
        # Экранируем всю строку целиком
        user_str = escape_markdown_v2(user_str)
        
        message += f"• {user_str}\n"
    
    await update.message.reply_text(
        message,
        parse_mode=ParseMode.MARKDOWN_V2,
        disable_web_page_preview=True
    )

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    if context.error is None:
        return
    if "NoneType" in str(context.error) and "new_chat_member" in str(context.error):
        return
    print(f"❌ Ошибка при обработке обновления: {context.error}")
    import traceback
    traceback.print_exc()

def main():
    print("🤖 Бот запущен. Добавьте меня в группу, чтобы начать!")
    
    application = Application.builder().token("8463651666:AAEMuvMoSIvruvUhicBPZg2Z46ZUbTKeA4c").build()
    application.add_error_handler(error_handler)
    
    application.add_handler(ChatMemberHandler(on_chat_member_update))
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("all", all_command))
    application.add_handler(MessageHandler(filters.ChatType.GROUPS, handle_group_message))
    
    application.run_polling()

if __name__ == "__main__":
    main()