import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, MessageHandler, filters, CallbackQueryHandler
from db import User, Session
import state

# Кастомный фильтр для проверки, является ли сообщение пересланным
async def is_forwarded(update, context):
    return bool(update.message.forward_from)

STATE_MIX_LIST = 1

async def tournament_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query: await query.answer()
    
    text = "🔀 **Генератор команд (Mix)**\n\n"
    text += "Режим для тренировочных игр и скримов.\n\n"
    
    keyboard = [
        [InlineKeyboardButton("🎲 Создать микс (Случайные)", callback_data="tourn_mix_start")],
        [InlineKeyboardButton("⬅ Назад в меню", callback_data=state.CD_BACK_TO_MENU)]
    ]
    
    if query:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def mix_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query: await query.answer()
    
    context.user_data["mix_participants"] = []
    
    text = (
        "🎲 **Режим сбора на Микс**\n\n"
        "1. Перешлите сообщения участников, которые будут играть.\n"
        "2. Когда все пересланы, нажмите кнопку '🎲 Перемешать и создать команды'.\n"
        "3. Бот случайным образом разделит их на 2 команды."
    )
    
    keyboard = [
        [InlineKeyboardButton("🎲 Перемешать и создать команды", callback_data="tourn_mix_finish")],
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel_mix")]
    ]
    
    if query:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    
    return STATE_MIX_LIST

async def mix_add_participant(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ Обрабатываем пересланные сообщения """
    if update.message.forward_from:
        user_id = update.message.forward_from.id
        user_name = update.message.forward_from.first_name
        
        # Избегаем дублей
        parts = context.user_data.get("mix_participants", [])
        if user_id not in [p['id'] for p in parts]:
            parts.append({'id': user_id, 'name': user_name})
            context.user_data["mix_participants"] = parts
            await update.message.reply_text(f"✅ Добавлен: {user_name}")
        else:
            await update.message.reply_text(f"⚠️ {user_name} уже в списке.")
    else:
        await update.message.reply_text("⚠️ Пожалуйста, перешлите именно сообщение пользователя.")
    
    return STATE_MIX_LIST

async def mix_finish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ Создаем команды """
    query = update.callback_query
    if query: await query.answer()
    
    participants = context.user_data.get("mix_participants", [])
    
    if len(participants) < 2:
        if query:
            await query.message.reply_text("❌ Слишком мало участников. Нужно минимум 2 человека для микса.")
        else:
            await update.message.reply_text("❌ Слишком мало участников.")
        return STATE_MIX_LIST

    # Перемешиваем
    random.shuffle(participants)
    
    # Делим пополам
    mid = len(participants) // 2
    team_a = participants[:mid]
    team_b = participants[mid:]

    text = "🎲 **РЕЗУЛЬТАТ МИКСА**\n\n"
    
    # Команда А
    text += "🔴 **Команда RED:**\n"
    for p in team_a:
        text += f"• {p['name']}\n"
    
    text += "\n"
    
    # Команда Б
    text += "🔵 **Команда BLUE:**\n"
    for p in team_b:
        text += f"• {p['name']}\n"
    
    text += "\n🏆 Удачной игры!"
    
    keyboard = [[InlineKeyboardButton("⬅ В меню", callback_data=state.CD_BACK_TO_MENU)]]
    
    # Отправляем результат
    if query:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    
    context.user_data["mix_participants"] = []
    return ConversationHandler.END

async def mix_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query: await query.answer()
    
    context.user_data["mix_participants"] = []
    # Возвращаемся в меню
    from start import show_main_menu
    await show_main_menu(update, context)
    return ConversationHandler.END

# Conversation Handler для режима микса
mix_conv_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(mix_start, pattern="^tourn_mix_start$")],
    states={
        STATE_MIX_LIST: [
            CallbackQueryHandler(mix_finish, pattern="^tourn_mix_finish$"),
            CallbackQueryHandler(mix_cancel, pattern="^cancel_mix$"),
            MessageHandler(is_forwarded, mix_add_participant)
        ],
    },
    fallbacks=[CallbackQueryHandler(mix_cancel, pattern="^tourn_cancel$")],
    per_message=False  # <--- ДОБАВИТЬ ЭТУ СТРОКУ
)