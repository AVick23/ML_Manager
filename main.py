"""
Главный файл бота.
Содержит инициализацию, регистрацию хендлеров и запуск бота.
"""
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
from config import BOT_TOKEN, ADMIN_IDS, GROUP_ID, logger, log_config
from db import save_user

from start import start_command, back_to_menu_handler
from lists_of_players import show_all_players
from settings import (
    settings_menu, settings_del_user_start,
    settings_info, handle_global_delete_input
)
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
# Импорты из папки events
from events.handlers import (
    events_menu, show_event_detail, handle_event_action,
    create_event_start, handle_text_input as handle_crm_input,
    select_day, select_hour, select_minute,
    back_to_day, back_to_hour, cancel_creation,
    delete_event, back_to_events_list,
    edit_event_start, edit_title_start, edit_time_start, 
    cancel_edit, receive_edited_title,
    check_and_notify_events
)
# Импорты из папки announcement
from announcement.handlers import (
    announce_start, receive_announce_text,
    announce_confirm, announce_edit, announce_cancel
)
from scheduler import start_scheduler
from tournament import tournament_menu, mix_conv_handler


# ==========================================
# ДИСПЕТЧЕР ТЕКСТОВЫХ СООБЩЕНИЙ (ЛС)
# ==========================================

async def dispatch_private_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Перенаправляет текстовые сообщения в зависимости от состояния пользователя"""
    u_state = context.user_data
    
    # Проверяем состояния в порядке приоритета
    if u_state.get("announce_state") == "awaiting_announce_text":
        await receive_announce_text(update, context)
    elif "state" in u_state and u_state["state"] == "EDITING_TITLE":
        await receive_edited_title(update, context)
    elif "crm_state" in u_state and u_state["crm_state"]:
        await handle_crm_input(update, context)
    elif "settings_state" in u_state and u_state["settings_state"]:
        await handle_global_delete_input(update, context)
    elif "reg_state" in u_state and u_state["reg_state"]:
        await handle_registration_input(update, context)


# ==========================================
# ГРУППОВЫЕ СОБЫТИЯ
# ==========================================

async def on_chat_member_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка изменения состава чата"""
    if not update.chat_member:
        return
    
    result = update.chat_member
    new_member = result.new_chat_member

    if new_member.user.id == context.bot.id:
        if new_member.status == "member":
            chat_id = update.effective_chat.id
            logger.info(f"🤖 Бот добавлен в группу: {chat_id}")
            await update.effective_chat.send_message(
                "✅ Привет! Я запомню эту группу для уведомлений о играх."
            )
            
            if not GROUP_ID:
                context.bot_data["last_admin_group_id"] = chat_id
        return

    if new_member.status not in ["left", "kicked"]:
        user = new_member.user
        await save_user(
            user_id=user.id,
            first_name=user.first_name,
            last_name=user.last_name,
            username=user.username
        )


async def handle_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сохраняет данные пользователя и запоминает ID группы"""
    if update.effective_chat.type not in ["group", "supergroup"]:
        return

    user = update.effective_user
    chat = update.effective_chat

    await save_user(
        user_id=user.id,
        first_name=user.first_name,
        last_name=user.last_name,
        username=user.username
    )
    
    if not GROUP_ID:
        context.bot_data["last_admin_group_id"] = chat.id


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Глобальный обработчик ошибок"""
    if context.error is None:
        return
    
    if "NoneType" in str(context.error) and "new_chat_member" in str(context.error):
        return
    
    logger.error(f"❌ Ошибка: {context.error}", exc_info=True)


# ==========================================
# MAIN
# ==========================================

