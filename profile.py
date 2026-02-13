from telegram import Update
from telegram.ext import ContextTypes
from db import User, ROLE_NAMES, ROLE_TO_MODEL, Session, ADMIN_IDS

# --- ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ ГЕНЕРАЦИИ ПРОФИЛЯ ---
async def _get_user_profile_text(user_id: int, fallback_name: str) -> str:
    """
    Генерирует текст профиля по ID пользователя.
    fallback_name - имя, которое покажем, если пользователя нет в базе.
    """
    session = Session()
    try:
        db_user = session.query(User).filter_by(user_id=user_id).first()
        
        if not db_user:
            return (
                f"❓ Пользователь {fallback_name} не найден в базе данных.\n"
                f"Возможно, он еще не писал в группе с ботом."
            )
        
        # Собираем роли
        roles_list = []
        id_ml_list = []
        
        for role_key, Model in ROLE_TO_MODEL.items():
            role_entry = session.query(Model).filter_by(user_id=user_id).first()
            if role_entry:
                roles_list.append(f"🔹 {ROLE_NAMES[role_key]}")
                # Используем простые строки, без Markdown разметки, чтобы не было ошибок
                id_ml_list.append(f"{ROLE_NAMES[role_key]}: {role_entry.id_ml}")
        
        if not roles_list:
            role_text = "🔹 Нет ролей"
        else:
            role_text = "\n".join(roles_list)
        
        id_text = "\n".join(id_ml_list) if id_ml_list else "Не указан"
        
        # Проверка на админа (берем из db.py или указываем здесь)
        # Если хотите хардкод, замените строку ниже на: is_admin = "Да" if user_id in [ВАШИ_ID] else "Нет"
        is_admin = "Да" if user_id in ADMIN_IDS else "Нет"
        
        # Формируем текст без Markdown (убрали звездочки и обратные кавычки)
        text = (
            f"👤 Профиль игрока\n\n"
            f"🏷 Имя: {db_user.first_name} {db_user.last_name or ''}\n"
            f"🔗 Ник: @{db_user.username if db_user.username else 'скрыт'}\n"
            f"🆔 ID TG: {db_user.user_id}\n"
            f"👑 Админ: {is_admin}\n\n"
            f"⚔️ Роли:\n{role_text}\n\n"
            f"🎮 Игровые ID:\n{id_text}"
        )
        return text
        
    finally:
        session.close()

# --- ХЕНДЛЕРЫ ---

async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Команда /me. Доступна всем (в ЛС и в группе).
    Показывает профиль того, кто вызвал команду.
    """
    user = update.effective_user
    text = await _get_user_profile_text(user.id, user.first_name)
    await update.message.reply_text(text)


async def who_is_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Реакция на сообщение "Кто" (или "кто") в ответ на сообщение пользователя.
    Работает только в группах.
    """
    # 1. Проверяем, что это группа
    if update.effective_chat.type not in ["group", "supergroup"]:
        return

    # 2. Проверяем, что это ответ на сообщение
    if not update.message or not update.message.reply_to_message:
        return

    # 3. Проверяем текст (должен быть "кто", без учета регистра)
    # strip() убирает пробелы по краям
    if not update.message.text or update.message.text.strip().lower() != "кто":
        return

    # Получаем того, чье сообщение цитировали
    target_user = update.message.reply_to_message.from_user
    
    # Защита: если ответили на сообщение самого бота
    if target_user.id == context.bot.id:
        await update.message.reply_text("Я всего лишь бот 🤖")
        return

    # Генерируем профиль
    text = await _get_user_profile_text(target_user.id, target_user.first_name)
    await update.message.reply_text(text)