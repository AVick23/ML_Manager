from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from db import get_all_users, is_user_admin, ADMIN_IDS, Session, ROLE_TO_MODEL, ROLE_NAMES
import state
import asyncio

ITEMS_PER_PAGE = 10

def escape_html(text):
    """Экранирует спецсимволы для HTML"""
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return ''.join(f'\\{char}' if char in escape_chars else char for char in str(text))

async def show_all_players(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    
    if not await is_user_admin(user_id):
        await query.edit_message_text("❌ У вас нет прав для просмотра этого раздела.")
        return

    users = await get_all_users()
    
    if not users:
        await query.edit_message_text("В базе данных пока нет пользователей.")
        return

    # Определяем текущую страницу
    page = 1
    if query.data and ":" in query.data:
        try:
            page = int(query.data.split(":")[1])
        except (ValueError, IndexError):
            page = 1

    total_users = len(users)
    admin_count = sum(1 for user in users if user.user_id in ADMIN_IDS)
    total_pages = (total_users + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
    
    start_index = (page - 1) * ITEMS_PER_PAGE
    end_index = start_index + ITEMS_PER_PAGE
    page_users = users[start_index:end_index]

    message = (
        f"👥 <b>Список всех пользователей</b> (всего: {total_users}, админов: {admin_count})\n"
        f"📄 Страница {page}/{total_pages}\n\n"
    )
    
    # --- ЛОГИКА ПРОВЕРКИ РОЛЕЙ ---
    def get_roles_for_page_sync():
        session = Session()
        try:
            user_roles = {} # {user_id: [RoleName1, RoleName2]}
            
            for role_key, Model in ROLE_TO_MODEL.items():
                # Ищем записи в таблице роли, где user_id есть в списке текущей страницы
                role_entries = session.query(Model).filter(Model.user_id.in_([u.user_id for u in page_users])).all()
                
                for entry in role_entries:
                    uid = entry.user_id
                    if uid not in user_roles:
                        user_roles[uid] = []
                    
                    role_name = ROLE_NAMES[role_key]
                    if role_name not in user_roles[uid]:
                        user_roles[uid].append(role_name)
            
            return user_roles
        finally:
            session.close()

    # Запускаем в отдельном потоке
    user_roles_map = await asyncio.to_thread(get_roles_for_page_sync)

    # Формируем сообщение
    for user in page_users:
        full_name = f"{user.first_name} {user.last_name or ''}".strip() or "Не указано имя"
        username = f"@{user.username}" if user.username else "нет username"
        admin_status = "✅ Админ" if user.user_id in ADMIN_IDS else "❌ Игрок"
        
        # Проверяем роли
        roles = user_roles_map.get(user.user_id, [])
        if roles:
            # Объединяем роли в строку через запятую
            role_display = ", ".join([escape_html(r) for r in roles])
            role_text = f"🟢 [{role_display}]"
        else:
            role_text = "⚪ Без роли"
        
        message += f"• <code>{user.user_id}</code> | {full_name} ({username})<br>"
        message += f"  {admin_status} | {role_text}<br>\n"
    
    # Клавиатура навигации
    keyboard = []
    nav_buttons = []
    
    if page > 1:
        nav_buttons.append(InlineKeyboardButton("⬅️", callback_data=f"{state.CD_MENU_PLAYERS}:{page-1}"))
    
    nav_buttons.append(InlineKeyboardButton(f"📄 {page}/{total_pages}", callback_data="ignore"))
    
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton("➡️", callback_data=f"{state.CD_MENU_PLAYERS}:{page+1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
        
    keyboard.append([InlineKeyboardButton("⬅ Назад в меню", callback_data=state.CD_BACK_TO_MENU)])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='HTML')
    except Exception as e:
        # Если текст слишком длинный для редактирования, отправляем новым сообщением (опционально)
        pass