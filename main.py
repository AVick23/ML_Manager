import os
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ChatMemberHandler,
    CallbackQueryHandler,
    ContextTypes
)

# Импорты из наших модулей
import db
import state
from db import ADMIN_IDS

from start import start_command, back_to_menu_handler
from lists_of_players import show_all_players
from settings import (
    settings_menu, settings_del_user_start, 
    settings_info, handle_global_delete_input
)
from profile import profile_command
from registration import (
    reg_menu, view_role_handler, back_to_roles_handler, 
    add_to_role_start, del_from_role_start, handle_registration_input,
    show_users_by_letter, select_user_for_action,
    delete_user_handler, del_page_handler
)
from tag_players import (
    tag_menu, teg_view_role_handler, teg_single_user_handler, 
    teg_all_users_handler, teg_back_handler
)

load_dotenv()

# --- Групповые события ---

async def on_chat_member_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.chat_member: return
    result = update.chat_member
    new_member = result.new_chat_member

    if new_member.user.id == context.bot.id:
        if new_member.status == "member":
            await update.effective_chat.send_message("✅ Привет! Я запишу всех участников при их первом сообщении.")
        return

    if new_member.status not in ["left", "kicked"]:
        user = new_member.user
        await db.save_user(
            user_id=user.id,
            first_name=user.first_name,
            last_name=user.last_name,
            username=user.username
        )
        
async def handle_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type not in ["group", "supergroup"]:
        return

    user = update.effective_user
    chat = update.effective_chat

    await db.save_user(
        user_id=user.id,
        first_name=user.first_name,
        last_name=user.last_name,
        username=user.username
    )
    
    if user.id in ADMIN_IDS:
        context.bot_data["last_admin_group_id"] = chat.id

# --- Обработка ошибок ---

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    if context.error is None: return
    if "NoneType" in str(context.error) and "new_chat_member" in str(context.error): return
    print(f"❌ Ошибка: {context.error}")

# --- Main ---

def main():
    print("🤖 Бот запущен!")
    
    bot_token = os.getenv("BOT_TOKEN")
    if not bot_token:
        raise ValueError("❌ Токен бота не найден!")

    application = Application.builder().token(bot_token).build()
    application.add_error_handler(error_handler)
    
    # 1. Системные и групповые хендлеры
    application.add_handler(ChatMemberHandler(on_chat_member_update))
    application.add_handler(MessageHandler(filters.ChatType.GROUPS, handle_group_message))
    
    # 2. Команды
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("me", profile_command))
    
    # 3. Главное меню (Dashboard Callbacks)
    application.add_handler(CallbackQueryHandler(show_all_players, pattern=f"^{state.CD_MENU_PLAYERS}"))
    application.add_handler(CallbackQueryHandler(reg_menu, pattern=f"^{state.CD_MENU_REG}$"))
    application.add_handler(CallbackQueryHandler(tag_menu, pattern=f"^{state.CD_MENU_TAG}$"))
    application.add_handler(CallbackQueryHandler(settings_menu, pattern=f"^{state.CD_MENU_SETTINGS}$"))
    application.add_handler(CallbackQueryHandler(back_to_menu_handler, pattern=f"^{state.CD_BACK_TO_MENU}$"))
    
    # 4. Регистрация (Registration Callbacks)
    application.add_handler(CallbackQueryHandler(view_role_handler, pattern=f"^{state.CD_VIEW_ROLE}:"))
    
    # Добавление
    application.add_handler(CallbackQueryHandler(add_to_role_start, pattern=f"^{state.CD_ADD_TO}:"))
    application.add_handler(CallbackQueryHandler(show_users_by_letter, pattern=r"^reg_letter:"))
    application.add_handler(CallbackQueryHandler(select_user_for_action, pattern=r"^reg_select_user:"))
    
    # Удаление
    application.add_handler(CallbackQueryHandler(del_from_role_start, pattern=f"^{state.CD_DEL_FROM}:"))
    application.add_handler(CallbackQueryHandler(delete_user_handler, pattern=r"^del_user:"))
    application.add_handler(CallbackQueryHandler(del_page_handler, pattern=r"^del_page:"))
    
    application.add_handler(CallbackQueryHandler(back_to_roles_handler, pattern=f"^{state.CD_BACK_TO_ROLES}$"))
    
    # 5. Теги (Tag Callbacks)
    application.add_handler(CallbackQueryHandler(teg_view_role_handler, pattern=f"^{state.CD_TEG_ROLE}:"))
    application.add_handler(CallbackQueryHandler(teg_single_user_handler, pattern=f"^{state.CD_TEG_USER}:"))
    application.add_handler(CallbackQueryHandler(teg_all_users_handler, pattern=f"^{state.CD_TEG_ALL}:"))
    application.add_handler(CallbackQueryHandler(teg_back_handler, pattern=f"^{state.CD_TEG_BACK}$"))
    
    # 6. Настройки (Settings Callbacks)
    application.add_handler(CallbackQueryHandler(settings_del_user_start, pattern="^settings_del_user$"))
    application.add_handler(CallbackQueryHandler(settings_info, pattern="^settings_info$"))
    
    # 7. Текстовый ввод
    # Регистрация (ввод ID)
    application.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND,
            handle_registration_input
        )
    )
    # Настройки (ввод никнейма для удаления)
    application.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND,
            handle_global_delete_input
        )
    )
    
    application.run_polling()

if __name__ == "__main__":
    main()