from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from db import get_all_users, is_user_admin, ADMIN_IDS
import state

ITEMS_PER_PAGE = 10

async def show_all_players(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    
    # Проверка прав
    if not await is_user_admin(user_id):
        await query.edit_message_text("❌ У вас нет прав для просмотра этого раздела.")
        return

    users = await get_all_users()
    
    if not users:
        await query.edit_message_text("В базе данных пока нет пользователей.")
        return

    # Определяем текущую страницу из callback_data (формат: menu_players:2)
    page = 1
    if query.data and ":" in query.data:
        try:
            page = int(query.data.split(":")[1])
        except (ValueError, IndexError):
            page = 1

    total_users = len(users)
    admin_count = sum(1 for user in users if user.user_id in ADMIN_IDS)
    total_pages = (total_users + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
    
    # Вырезаем список для текущей страницы
    start_index = (page - 1) * ITEMS_PER_PAGE
    end_index = start_index + ITEMS_PER_PAGE
    page_users = users[start_index:end_index]

    message = (
        f"👥 **Список всех пользователей** (всего: {total_users}, админов: {admin_count})\n"
        f"📄 Страница {page}/{total_pages}\n\n"
    )
    
    for user in page_users:
        full_name = f"{user.first_name} {user.last_name or ''}".strip() or "Не указано имя"
        username = f"@{user.username}" if user.username else "нет username"
        admin_status = "✅ Админ" if user.user_id in ADMIN_IDS else "❌ Игрок"
        message += f"• `{user.user_id}` | {full_name} ({username}) — {admin_status}\n"
    
    # Формируем клавиатуру
    keyboard = []
    nav_buttons = []
    
    # Кнопка "Назад"
    if page > 1:
        nav_buttons.append(InlineKeyboardButton("⬅️", callback_data=f"{state.CD_MENU_PLAYERS}:{page-1}"))
    
    # Кнопка с номером страницы (информационная)
    nav_buttons.append(InlineKeyboardButton(f"📄 {page}/{total_pages}", callback_data="ignore"))
    
    # Кнопка "Вперед"
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton("➡️", callback_data=f"{state.CD_MENU_PLAYERS}:{page+1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
        
    # Кнопка возврата в главное меню
    keyboard.append([InlineKeyboardButton("⬅ Назад в меню", callback_data=state.CD_BACK_TO_MENU)])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')
    except Exception as e:
        # Игнорируем ошибку, если текст не изменился
        pass