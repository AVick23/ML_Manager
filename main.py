import asyncio
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import Column, Integer, String, Boolean, UniqueConstraint
from sqlalchemy.orm import declarative_base
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
import os
from dotenv import load_dotenv
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ChatMemberHandler,
    CallbackQueryHandler,
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

class Exp(RegistrationBase):
    __tablename__ = 'exp'

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
    "exp": "Экспа",
    "les": "Лес",
    "roam": "Роум",
    "adk": "Адк",
    "moderator": "Модератор",
}

ROLE_TO_MODEL = {
    "middle": Middle,
    "exp": Exp,
    "les": Les,
    "roam": Roam,
    "adk": Adk,
    "moderator": Moderator,
}

load_dotenv()

DB_NAME = "bot_users.db"
engine = create_engine(f'sqlite:///{DB_NAME}')
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)

def get_all_users_sync():
    session = Session()
    try:
        return session.query(User).all()
    finally:
        session.close()

async def get_all_users():
    return await asyncio.to_thread(get_all_users_sync)

def get_role_users_sync(role_model):
    session = Session()
    try:
        return session.query(role_model).all()
    finally:
        session.close()

async def get_role_users(role_key: str):
    model = ROLE_TO_MODEL[role_key]
    return await asyncio.to_thread(get_role_users_sync, model)

def find_user_by_username_sync(username: str):
    if not username:
        return None
    clean_username = username.lstrip('@')
    session = Session()
    try:
        return session.query(User).filter(User.username == clean_username).first()
    finally:
        session.close()

async def find_user_by_username(username: str):
    return await asyncio.to_thread(find_user_by_username_sync, username)

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

async def add_user_to_role(role_key: str, user: User, id_ml: int):
    model = ROLE_TO_MODEL[role_key]
    return await asyncio.to_thread(add_user_to_role_sync, model, user, id_ml)

def is_user_admin_sync(user_id: int) -> bool:
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

    if new_member.user.id == context.bot.id:
        if new_member.status == "member":
            await update.effective_chat.send_message("✅ Привет! Я запишу всех участников при их первом сообщении.")
        return

    if new_member.status not in ["left", "kicked"]:
        user = new_member.user
        try:
            chat_member = await context.bot.get_chat_member(
                chat_id=update.effective_chat.id,
                user_id=user.id
            )
            is_admin = (chat_member.status == "creator")
        except Exception:
            is_admin = False

        await save_user(
            user_id=user.id,
            first_name=user.first_name,
            last_name=user.last_name,
            username=user.username,
            is_admin=is_admin
        )
        
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        await update.message.reply_text(
            "❌ Эта команда доступна только в личных сообщениях с ботом."
        )
        return
    
    user_id = update.effective_user.id

    if not await is_user_admin(user_id):
        await update.message.reply_text(
            "❌ У вас нет прав на использование этой команды. "
            "Только администраторы бота могут просматривать список пользователей."
        )
        return
    
    await update.message.reply_text(
        "Привет! Я бот, который записывает данные пользователей в группах.\n"
        "Когда я добавлен в группу, я автоматически назначаю админом того, кто меня добавил.\n"
        "Все пользователи, пишущие в группе, записываются в базу данных."
    )

async def handle_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type not in ["group", "supergroup"]:
        return

    user = update.effective_user
    chat = update.effective_chat

    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
        is_admin = member.status in ("creator")
    except Exception:
        is_admin = False

    await save_user(
        user_id=user.id,
        first_name=user.first_name,
        last_name=user.last_name,
        username=user.username,
        is_admin=is_admin
    )
    
    if is_admin:
        context.bot_data["last_admin_group_id"] = chat.id

