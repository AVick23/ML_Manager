"""
Модуль тегирования (призыва) игроков.
Интуитивный UX: Список -> Выбор -> Уведомление в группу.
Использует HTML для надежного форматирования.
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from config import GROUP_ID, logger
from db import get_role_users, ROLE_NAMES, ROLE_TO_MODEL, Session
import state

ITEMS_PER_PAGE = 10
TAG_CHUNK_SIZE = 4


# ==========================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==========================================

def get_group_id(context: ContextTypes.DEFAULT_TYPE) -> int | None:
    """Безопасное получение ID группы"""
    if GROUP_ID:
        return GROUP_ID
    return context.bot_data.get("last_admin_group_id")


# ==========================================
# МЕНЮ ВЫБОРА РОЛИ
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
    keyboard.append([InlineKeyboardButton("🏠 В главное меню", callback_data=state.CD_BACK_TO_MENU)])

    await query.edit_message_text(
        "📢 <b>Выберите роль для вызова:</b>", 
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )


# ==========================================
# СПИСОК ИГРОКОВ (ПАГИНАЦИЯ)
# ==========================================

async def teg_view_role_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Просмотр списка игроков роли"""
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
        await query.edit_message_text("👻 В этой категории пока никого нет.")
        return

    total_pages = (len(users) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
    start_index = (page - 1) * ITEMS_PER_PAGE
    end_index = start_index + ITEMS_PER_PAGE
    page_users = users[start_index:end_index]

    buttons = []
    for u in page_users:
        btn_text = f"@{u.username}" if u.username else (u.first_name or f"ID:{u.user_id}")
        callback = f"{state.CD_TEG_USER}:{u.user_id}:{role_key}"
        buttons.append(InlineKeyboardButton(btn_text, callback_data=callback))

    keyboard = []
    if buttons:
        keyboard += [buttons[i:i+2] for i in range(0, len(buttons), 2)]

    keyboard.append([
        InlineKeyboardButton(f"📣 Вызвать всех ({len(users)})", callback_data=f"{state.CD_TEG_ALL}:{role_key}")
    ])

    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton("⬅️", callback_data=f"{state.CD_TEG_ROLE}:{role_key}:{page-1}"))
    nav_buttons.append(InlineKeyboardButton(f"📄 {page}/{total_pages}", callback_data="ignore"))
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton("➡️", callback_data=f"{state.CD_TEG_ROLE}:{role_key}:{page+1}"))

    if len(nav_buttons) > 1:
        keyboard.append(nav_buttons)

    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data=state.CD_TEG_BACK)])

    await query.edit_message_text(
        f"👥 <b>{ROLE_NAMES[role_key]}</b> (Страница {page}):\nВыберите игрока или вызовите всех:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )


async def teg_back_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Возврат к меню выбора роли"""
    query = update.callback_query
    await query.answer()
    await tag_menu(update, context)


# ==========================================
# ЛОГИКА ТЕГГИРОВАНИЯ
# ==========================================

async def teg_single_user_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Тегирование одного игрока (HTML)"""
    query = update.callback_query
    await query.answer()

    _, user_id_str, role_key = query.data.split(":", 2)
    target_user_id = int(user_id_str)
    
    convener = query.from_user
    
    role_model = ROLE_TO_MODEL.get(role_key)
    if not role_model:
        await query.message.reply_text("❌ Ошибка роли.")
        return

    session = Session()
    try:
        role_user = session.query(role_model).filter_by(user_id=target_user_id).first()

        if not role_user:
            await query.message.reply_text("❌ Пользователь не найден.")
            return

        # Формируем упоминание цели
        if role_user.username:
            target_link = f"@{role_user.username}"
        else:
            # Если нет юзернейма, делаем кликабельную ссылку по ID
            target_link = f'<a href="tg://user?id={target_user_id}">{role_user.first_name or "Игрок"}</a>'
            
        id_ml = role_user.id_ml or "не указан"
    finally:
        session.close()

    group_id = get_group_id(context)
    if not group_id:
        await query.message.reply_text("❌ Не определена группа для отправки.")
        return

    text = (
        f"📢 <b>ВЫЗОВ ИГРОКА</b>\n\n"
        f"👤 Инициатор: {convener.mention_html()}\n"
        f"🎯 Цель: {target_link} (ID ML: {id_ml})\n"
        f"🛡 Роль: {ROLE_NAMES.get(role_key)}\n\n"
        f"⚔️ Требуется на землях рассвета!"
    )

    try:
        await context.bot.send_message(chat_id=group_id, text=text, parse_mode="HTML")
        await query.message.reply_text(f"✅ Вызов для {target_link} отправлен в группу!", parse_mode="HTML")
        logger.info(f"📢 User {convener.id} теганул {target_user_id}")
    except Exception as e:
        logger.error(f"Ошибка отправки тега: {e}")
        await query.message.reply_text(f"❌ Не удалось отправить: {e}")


async def teg_all_users_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Тегирование всех игроков роли (HTML)"""
    query = update.callback_query
    await query.answer()

    role_key = query.data.split(":", 1)[1]
    convener = query.from_user

    users = await get_role_users(role_key)
    users_with_username = [u for u in users if u.username]

    if not users_with_username:
        await query.message.reply_text("❌ В категории нет пользователей с username.")
        return

    group_id = get_group_id(context)
    if not group_id:
        await query.message.reply_text("❌ Не определена группа.")
        return

    chunks = [users_with_username[i:i+TAG_CHUNK_SIZE] for i in range(0, len(users_with_username), TAG_CHUNK_SIZE)]
    role_name = ROLE_NAMES.get(role_key, "Роль")

    try:
        for i, chunk in enumerate(chunks):
            lines = []
            
            if i == 0:
                lines.append(f"📢 <b>МАССОВЫЙ ВЫЗОВ</b> 📢\n🛡 Роль: <b>{role_name}</b>\n")

            for u in chunk:
                id_ml = u.id_ml or "нет"
                lines.append(f"• @{u.username} (ID: {id_ml})")

            await context.bot.send_message(
                chat_id=group_id, 
                text="\n".join(lines), 
                parse_mode="HTML"
            )

        # Финальное сообщение
        final_text = (
            f"👑 <b>ВЫЗОВ ЗАВЕРШЕН</b>\n\n"
            f"🙋‍♂️ Всех созывал: {convener.mention_html()}\n"
            f"⚡️ Всего игроков: {len(users_with_username)}\n\n"
            f"⚔️ Ждем на землях рассвета!"
        )

        await context.bot.send_message(
            chat_id=group_id, 
            text=final_text, 
            parse_mode="HTML"
        )

        await query.message.reply_text(f"✅ Массовый вызов роли <b>{role_name}</b> выполнен!", parse_mode="HTML")
        logger.info(f"📢 User {convener.id} вызвал всех {role_name}")

    except Exception as e:
        logger.error(f"Ошибка массового тега: {e}")
        await query.message.reply_text(f"❌ Ошибка: {e}")