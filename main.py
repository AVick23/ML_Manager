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
from events import (
    crm_menu, crm_create_event_start, handle_crm_input,
    join_menu, handle_event_action,
    evt_select_day, evt_select_hour, evt_select_minute,
    evt_back_day, evt_back_hour, evt_cancel,
    evt_view_participants, evt_delete_event, back_to_crm_menu
)
from scheduler import start_scheduler
from tournament import tournament_menu, mix_conv_handler


# ==========================================
# ДИСПЕТЧЕР ТЕКСТОВЫХ СООБЩЕНИЙ (ЛС)
# ==========================================

async def dispatch_private_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Перенаправляет текстовые сообщения в зависимости от состояния пользователя"""
    u_state = context.user_data
    
    if "crm_state" in u_state and u_state["crm_state"]:
        await handle_crm_input(update, context)
    elif "settings_state" in u_state and u_state["settings_state"]:
        await handle_global_delete_input(update, context)
    elif "reg_state" in u_state and u_state["reg_state"]:
        await handle_registration_input(update, context)


# ==========================================
# ГРУППОВЫЕ СОБЫТИЯ
# ==========================================

async def on_chat_member_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка изменения состава чата (добавление/удаление участников)"""
    if not update.chat_member:
        return
    
    result = update.chat_member
    new_member = result.new_chat_member

    # Бот был добавлен в группу
    if new_member.user.id == context.bot.id:
        if new_member.status == "member":
            chat_id = update.effective_chat.id
            logger.info(f"🤖 Бот добавлен в группу: {chat_id}")
            await update.effective_chat.send_message(
                "✅ Привет! Я запомню эту группу для уведомлений о играх."
            )
            
            # === ИСПРАВЛЕНО: Запоминаем группу при добавлении бота ===
            if not GROUP_ID:
                context.bot_data["last_admin_group_id"] = chat_id
                logger.info(f"📌 Группа {chat_id} сохранена для уведомлений")
        return

    # Новый участник в группе
    if new_member.status not in ["left", "kicked"]:
        user = new_member.user
        await save_user(
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

    await save_user(
        user_id=user.id,
        first_name=user.first_name,
        last_name=user.last_name,
        username=user.username
    )
    
    # === ИСПРАВЛЕНО: Fallback для GROUP_ID ===
    # Запоминаем группу только если GROUP_ID не задан в .env
    if not GROUP_ID:
        context.bot_data["last_admin_group_id"] = chat.id


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Глобальный обработчик ошибок"""
    if context.error is None:
        return
    
    # Игнорируем известные не критичные ошибки
    if "NoneType" in str(context.error) and "new_chat_member" in str(context.error):
        return
    
    logger.error(f"❌ Ошибка: {context.error}", exc_info=True)


# ==========================================
# MAIN
# ==========================================

def main():
    """Точка входа в приложение"""
    logger.info("🤖 Запуск ML Manager Bot...")
    
    # Выводим конфигурацию
    log_config()
    
    if not BOT_TOKEN:
        raise ValueError("❌ BOT_TOKEN не найден!")

    # Создаём приложение
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_error_handler(error_handler)
    
    # ==========================================
    # 1. Системные хендлеры
    # ==========================================
    application.add_handler(ChatMemberHandler(on_chat_member_update))

    # ==========================================
    # 2. Команды (Группа 0 - Высокий приоритет)
    # ==========================================
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("me", profile_command))
    application.add_handler(CommandHandler("join", join_menu))

    # ==========================================
    # 3. Групповые хендлеры (Распределение по группам)
    # ==========================================
    
    # ГРУППА 1: Реакция на "Кто"
    application.add_handler(
        MessageHandler(filters.ChatType.GROUPS & filters.TEXT & filters.REPLY, who_is_handler),
        group=1
    )

    # ГРУППА 2: Сбор статистики (Фоновый)
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
    
    # Запускаем планировщик
    start_scheduler(application)
    
    logger.info("🚀 Бот запущен и готов к работе!")
    
    # Запускаем поллинг
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()