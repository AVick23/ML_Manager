from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from db import (
    get_all_users, is_user_admin, 
    ROLE_NAMES, ROLE_TO_MODEL, Session, User, ADMIN_IDS
)
import state

async def settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not await is_user_admin(query.from_user.id):
        await query.edit_message_text("❌ Эта функция доступна только администраторам.")
        return

    text = (
        "⚙️ **Настройки и Утилиты**\n\n"
        "Управление базой данных и документация."
    )
    
    keyboard = [
        [
            InlineKeyboardButton("🗑 Удалить игрока (Из базы)", callback_data="settings_del_user"),
            InlineKeyboardButton("ℹ️ Инструкция", callback_data="settings_info")
        ],
        [InlineKeyboardButton("⬅ Назад в меню", callback_data=state.CD_BACK_TO_MENU)]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def settings_del_user_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ Запуск процедуры полного удаления игрока """
    query = update.callback_query
    await query.answer()
    
    context.user_data["settings_state"] = "awaiting_global_del_username"
    
    await query.edit_message_text(
        "🗑 **Полное удаление игрока**\n\n"
        "⚠️ Это действие удалит игрока:\n"
        "1. Из таблицы `users`.\n"
        "2. Из ВСЕХ ролей (Мидл, Лес и т.д.).\n\n"
        "Введите @username игрока для удаления:",
        parse_mode='Markdown'
    )

async def handle_global_delete_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ Обработка ввода логина для удаления """
    # Проверяем, что мы в нужном состоянии
    if context.user_data.get("settings_state") != "awaiting_global_del_username":
        return
    
    if not await is_user_admin(update.effective_user.id):
        return

    username = update.message.text.strip()
    if not username.startswith('@'):
        return await update.message.reply_text("❌ Введите username с @ (например: @username).")

    session = Session()
    try:
        user = session.query(User).filter(User.username == username.lstrip('@')).first()
        if not user:
            return await update.message.reply_text("❌ Пользователь с таким ником не найден в базе.")
        
        # Собираем информацию об удаляемых ролях для отчета
        deleted_roles = []
        
        # Удаляем из всех ролей
        for role_key, Model in ROLE_TO_MODEL.items():
            entry = session.query(Model).filter_by(user_id=user.user_id).first()
            if entry:
                session.delete(entry)
                deleted_roles.append(ROLE_NAMES[role_key])
        
        # Удаляем самого пользователя
        session.delete(user)
        session.commit()
        
        # Очищаем состояние
        context.user_data.pop("settings_state", None)
        
        roles_str = ", ".join(deleted_roles) if deleted_roles else "Нет"
        await update.message.reply_text(
            f"✅ Игрок @{user.username} полностью удален из базы данных.\n"
            f"Удалены роли: {roles_str}."
        )
        
    except Exception as e:
        session.rollback()
        await update.message.reply_text(f"❌ Ошибка при удалении: {e}")
    finally:
        session.close()

async def settings_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ Полная инструкция по боту """
    query = update.callback_query
    await query.answer()
    
    text = (
        "📖 **Инструкция к ML Manager Bot**\n\n"
        
        "🤖 **Основные команды:**\n"
        "• `/start` — Главное меню бота.\n"
        "• `/me` — Посмотреть свой игровой профиль (роль и ID).\n\n"
        
        "👥 **Для Игроков:**\n"
        "Вы можете использовать кнопку **\"Тегнуть игроков\"**, чтобы позвать конкретную роль (например, Мидл) в общий чат.\n\n"
        
        "🔧 **Для Администраторов:**\n\n"
        
        "📝 **Регистрация игроков:**\n"
        "1. Меню -> \"Регистрация ролей\".\n"
        "2. Выберите нужную роль (Мидл, Лес и т.д.).\n"
        "3. Нажмите \"➕ Добавить\".\n"
        "4. Выберите первую букву имени игрока.\n"
        "5. Кликните на игрока из списка и введите его **ID из Mobile Legends**.\n\n"
        
        "🗑 **Удаление игроков:**\n"
        "• **Из роли:** Меню -> Регистрация -> Выбрать роль -> \"Удалить\".\n"
        "• **Полностью:** Настройки -> \"Удалить игрока\" (удаляет из базы навсегда).\n\n"
        
        "📊 **Управление списками:**\n"
        "Все списки (Общий и по ролям) поддерживают пагинацию (по 10 человек на страницу). Используйте стрелки навигации.\n\n"
        
        "📢 **Призывы (Теги):**\n"
        "Админ выбирает роль -> \"Тегнуть всех\". Бот автоматически разобьет список по 4 человека и отправит в группу, где админ последний раз был активен."
    )
    
    keyboard = [[InlineKeyboardButton("⬅ Назад", callback_data=state.CD_MENU_SETTINGS)]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')