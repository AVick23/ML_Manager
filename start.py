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

    # 1. Всегда сохраняем/обновляем пользователя в БД при старте.
    # Это нужно, чтобы бот работал корректно для всех, даже если они только пришли в ЛС.
    await save_user(
        user_id=user.id,
        first_name=user.first_name,
        last_name=user.last_name,
        username=user.username
    )
    
    await show_main_menu(update, context)

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    
    # Определяем ID пользователя (если это callback или новое сообщение)
    if update.effective_user:
        user_id = update.effective_user.id
    elif query:
        user_id = query.from_user.id
    else:
        return
    
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
                InlineKeyboardButton("📅 Игры (CRM)", callback_data=state.CD_MENU_CRM),
                InlineKeyboardButton("🎲 Микс (Рандом)", callback_data=state.CD_MENU_TOURNAMENT)
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
        # Игнорируем ошибку, если текст не изменился
        pass

async def back_to_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    await show_main_menu(update, context)