from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from db import is_user_admin, save_user, ADMIN_IDS
import state

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        await update.message.reply_text(
            "❌ Эта команда доступна только в личных сообщениях с ботом."
        )
        return
    
    user_id = update.effective_user.id
    user = update.effective_user

    # Если это админ, а его нет в БД (или данные устарели) — сохраняем/обновляем.
    # Это решает проблему "админов нет в списке", если они не писали в группу.
    if user_id in ADMIN_IDS:
        await save_user(
            user_id=user.id,
            first_name=user.first_name,
            last_name=user.last_name,
            username=user.username
        )
    
    await show_main_menu(update, context)

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id if update.effective_user else (update.callback_query.from_user.id if query else None)
    
    is_admin = await is_user_admin(user_id)
    
    text = ""
    keyboard = []

    if is_admin:
        # МЕНЮ АДМИНА
        text = (
            "🛠 **Панель Администратора**\n\n"
            "У вас есть полный доступ к управлению."
        )
        
        keyboard = [
            [
                InlineKeyboardButton("👥 Список игроков", callback_data=state.CD_MENU_PLAYERS),
                InlineKeyboardButton("📝 Регистрация ролей", callback_data=state.CD_MENU_REG)
            ],
            [
                InlineKeyboardButton("📢 Тегнуть игроков", callback_data=state.CD_MENU_TAG),
                InlineKeyboardButton("⚙️ Настройки", callback_data=state.CD_MENU_SETTINGS)
            ]
        ]
    else:
        # МЕНЮ ОБЫЧНОГО ИГРОКА
        text = (
            "👋 **Добро пожаловать!**\n\n"
            "Вы можете использовать бота для вызова игроков на матчи по ролям."
        )
        
        # Обычному игроку даем только доступ к тегам
        keyboard = [
            [
                InlineKeyboardButton("📢 Тегнуть игроков", callback_data=state.CD_MENU_TAG)
            ]
        ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        if query:
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    except Exception as e:
        pass # Игнорируем ошибки редактирования, если ничего не изменилось

async def back_to_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await show_main_menu(update, context)