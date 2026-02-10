from telegram import Update
from telegram.ext import ContextTypes
from db import User, ROLE_NAMES, ROLE_TO_MODEL, Session

async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ Показывает профиль отправителя (работает и в группе, и в ЛС) """
    user = update.effective_user
    
    # Ищем пользователя в базе
    session = Session()
    try:
        db_user = session.query(User).filter_by(user_id=user.id).first()
        
        if not db_user:
            text = (
                f"👋 Привет, {user.first_name}!\n\n"
                f"Я не нашел тебя в своей базе данных.\n"
                f"Напиши что-нибудь в группе с ботом, чтобы я тебя записал."
            )
        else:
            # Собираем роли
            roles_list = []
            id_ml_list = []
            
            for role_key, Model in ROLE_TO_MODEL.items():
                role_entry = session.query(Model).filter_by(user_id=user.id).first()
                if role_entry:
                    roles_list.append(f"🔹 {ROLE_NAMES[role_key]}")
                    id_ml_list.append(f"{ROLE_NAMES[role_key]}: `{role_entry.id_ml}`")
            
            if not roles_list:
                role_text = "🔹 Нет ролей"
            else:
                role_text = "\n".join(roles_list)
            
            id_text = "\n".join(id_ml_list) if id_ml_list else "Не указан"
            
            is_admin = "Да" if user.id in [1716576518, 1373472999] else "Нет"
            
            text = (
                f"👤 **Профиль игрока**\n\n"
                f"🏷 Имя: {db_user.first_name} {db_user.last_name or ''}\n"
                f"🔗 Ник: @{db_user.username if db_user.username else 'скрыт'}\n"
                f"🆔 ID TG: `{db_user.user_id}`\n"
                f"👑 Админ: {is_admin}\n\n"
                f"⚔️ **Роли:**\n{role_text}\n\n"
                f"🎮 **Игровые ID:**\n{id_text}"
            )
            
        await update.message.reply_text(text, parse_mode='Markdown')
        
    finally:
        session.close()