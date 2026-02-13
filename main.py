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
# ИМПОРТ: Добавлен who_is_handler
from profile import profile_command, who_is_handler
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
from events import (
    crm_menu, crm_create_event_start, handle_crm_input, 
    join_menu, handle_event_action,
    evt_select_day, evt_select_hour, evt_select_minute, 
    evt_back_day, evt_back_hour, evt_cancel,
    evt_view_participants, evt_delete_event, back_to_crm_menu
)
from scheduler import start_scheduler

# ИМПОРТ ДЛЯ ТУРНИРА / МИКСА
from tournament import tournament_menu, mix_conv_handler

load_dotenv()

# --- ДИСПЕТЧЕР ТЕКСТОВЫХ СООБЩЕНИЙ (ЛС) ---
async def dispatch_private_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Перенаправляет текстовые сообщения в зависимости от состояния пользователя"""
    u_state = context.user_data
    
    if "crm_state" in u_state and u_state["crm_state"]:
        await handle_crm_input(update, context)
    elif "settings_state" in u_state and u_state["settings_state"]:
        await handle_global_delete_input(update, context)
    elif "reg_state" in u_state and u_state["reg_state"]:
        await handle_registration_input(update, context)

# --- ГРУППОВЫЕ СОБЫТИЯ ---

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
    """
    Сохраняет данные пользователя и запоминает ID группы.
    Запускается для ВСЕХ сообщений в группе.
    """
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
    
    context.bot_data["last_admin_group_id"] = chat.id


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    if context.error is None: return
    if "NoneType" in str(context.error) and "new_chat_member" in str(context.error): return
    print(f"❌ Ошибка: {context.error}")

# --- MAIN ---

def main():
    print("🤖 Бот запущен!")
    
    bot_token = os.getenv("BOT_TOKEN")
    if not bot_token:
        raise ValueError("❌ Токен бота не найден!")

    application = Application.builder().token(bot_token).build()
    application.add_error_handler(error_handler)
    
    # ==========================================
    # 1. Системные хендлеры
    # ==========================================
    application.add_handler(ChatMemberHandler(on_chat_member_update))

    # ==========================================
    # 2. Команды (Группа 0 - Высокий приоритет)
    # ==========================================
    # Команды добавляем ПЕРВЫМИ в группу 0.
    # Они перехватят /me, /start и т.д. раньше, чем универсальный сборщик статистики.
    
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("me", profile_command)) 
    application.add_handler(CommandHandler("join", join_menu))

    # ==========================================
    # 3. Групповые хендлеры (Распределение по группам)
    # ==========================================
    
    # ГРУППА 1: Реакция на "Кто"
    # Если сообщение подходит под условие (ответ + текст "кто"), выполняется здесь.
    application.add_handler(
        MessageHandler(filters.ChatType.GROUPS & filters.TEXT & filters.REPLY, who_is_handler), 
        group=1
    )

    # ГРУППА 2: Сбор статистики (Фоновый)
    # Выполняется ПОСЛЕ команд (группа 0) и спец-реакций (группа 1).
    # Сохраняет юзера в базу и запоминает ID группы для тегов.
    # Если сообщение было командой (/me), группа 0 его уже обработала, 
    # но PTB позволяет запустить эту функцию параллельно (т.к. группа другая).
    application.add_handler(
        MessageHandler(filters.ChatType.GROUPS, handle_group_message), 
        group=2
    )

    # ==========================================
    # 4. Главное меню (Dashboard Callbacks)
    # ==========================================
    
    application.add_handler(CallbackQueryHandler(show_all_players, pattern=f"^{state.CD_MENU_PLAYERS}"))
    application.add_handler(CallbackQueryHandler(reg_menu, pattern=f"^{state.CD_MENU_REG}$"))
    application.add_handler(CallbackQueryHandler(tag_menu, pattern=f"^{state.CD_MENU_TAG}$"))
    application.add_handler(CallbackQueryHandler(crm_menu, pattern=f"^{state.CD_MENU_CRM}$"))
    application.add_handler(CallbackQueryHandler(tournament_menu, pattern=f"^{state.CD_MENU_TOURNAMENT}$"))
    application.add_handler(CallbackQueryHandler(settings_menu, pattern=f"^{state.CD_MENU_SETTINGS}$"))
    application.add_handler(CallbackQueryHandler(back_to_menu_handler, pattern=f"^{state.CD_BACK_TO_MENU}$"))
    
    # ==========================================
    # 5. Регистрация (Registration Callbacks)
    # ==========================================
    
    application.add_handler(CallbackQueryHandler(view_role_handler, pattern=f"^{state.CD_VIEW_ROLE}:"))
    
    application.add_handler(CallbackQueryHandler(add_to_role_start, pattern=f"^{state.CD_ADD_TO}:"))
    application.add_handler(CallbackQueryHandler(show_users_by_letter, pattern=r"^reg_letter:"))
    application.add_handler(CallbackQueryHandler(select_user_for_action, pattern=r"^reg_select_user:"))
    
    application.add_handler(CallbackQueryHandler(del_from_role_start, pattern=f"^{state.CD_DEL_FROM}:"))
    application.add_handler(CallbackQueryHandler(delete_user_handler, pattern=r"^del_user:"))
    application.add_handler(CallbackQueryHandler(del_page_handler, pattern=r"^del_page:"))
    
    application.add_handler(CallbackQueryHandler(back_to_roles_handler, pattern=f"^{state.CD_BACK_TO_ROLES}$"))
    
    # ==========================================
    # 6. Теги (Tag Callbacks)
    # ==========================================
    
    application.add_handler(CallbackQueryHandler(teg_view_role_handler, pattern=f"^{state.CD_TEG_ROLE}:"))
    application.add_handler(CallbackQueryHandler(teg_single_user_handler, pattern=f"^{state.CD_TEG_USER}:"))
    application.add_handler(CallbackQueryHandler(teg_all_users_handler, pattern=f"^{state.CD_TEG_ALL}:"))
    application.add_handler(CallbackQueryHandler(teg_back_handler, pattern=f"^{state.CD_TEG_BACK}$"))
    
    # ==========================================
    # 7. CRM (Игры и Планирование)
    # ==========================================
    
    application.add_handler(CallbackQueryHandler(crm_create_event_start, pattern="^crm_create_event$"))
    
    application.add_handler(CallbackQueryHandler(evt_select_day, pattern=r"^evt_day:"))
    application.add_handler(CallbackQueryHandler(evt_select_hour, pattern=r"^evt_hour:"))
    application.add_handler(CallbackQueryHandler(evt_select_minute, pattern=r"^evt_min:"))
    application.add_handler(CallbackQueryHandler(evt_back_day, pattern="^evt_back_day$"))
    application.add_handler(CallbackQueryHandler(evt_back_hour, pattern="^evt_back_hour$"))
    application.add_handler(CallbackQueryHandler(evt_cancel, pattern="^cancel_event$"))
    
    application.add_handler(CallbackQueryHandler(evt_view_participants, pattern=r"^evt_view:"))
    application.add_handler(CallbackQueryHandler(evt_delete_event, pattern=r"^evt_del:"))
    application.add_handler(CallbackQueryHandler(back_to_crm_menu, pattern="^back_to_crm_menu$"))
    
    application.add_handler(CallbackQueryHandler(handle_event_action, pattern=r"^event_(join|leave):"))
    
    # ==========================================
    # 8. Микс (Турнир)
    # ==========================================
    
    application.add_handler(mix_conv_handler)
    
    # ==========================================
    # 9. Настройки (Settings Callbacks)
    # ==========================================
    
    application.add_handler(CallbackQueryHandler(settings_del_user_start, pattern="^settings_del_user$"))
    application.add_handler(CallbackQueryHandler(settings_info, pattern="^settings_info$"))
    
    # ==========================================
    # 10. Текстовый ввод (ЛС)
    # ==========================================
    
    application.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND,
            dispatch_private_text
        )
    )
    
    # ==========================================
    # ЗАПУСК
    # ==========================================
    
    start_scheduler(application)
    application.run_polling()

if __name__ == "__main__":
    main()