def main():
    """Точка входа в приложение"""
    logger.info("🤖 Запуск ML Manager Bot...")
    
    log_config()
    
    if not BOT_TOKEN:
        raise ValueError("❌ BOT_TOKEN не найден!")

    application = Application.builder().token(BOT_TOKEN).build()
    application.add_error_handler(error_handler)
    
    # ==========================================
    # 1. Системные хендлеры
    # ==========================================
    application.add_handler(ChatMemberHandler(on_chat_member_update))

    # ==========================================
    # 2. Команды
    # ==========================================
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("me", profile_command))

    # ==========================================
    # 3. Групповые хендлеры
    # ==========================================
    
    application.add_handler(
        MessageHandler(filters.ChatType.GROUPS & filters.TEXT & filters.REPLY, who_is_handler),
        group=1
    )

    application.add_handler(
        MessageHandler(filters.ChatType.GROUPS, handle_group_message),
        group=2
    )

    # ==========================================
    # 4. Главное меню
    # ==========================================
    
    application.add_handler(CallbackQueryHandler(show_all_players, pattern=f"^{state.CD_MENU_PLAYERS}"))
    application.add_handler(CallbackQueryHandler(reg_menu, pattern=f"^{state.CD_MENU_REG}$"))
    application.add_handler(CallbackQueryHandler(tag_menu, pattern=f"^{state.CD_MENU_TAG}$"))
    application.add_handler(CallbackQueryHandler(events_menu, pattern=f"^{state.CD_MENU_CRM}$"))
    application.add_handler(CallbackQueryHandler(tournament_menu, pattern=f"^{state.CD_MENU_TOURNAMENT}$"))
    application.add_handler(CallbackQueryHandler(settings_menu, pattern=f"^{state.CD_MENU_SETTINGS}$"))
    application.add_handler(CallbackQueryHandler(back_to_menu_handler, pattern=f"^{state.CD_BACK_TO_MENU}$"))
    
    # ==========================================
    # 5. Регистрация
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
    # 6. Теги
    # ==========================================
    
    application.add_handler(CallbackQueryHandler(teg_view_role_handler, pattern=f"^{state.CD_TEG_ROLE}:"))
    application.add_handler(CallbackQueryHandler(teg_single_user_handler, pattern=f"^{state.CD_TEG_USER}:"))
    application.add_handler(CallbackQueryHandler(teg_all_users_handler, pattern=f"^{state.CD_TEG_ALL}:"))
    application.add_handler(CallbackQueryHandler(teg_back_handler, pattern=f"^{state.CD_TEG_BACK}$"))
    
    # ==========================================
    # 7. События (Events) - ОСНОВНАЯ ЧАСТЬ
    # ==========================================
    
    # Просмотр и действия
    application.add_handler(CallbackQueryHandler(show_event_detail, pattern=r"^evt_detail:"))
    application.add_handler(CallbackQueryHandler(handle_event_action, pattern=r"^event_(join|leave):"))
    application.add_handler(CallbackQueryHandler(back_to_events_list, pattern="^back_to_evt_list$"))
    
    # Создание (Админ)
    application.add_handler(CallbackQueryHandler(create_event_start, pattern="^crm_create_event$"))
    application.add_handler(CallbackQueryHandler(select_day, pattern=r"^evt_day:"))
    application.add_handler(CallbackQueryHandler(select_hour, pattern=r"^evt_hour:"))
    application.add_handler(CallbackQueryHandler(select_minute, pattern=r"^evt_min:"))
    application.add_handler(CallbackQueryHandler(back_to_day, pattern="^evt_back_day$"))
    application.add_handler(CallbackQueryHandler(back_to_hour, pattern="^evt_back_hour$"))
    application.add_handler(CallbackQueryHandler(cancel_creation, pattern="^cancel_event$"))
    
    # Удаление (Админ)
    application.add_handler(CallbackQueryHandler(delete_event, pattern=r"^evt_del:"))
    
    # Редактирование событий
    application.add_handler(CallbackQueryHandler(edit_event_start, pattern="^evt_edit:"))
    application.add_handler(CallbackQueryHandler(edit_title_start, pattern="^evt_edit_title$"))
    application.add_handler(CallbackQueryHandler(edit_time_start, pattern="^evt_edit_time$"))
    application.add_handler(CallbackQueryHandler(cancel_edit, pattern="^evt_edit_cancel$"))
    
    # ==========================================
    # 8. Микс (Турнир)
    # ==========================================
    
    application.add_handler(mix_conv_handler)
    
    # ==========================================
    # 9. Настройки (ДопФункционал)
    # ==========================================
    
    application.add_handler(CallbackQueryHandler(settings_del_user_start, pattern="^settings_del_user$"))
    application.add_handler(CallbackQueryHandler(settings_info, pattern="^settings_info$"))
    application.add_handler(CallbackQueryHandler(announce_start, pattern="^settings_announce$"))
    
    # ==========================================
    # 9.1. Обработчики объявлений
    # ==========================================
    
    application.add_handler(CallbackQueryHandler(announce_confirm, pattern="^announce_confirm$"))
    application.add_handler(CallbackQueryHandler(announce_edit, pattern="^announce_edit$"))
    application.add_handler(CallbackQueryHandler(announce_cancel, pattern="^announce_cancel$"))
    
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
    logger.info("🚀 Бот запущен и готов к работе!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()