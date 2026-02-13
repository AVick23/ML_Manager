from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from sqlalchemy import or_
from db import (
    User, get_all_users, get_role_users, 
    add_user_to_role, remove_user_from_role, is_user_admin, 
    ROLE_NAMES, Session
)
import state

ITEMS_PER_PAGE = 10

# --- Конфигурация алфавитных групп (Только для добавления) ---
LETTER_GROUPS = {
    "A-C": ['a', 'b', 'c'],
    "D-F": ['d', 'e', 'f'],
    "G-I": ['g', 'h', 'i'],
    "J-L": ['j', 'k', 'l'],
    "M-O": ['m', 'n', 'o'],
    "P-R": ['p', 'q', 'r'],
    "S-U": ['s', 't', 'u'],
    "V-X": ['v', 'w', 'x'],
    "Y-Z": ['y', 'z'],
    "0-9": ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9'],
    "😎 Другое": [] 
}

# ==========================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==========================================

async def _render_delete_list(update: Update, context: ContextTypes.DEFAULT_TYPE, role_key: str, page: int):
    """
    Функция отрисовки списка для удаления. 
    """
    query = update.callback_query
    
    users = await get_role_users(role_key)
    
    if not users:
        # Если список пуст
        kb = [[InlineKeyboardButton("⬅ Назад", callback_data=f"{state.CD_VIEW_ROLE}:{role_key}:1")]]
        await query.edit_message_text("В этой категории пока нет игроков для удаления.", reply_markup=InlineKeyboardMarkup(kb))
        return

    total_pages = (len(users) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
    start_index = (page - 1) * ITEMS_PER_PAGE
    end_index = start_index + ITEMS_PER_PAGE
    page_users = users[start_index:end_index]

    # ИСПРАВЛЕНО: Убраны звездочки (Markdown) во избежание ошибок парсинга
    text = f"🗑 Удаление из {ROLE_NAMES[role_key]} (всего: {len(users)})\nСтраница {page}/{total_pages}\n\n"
    text += "Нажмите на игрока, чтобы удалить его из этой роли:\n\n"

    keyboard = []
    for u in page_users:
        # Формируем имя. Если есть username - добавляем, иначе просто имя
        name = f"{u.first_name} (@{u.username})" if u.username else u.first_name
        callback = f"del_user:{u.user_id}:{role_key}:{page}"
        keyboard.append([InlineKeyboardButton(f"❌ {name}", callback_data=callback)])

    # Навигация
    nav_buttons = []
    if page > 1: 
        nav_buttons.append(InlineKeyboardButton("⬅️", callback_data=f"del_page:{role_key}:{page-1}"))
    
    nav_buttons.append(InlineKeyboardButton(f"📄 {page}/{total_pages}", callback_data="ignore"))
    
    if page < total_pages: 
        nav_buttons.append(InlineKeyboardButton("➡️", callback_data=f"del_page:{role_key}:{page+1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)

    keyboard.append([InlineKeyboardButton("⬅ Назад", callback_data=f"{state.CD_VIEW_ROLE}:{role_key}:1")])

    # ИСПРАВЛЕНО: Убран parse_mode='Markdown'
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

# ==========================================
# ОСНОВНЫЕ ХЕНДЛЕРЫ
# ==========================================

async def reg_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not await is_user_admin(query.from_user.id):
        await query.edit_message_text("❌ Эта функция доступна только администраторам.")
        return

    buttons = [
        InlineKeyboardButton(name, callback_data=f"{state.CD_VIEW_ROLE}:{key}:1")
        for key, name in ROLE_NAMES.items()
    ]
    keyboard = [buttons[i:i+2] for i in range(0, len(buttons), 2)]
    keyboard.append([InlineKeyboardButton("⬅ Назад в меню", callback_data=state.CD_BACK_TO_MENU)])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("Выберите категорию для управления:", reply_markup=reply_markup)

# --- ПРОСМОТР РОЛИ ---

async def view_role_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    role_key = parts[1]
    page = int(parts[2]) if len(parts) > 2 else 1

    if role_key not in ROLE_NAMES:
        await query.edit_message_text("❌ Ошибка роли.")
        return

    users = await get_role_users(role_key)
    
    if not users:
        # ИСПРАВЛЕНО: Убраны звездочки
        text = f"👥 {ROLE_NAMES[role_key]}\n\nПока никто не зарегистрирован."
        keyboard = [
            [
                InlineKeyboardButton("➕ Добавить", callback_data=f"{state.CD_ADD_TO}:{role_key}"),
                InlineKeyboardButton("🗑 Удалить", callback_data=f"{state.CD_DEL_FROM}:{role_key}")
            ],
            [InlineKeyboardButton("⬅ Назад", callback_data=state.CD_BACK_TO_ROLES)]
        ]
        # ИСПРАВЛЕНО: Убран parse_mode
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    total_pages = (len(users) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
    start_index = (page - 1) * ITEMS_PER_PAGE
    end_index = start_index + ITEMS_PER_PAGE
    page_users = users[start_index:end_index]

    # ИСПРАВЛЕНО: Убраны звездочки
    text = f"👥 {ROLE_NAMES[role_key]} (всего: {len(users)})\nСтраница {page}/{total_pages}\n\n"
    
    for u in page_users:
        name = f"{u.first_name} {u.last_name or ''}".strip() or "Не указано имя"
        tag = f"@{u.username}" if u.username else "нет username"
        id_ml = u.id_ml or "не указан"
        # ИСПРАВЛЕНО: Убраны обратные кавычки вокруг ID (они вызывали ошибку, если в имени были спецсимволы)
        text += f"• {name} ({tag}) — ID: {id_ml}\n"

    keyboard = []
    keyboard.append([
        InlineKeyboardButton("➕ Добавить", callback_data=f"{state.CD_ADD_TO}:{role_key}"),
        InlineKeyboardButton("🗑 Удалить", callback_data=f"{state.CD_DEL_FROM}:{role_key}")
    ])
    
    nav_buttons = []
    if page > 1: nav_buttons.append(InlineKeyboardButton("⬅️", callback_data=f"{state.CD_VIEW_ROLE}:{role_key}:{page-1}"))
    nav_buttons.append(InlineKeyboardButton(f"📄 {page}/{total_pages}", callback_data="ignore"))
    if page < total_pages: nav_buttons.append(InlineKeyboardButton("➡️", callback_data=f"{state.CD_VIEW_ROLE}:{role_key}:{page+1}"))
    if nav_buttons: keyboard.append(nav_buttons)
    keyboard.append([InlineKeyboardButton("⬅ Назад", callback_data=state.CD_BACK_TO_ROLES)])
    
    # ИСПРАВЛЕНО: Убран parse_mode
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def back_to_roles_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await reg_menu(update, context)

# ==========================================
# ЛОГИКА ДОБАВЛЕНИЯ (Поиск по базе)
# ==========================================

async def add_to_role_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    role_key = query.data.split(":", 1)[1]
    context.user_data.update({
        "reg_action": "add",
        "reg_role": role_key
    })

    keyboard = []
    row = []
    for group_name, letters in LETTER_GROUPS.items():
        btn = InlineKeyboardButton(group_name, callback_data=f"reg_letter:{group_name}")
        row.append(btn)
        if len(row) == 4:
            keyboard.append(row)
            row = []
    if row: keyboard.append(row)

    keyboard.append([InlineKeyboardButton("⬅ Отмена", callback_data=state.CD_VIEW_ROLE + ":" + role_key + ":1")])

    # ИСПРАВЛЕНО: Убраны звездочки и parse_mode
    await query.edit_message_text(
        f"➕ Добавление в {ROLE_NAMES[role_key]}\n\n"
        f"Выберите первую букву имени или ника игрока:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def show_users_by_letter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    group_name = query.data.split(":")[1]
    letters = LETTER_GROUPS.get(group_name, [])

    def search_users_sync():
        session = Session()
        try:
            conditions = []
            for l in letters:
                conditions.append(User.username.ilike(f'{l}%'))
                conditions.append(User.first_name.ilike(f'{l}%'))
            
            if group_name == "😎 Другое":
                rus_letters = ['а','б','в','г','д','е','ё','ж','з','и','й','к','л','м','н','о','п','р','с','т','у','ф','х','ц','ч','ш','щ','ъ','ы','ь','э','ю','я']
                conditions = [User.username.ilike(f'{l}%') for l in rus_letters] + [User.first_name.ilike(f'{l}%') for l in rus_letters]

            if not conditions: return []
            return session.query(User).filter(or_(*conditions)).all()
        finally:
            session.close()

    import asyncio
    users = await asyncio.to_thread(search_users_sync)

    if not users:
        role_key = context.user_data.get("reg_role")
        kb = [[InlineKeyboardButton("⬅ Назад", callback_data=f"{state.CD_ADD_TO}:{role_key}")]]
        await query.edit_message_text("Игроков с такими буквами не найдено.", reply_markup=InlineKeyboardMarkup(kb))
        return

    page_users = users[:ITEMS_PER_PAGE] 

    # ИСПРАВЛЕНО: Убраны звездочки
    text = f"🔍 Буква: {group_name} (найдено: {len(users)})\n\nВыберите игрока:\n"
    keyboard = []

    for u in page_users:
        name = f"{u.first_name} (@{u.username})" if u.username else u.first_name
        callback = f"reg_select_user:{u.user_id}"
        keyboard.append([InlineKeyboardButton(name, callback_data=callback)])

    role_key = context.user_data.get('reg_role')
    keyboard.append([InlineKeyboardButton("⬅ Выбрать другую букву", callback_data=f"{state.CD_ADD_TO}:{role_key}")])

    # ИСПРАВЛЕНО: Убран parse_mode
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def select_user_for_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = int(query.data.split(":")[1])
    role_key = context.user_data.get('reg_role')
    
    session = Session()
    try:
        user = session.query(User).filter_by(user_id=user_id).first()
        if not user:
            await query.message.reply_text("Ошибка: пользователь не найден.")
            return
    finally:
        session.close()

    context.user_data['candidate_user'] = user
    context.user_data['reg_state'] = state.REG_AWAITING_IDML
    
    name = f"{user.first_name} (@{user.username})" if user.username else user.first_name
    
    # ИСПРАВЛЕНО: Убраны звездочки и parse_mode
    await query.edit_message_text(
        f"✅ Выбран игрок: {name}\n\n"
        f"🔢 Введите его игровой ID (ID ML):"
    )

# ==========================================
# ЛОГИКА УДАЛЕНИЯ
# ==========================================

async def del_from_role_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ Запуск режима удаления """
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    role_key = parts[1]
    page = int(parts[2]) if len(parts) > 2 else 1

    await _render_delete_list(update, context, role_key, page)

async def delete_user_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ Обработка нажатия на кнопку удаления конкретного юзера """
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    user_id = int(parts[1])
    role_key = parts[2]
    page = int(parts[3]) if len(parts) > 3 else 1

    try:
        await remove_user_from_role(role_key, user_id)
        await _render_delete_list(update, context, role_key, page)
        
    except Exception as e:
        await query.message.reply_text(f"❌ Ошибка при удалении: {e}")

async def del_page_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ Навигация по страницам удаления """
    query = update.callback_query
    await query.answer()
    
    parts = query.data.split(":")
    role_key = parts[1]
    page = int(parts[2])
    
    await _render_delete_list(update, context, role_key, page)

# ==========================================
# ОБРАБОТКА ТЕКСТА (Ввод ID)
# ==========================================

async def handle_registration_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not await is_user_admin(user_id):
        await update.message.reply_text("❌ Нет прав.")
        return

    state_curr = context.user_data.get("reg_state")
    
    if state_curr != state.REG_AWAITING_IDML:
        return

    role_key = context.user_data.get("reg_role")
    candidate = context.user_data.get("candidate_user")
    
    if not role_key or not candidate:
        await update.message.reply_text("❌ Ошибка сессии. Начните заново через меню.")
        context.user_data.clear()
        return

    text = update.message.text.strip()

    try:
        id_ml = int(text)
        if id_ml <= 0: raise ValueError
    except:
        return await update.message.reply_text("❌ ID должен быть положительным числом (только цифры).")

    try:
        await add_user_to_role(role_key, candidate, id_ml)
        await update.message.reply_text(
            f"✅ Пользователь @{candidate.username} добавлен в {ROLE_NAMES[role_key]} с ID {id_ml}!"
        )
    except ValueError as e:
        await update.message.reply_text(f"❌ {e}")
    except Exception as e:
        await update.message.reply_text("❌ Ошибка БД.")
        print(f"Error: {e}")

    context.user_data.clear()