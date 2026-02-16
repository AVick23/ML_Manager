"""
Модуль тегирования (призыва) игроков по ролям.
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from config import GROUP_ID, logger
from db import get_role_users, ROLE_NAMES, ROLE_TO_MODEL, Session
import state

ITEMS_PER_PAGE = 10
# Размер блока для тегирования (чтобы не спамить огромными сообщениями)
TAG_CHUNK_SIZE = 4


# ==========================================
# МЕНЮ ВЫБОРА РОЛИ ДЛЯ ТЕГА
# ==========================================

async def tag_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Меню выбора роли для тегирования"""
    query = update.callback_query
    await query.answer()
    
    buttons = [
        InlineKeyboardButton(name, callback_data=f"{state.CD_TEG_ROLE}:{key}:1")
        for key, name in ROLE_NAMES.items()
    ]
    keyboard = [buttons[i:i+2] for i in range(0, len(buttons), 2)]
    keyboard.append([InlineKeyboardButton("⬅ Назад в меню", callback_data=state.CD_BACK_TO_MENU)])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text("Выберите категорию для тега:", reply_markup=reply_markup)


# ==========================================
# ВЫБОР ИГРОКА С ПАГИНАЦИЕЙ
# ==========================================

async def teg_view_role_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Просмотр списка игроков роли для тегирования"""
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    role_key = parts[1]
    page = int(parts[2]) if len(parts) > 2 else 1

    if role_key not in ROLE_NAMES:
        await query.edit_message_text("❌ Неверная категория.")
        return

    users = await get_role_users(role_key)
    if not users:
        await query.edit_message_text("В этой категории никто не зарегистрирован.")
        return

    total_pages = (len(users) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
    start_index = (page - 1) * ITEMS_PER_PAGE
    end_index = start_index + ITEMS_PER_PAGE
    page_users = users[start_index:end_index]

    buttons = []
    for u in page_users:
        if u.username:
            btn_text = f"@{u.username}"
            callback = f"{state.CD_TEG_USER}:{u.user_id}:{role_key}"
            buttons.append(InlineKeyboardButton(btn_text, callback_data=callback))
        
    keyboard = []
    if buttons:
        keyboard += [buttons[i:i+2] for i in range(0, len(buttons), 2)]
    
    if users:
        keyboard.append([InlineKeyboardButton("📣 Тегнуть всех", callback_data=f"{state.CD_TEG_ALL}:{role_key}")])

    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton("⬅️", callback_data=f"{state.CD_TEG_ROLE}:{role_key}:{page-1}"))
    nav_buttons.append(InlineKeyboardButton(f"📄 {page}/{total_pages}", callback_data="ignore"))
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton("➡️", callback_data=f"{state.CD_TEG_ROLE}:{role_key}:{page+1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)

    keyboard.append([InlineKeyboardButton("⬅ Назад", callback_data=state.CD_TEG_BACK)])

    await query.edit_message_text(
        f"Выберите игрока ({ROLE_NAMES[role_key]}) для тега (Стр. {page}/{total_pages}):",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def teg_back_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Возврат к меню выбора роли"""
    query = update.callback_query
    await query.answer()
    await tag_menu(update, context)


# ==========================================
# ТЕГ ОДНОГО ИГРОКА
# ==========================================

async def teg_single_user_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Тегирование одного игрока"""
    query = update.callback_query
    await query.answer()

    _, user_id_str, role_key = query.data.split(":", 2)
    user_id = int(user_id_str)

    role_model = ROLE_TO_MODEL.get(role_key)
    
    if not role_model:
        await query.message.reply_text("❌ Ошибка: неверная роль.")
        return
    
    session = Session()
    try:
        role_user = session.query(role_model).filter_by(user_id=user_id).first()
        
        if not role_user or not role_user.username:
            await query.message.reply_text("❌ Пользователь не найден или у него нет username.")
            return
        id_ml = role_user.id_ml or "не указан"
    finally:
        session.close()

    # Получаем ID группы
    group_id = GROUP_ID or context.bot_data.get("last_admin_group_id")
    
    if not group_id:
        await query.message.reply_text(
            "❌ Не удалось определить группу для тега. Напишите что-нибудь в группе."
        )
        return

    try:
        role_name = ROLE_NAMES.get(role_key, "неизвестная роль")
        await context.bot.send_message(
            chat_id=group_id,
            text=f"📢 Тег по роли «{role_name}»:\n👉 @{role_user.username} (ID ML: {id_ml})\nТы нужен на землях рассвета"
        )
        await query.message.reply_text(f"✅ @{role_user.username} тегнут в группу!")
        logger.info(f"📢 Тег @%s отправлен в группу %s", role_user.username, group_id)
    except Exception as e:
        await query.message.reply_text(f"❌ Ошибка отправки: {e}")
        logger.error(f"❌ Ошибка тегирования: {e}")


# ==========================================
# ТЕГ ВСЕХ ИГРОКОВ (ИСПРАВЛЕНО)
# ==========================================

async def teg_all_users_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Тегирование всех игроков роли с одинаковым форматированием"""
    query = update.callback_query
    await query.answer()

    role_key = query.data.split(":", 1)[1]
    users = await get_role_users(role_key)

    users_with_username = [u for u in users if u.username]
    if not users_with_username:
        await query.message.reply_text("❌ В категории нет пользователей с username.")
        return

    group_id = GROUP_ID or context.bot_data.get("last_admin_group_id")
    
    if not group_id:
        await query.message.reply_text(
            "❌ Не удалось определить группу. Напишите любое сообщение в группе."
        )
        return

    # Разбиваем на части по 4 человека
    chunks = [users_with_username[i:i+TAG_CHUNK_SIZE] for i in range(0, len(users_with_username), TAG_CHUNK_SIZE)]

    try:
        role_name = ROLE_NAMES.get(role_key, "неизвестная роль")

        for i, chunk in enumerate(chunks):
            lines = []
            
            # Заголовок добавляем ТОЛЬКО в первое сообщение
            if i == 0:
                lines.append(f"📢 Тег по роли «{role_name}»:\nТы нужен на землях рассвета")
            
            # Форматируем каждого игрока в блоке одинаково: с ID ML
            for u in chunk:
                id_ml = u.id_ml or "не указан"
                lines.append(f"• @{u.username} (ID ML: {id_ml})")
            
            message = "\n".join(lines)
            
            await context.bot.send_message(chat_id=group_id, text=message)
        
        await query.message.reply_text("✅ Теги отправлены!")
        logger.info(f"📢 Тег всех игроков роли {role_key} отправлен в группу {group_id}")
    except Exception as e:
        await query.message.reply_text(f"❌ Ошибка при теге всех: {e}")
        logger.error(f"❌ Ошибка тегирования всех: {e}")