async def all_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        await update.message.reply_text(
            "❌ Эта команда доступна только в личных сообщениях с ботом."
        )
        return
    
    user_id = update.effective_user.id

    if not await is_user_admin(user_id):
        await update.message.reply_text(
            "❌ У вас нет прав на использование этой команды. "
            "Только администраторы бота могут просматривать список пользователей."
        )
        return

    users = await get_all_users()
    if not users:
        await update.message.reply_text("Нет зарегистрированных пользователей.")
        return

    total = len(users)
    admin_count = sum(1 for user in users if user.admin)
    
    message = f"👥 Список пользователей (всего: {total}, админов: {admin_count})\n\n"
    
    for idx, user in enumerate(users):
        full_name = f"{user.first_name} {user.last_name or ''}".strip() or "Не указано имя"
        username = f"@{user.username}" if user.username else "нет username"
        admin_status = "✅ Админ" if user.admin else "❌ Не админ"
        message += f"{idx+1}. ID: {user.user_id} | {full_name} ({username}) - {admin_status}\n"
    
    await update.message.reply_text(message)

async def view_role_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    role_key = query.data.split(":", 1)[1]
    if role_key not in ROLE_TO_MODEL:
        await query.edit_message_text("❌ Ошибка роли.")
        return

    users = await get_role_users(role_key)
    text = f"👥 {ROLE_NAMES[role_key]}\n\n"
    if not users:
        text += "Пока никто не зарегистрирован."
    else:
        for u in users:
            name = f"{u.first_name} {u.last_name or ''}".strip() or "Не указано имя"
            tag = f"@{u.username}" if u.username else "нет username"
            id_ml = u.id_ml or "не указан"
            text += f"• {name} ({tag}) — ID: {id_ml}\n"

    keyboard = [
        [
            InlineKeyboardButton("➕ Добавить", callback_data=f"add_to:{role_key}"),
            InlineKeyboardButton("🗑 Удалить", callback_data=f"del_from:{role_key}")
        ],
        [InlineKeyboardButton("⬅ Назад", callback_data="back_to_roles")]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

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

async def remove_user_from_role(role_key: str, user_id: int):
    model = ROLE_TO_MODEL[role_key]
    return await asyncio.to_thread(remove_user_from_role_sync, model, user_id)
    
async def add_to_role_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    role_key = query.data.split(":", 1)[1]
    context.user_data.update({
        "reg_state": "awaiting_username",
        "reg_role": role_key
    })

    await query.edit_message_text(
        f"Введите username пользователя (начинается с @), которого хотите добавить в {ROLE_NAMES[role_key]}:"
    )

async def del_from_role_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    role_key = query.data.split(":", 1)[1]
    context.user_data.update({
        "reg_state": "awaiting_username_del",
        "reg_role": role_key
    })

    await query.edit_message_text(
        f"Введите username пользователя (начинается с @), которого хотите удалить из {ROLE_NAMES[role_key]}:"
    )
    
async def handle_registration_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not await is_user_admin(user_id):
        await update.message.reply_text("❌ У вас нет прав на использование этой команды.")
        return

    state = context.user_data.get("reg_state")
    if not state:
        return

    role_key = context.user_data.get("reg_role")
    if not role_key:
        return

    text = update.message.text.strip()

    if state == "awaiting_username":
        if not text.startswith('@'):
            await update.message.reply_text("❌ Username должен начинаться с @. Попробуйте снова.")
            return

        user = await find_user_by_username(text)
        if not user:
            await update.message.reply_text(
                f"❌ Пользователь {text} не найден в базе. Убедитесь, что он писал в группу и был записан ботом."
            )
            return

        context.user_data["reg_candidate_user"] = user
        context.user_data["reg_state"] = "awaiting_idml"

        full_name = f"{user.first_name} {user.last_name or ''}".strip()
        await update.message.reply_text(
            f"Найден: {full_name} (@{user.username})\n"
            "Теперь введите его игровой ID в Mobile Legends (только цифры):"
        )

    elif state == "awaiting_idml":
        try:
            id_ml = int(text)
            if id_ml <= 0:
                raise ValueError("ID должен быть положительным")
        except (ValueError, TypeError):
            await update.message.reply_text(
                "❌ ID должен быть положительным целым числом (например: 123456789). "
                "Пожалуйста, введите только цифры без пробелов, букв или символов."
            )
            return

        candidate = context.user_data.get("reg_candidate_user")
        if not candidate:
            await update.message.reply_text("❌ Ошибка: кандидат не найден. Начните сначала.")
            context.user_data.clear()
            return

        try:
            await add_user_to_role(role_key, candidate, id_ml)
            await update.message.reply_text(
                f"✅ Пользователь @{candidate.username} добавлен в {ROLE_NAMES[role_key]} с ID {id_ml}!"
            )
        except ValueError as e:
            await update.message.reply_text(f"❌ {e}")
        except Exception as e:
            await update.message.reply_text("❌ Ошибка при сохранении. Обратитесь к разработчику.")
            print(f"Ошибка регистрации: {e}")

        context.user_data.clear()

    elif state == "awaiting_username_del":
        if not text.startswith('@'):
            await update.message.reply_text("❌ Username должен начинаться с @. Попробуйте снова.")
            return

        user = await find_user_by_username(text)
        if not user:
            await update.message.reply_text(f"❌ Пользователь {text} не найден в базе.")
            return

        try:
            await remove_user_from_role(role_key, user.user_id)
            await update.message.reply_text(
                f"✅ Пользователь @{user.username} удалён из {ROLE_NAMES[role_key]}."
            )
        except ValueError as e:
            await update.message.reply_text(f"❌ {e}")
        except Exception as e:
            await update.message.reply_text("❌ Ошибка при удалении. Обратитесь к разработчику.")
            print(f"Ошибка удаления: {e}")

        context.user_data.clear()

async def reg_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        await update.message.reply_text(
            "❌ Эта команда доступна только в личных сообщениях с ботом."
        )
        return
    
    user_id = update.effective_user.id

    if not await is_user_admin(user_id):
        await update.message.reply_text("❌ Только администраторы могут использовать команду /reg.")
        return

    buttons = [
        InlineKeyboardButton(name, callback_data=f"view_role:{key}")
        for key, name in ROLE_NAMES.items()
    ]
    keyboard = [buttons[i:i+2] for i in range(0, len(buttons), 2)]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text("Выберите категорию:", reply_markup=reply_markup)
    
async def teg_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    buttons = [
        InlineKeyboardButton(name, callback_data=f"teg_role:{key}")
        for key, name in ROLE_NAMES.items()
    ]
    keyboard = [buttons[i:i+2] for i in range(0, len(buttons), 2)]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text("Выберите категорию для тега:", reply_markup=reply_markup)
    
async def teg_view_role_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    role_key = query.data.split(":", 1)[1]
    if role_key not in ROLE_TO_MODEL:
        await query.edit_message_text("❌ Неверная категория.")
        return

    users = await get_role_users(role_key)
    if not users:
        await query.edit_message_text("В этой категории никто не зарегистрирован.")
        return

    buttons = []
    for u in users:
        if u.username:
            btn_text = f"@{u.username}"
            callback = f"teg_user:{u.user_id}:{role_key}"
            buttons.append(InlineKeyboardButton(btn_text, callback_data=callback))
        
    keyboard = [buttons[i:i+2] for i in range(0, len(buttons), 2)]
    keyboard.append([InlineKeyboardButton("📣 Тегнуть всех", callback_data=f"teg_all:{role_key}")])
    keyboard.append([InlineKeyboardButton("⬅ Назад", callback_data="teg_back")])

    await query.edit_message_text(
        f"Выберите пользователя для тега в категории {ROLE_NAMES[role_key]}:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def teg_single_user_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    _, user_id_str, role_key = query.data.split(":", 2)
    user_id = int(user_id_str)

    
    role_model = ROLE_TO_MODEL[role_key]
    session = Session()
    try:
        role_user = session.query(role_model).filter_by(user_id=user_id).first()
        if not role_user or not role_user.username:
            await query.message.reply_text("❌ Пользователь не найден в этой категории или у него нет username.")
            return
        id_ml = role_user.id_ml or "не указан"
    finally:
        session.close()

    group_id = context.bot_data.get("last_admin_group_id")
    if not group_id:
        await query.message.reply_text(
            "❌ Не удалось определить группу для тега. Напишите что-нибудь в группе как админ, затем повторите."
        )
        return

    try:
        role_name = ROLE_NAMES.get(role_key, "неизвестная роль")
        await context.bot.send_message(
            chat_id=group_id,
            text=f"📢 Тег по роли «{role_name}»:\n👉 @{role_user.username} (ID ML: {id_ml})]+\n Ты нужен на землях рассвета"
        )
        await query.message.reply_text(f"✅ @{role_user.username} тегнут в группу с ID ML: {id_ml}!")
    except Exception as e:
        await query.message.reply_text(f"❌ Ошибка отправки: {e}")
        
async def teg_all_users_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    role_key = query.data.split(":", 1)[1]
    users = await get_role_users(role_key)

    users_with_username = [u for u in users if u.username]
    if not users_with_username:
        await query.message.reply_text("❌ В категории нет пользователей с username.")
        return

    group_id = context.bot_data.get("last_admin_group_id")
    if not group_id:
        await query.message.reply_text(
            "❌ Не удалось определить группу. Напишите в группе как админ, затем повторите."
        )
        return

    chunks = [users_with_username[i:i+4] for i in range(0, len(users_with_username), 4)]

    try:
        role_name = ROLE_NAMES.get(role_key, "неизвестная роль")

        
        for i, chunk in enumerate(chunks):
            if i == 0:
                lines = [f"📢 Тег по роли «{role_name}»:\nТы нужен на землях рассвета"]
                for u in chunk:
                    id_ml = u.id_ml or "не указан"
                    lines.append(f"• @{u.username} (ID ML: {id_ml})")
                message = "\n".join(lines)
            else:
                
                message = " ".join(f"@{u.username}" for u in chunk)
            
            await context.bot.send_message(chat_id=group_id, text=message)
    except Exception as e:
        await query.message.reply_text(f"❌ Ошибка при теге всех: {e}")
        
async def teg_back_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    buttons = [
        InlineKeyboardButton(name, callback_data=f"teg_role:{key}")
        for key, name in ROLE_NAMES.items()
    ]
    keyboard = [buttons[i:i+2] for i in range(0, len(buttons), 2)]
    await query.edit_message_text(
        "Выберите категорию для тега:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def back_to_roles_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    buttons = [
        InlineKeyboardButton(name, callback_data=f"view_role:{key}")
        for key, name in ROLE_NAMES.items()
    ]
    keyboard = [buttons[i:i+2] for i in range(0, len(buttons), 2)]
    await query.edit_message_text("Выберите категорию:", reply_markup=InlineKeyboardMarkup(keyboard))
    
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
    
    bot_token = os.getenv("BOT_TOKEN")
    if not bot_token:
        raise ValueError("❌ Токен бота не найден! Убедитесь, что в .env есть строка BOT_TOKEN=...")

    application = Application.builder().token(bot_token).build()
    application.add_error_handler(error_handler)
    
    application.add_handler(ChatMemberHandler(on_chat_member_update))
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("all", all_command))
    application.add_handler(CommandHandler("reg", reg_command))
    application.add_handler(CommandHandler("teg", teg_command))
    application.add_handler(MessageHandler(filters.ChatType.GROUPS, handle_group_message))
    
    application.add_handler(CallbackQueryHandler(view_role_handler, pattern=r"^view_role:"))
    application.add_handler(CallbackQueryHandler(add_to_role_start, pattern=r"^add_to:"))
    application.add_handler(CallbackQueryHandler(del_from_role_start, pattern=r"^del_from:"))
    application.add_handler(CallbackQueryHandler(back_to_roles_handler, pattern=r"^back_to_roles$"))

    application.add_handler(CallbackQueryHandler(teg_view_role_handler, pattern=r"^teg_role:"))
    application.add_handler(CallbackQueryHandler(teg_single_user_handler, pattern=r"^teg_user:"))
    application.add_handler(CallbackQueryHandler(teg_all_users_handler, pattern=r"^teg_all:"))
    application.add_handler(CallbackQueryHandler(teg_back_handler, pattern=r"^teg_back$"))
    
    application.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND,
            handle_registration_input
        )
    )
    
    application.run_polling()

if __name__ == "__main__":
    main()