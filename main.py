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
    
    # Приоритет проверки состояний:
    # 1. CRM (Создание игры)
    # 2. Настройки (Удаление игрока)
    # 3. Регистрация (Ввод ID роли)
    
    if "crm_state" in u_state and u_state["crm_state"]:
        await handle_crm_input(update, context)
    elif "settings_state" in u_state and u_state["settings_state"]:
        await handle_global_delete_input(update, context)
    elif "reg_state" in u_state and u_state["reg_state"]:
        await handle_registration_input(update, context)
    # Если ни одно состояние не совпадает - игнорируем сообщение

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
    Доступно ВСЕМ пользователям.
    """
    if update.effective_chat.type not in ["group", "supergroup"]:
        return

    user = update.effective_user
    chat = update.effective_chat

    # Сохраняем/обновляем пользователя в базе
    await db.save_user(
        user_id=user.id,
        first_name=user.first_name,
        last_name=user.last_name,
        username=user.username
    )
    
    # Запоминаем ID группы, чтобы работала функция "Тегнуть всех"
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
    # 1. Системные и групповые хендлеры
    # ==========================================
    
    application.add_handler(ChatMemberHandler(on_chat_member_update))
    
    # ГРУППЫ ХЕНДЛЕРОВ (GROUPS):
    # Используем группы, чтобы несколько хендлеров могли работать одновременно в группе.
    # Группа 0 (по умолчанию): Сохранение статистики (handle_group_message)
    # Группа 1: Реакция на "Кто" (who_is_handler)
    
    # Группа 0: Сохраняет юзера и ID группы для тегов. Всегда работает.
    application.add_handler(
        MessageHandler(filters.ChatType.GROUPS, handle_group_message), 
        group=0
    )
    
    # Группа 1: Проверяет, не написал ли кто-то "Кто" в ответ. 
    # Если условие не выполнено, просто пропускает сообщение.
    application.add_handler(
        MessageHandler(filters.ChatType.GROUPS & filters.TEXT & filters.REPLY, who_is_handler), 
        group=1
    )
    
    # ==========================================
    # 2. Команды
    # ==========================================
    
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("me", profile_command)) # Доступна всем
    application.add_handler(CommandHandler("join", join_menu))
    
    # ==========================================
    # 3. Главное меню (Dashboard Callbacks)
    # ==========================================
    
    application.add_handler(CallbackQueryHandler(show_all_players, pattern=f"^{state.CD_MENU_PLAYERS}"))
    application.add_handler(CallbackQueryHandler(reg_menu, pattern=f"^{state.CD_MENU_REG}$"))
    application.add_handler(CallbackQueryHandler(tag_menu, pattern=f"^{state.CD_MENU_TAG}$"))
    application.add_handler(CallbackQueryHandler(crm_menu, pattern=f"^{state.CD_MENU_CRM}$"))
    application.add_handler(CallbackQueryHandler(tournament_menu, pattern=f"^{state.CD_MENU_TOURNAMENT}$"))
    application.add_handler(CallbackQueryHandler(settings_menu, pattern=f"^{state.CD_MENU_SETTINGS}$"))
    application.add_handler(CallbackQueryHandler(back_to_menu_handler, pattern=f"^{state.CD_BACK_TO_MENU}$"))
    
    # ==========================================
    # 4. Регистрация (Registration Callbacks)
    # ==========================================
    
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
    
    # ==========================================
    # 5. Теги (Tag Callbacks)
    # ==========================================
    
    application.add_handler(CallbackQueryHandler(teg_view_role_handler, pattern=f"^{state.CD_TEG_ROLE}:"))
    application.add_handler(CallbackQueryHandler(teg_single_user_handler, pattern=f"^{state.CD_TEG_USER}:"))
    application.add_handler(CallbackQueryHandler(teg_all_users_handler, pattern=f"^{state.CD_TEG_ALL}:"))
    application.add_handler(CallbackQueryHandler(teg_back_handler, pattern=f"^{state.CD_TEG_BACK}$"))
    
    # ==========================================
    # 6. CRM (Игры и Планирование)
    # ==========================================
    
    application.add_handler(CallbackQueryHandler(crm_create_event_start, pattern="^crm_create_event$"))
    
    # КАЛЕНДАРЬ
    application.add_handler(CallbackQueryHandler(evt_select_day, pattern=r"^evt_day:"))
    application.add_handler(CallbackQueryHandler(evt_select_hour, pattern=r"^evt_hour:"))
    application.add_handler(CallbackQueryHandler(evt_select_minute, pattern=r"^evt_min:"))
    application.add_handler(CallbackQueryHandler(evt_back_day, pattern="^evt_back_day$"))
    application.add_handler(CallbackQueryHandler(evt_back_hour, pattern="^evt_back_hour$"))
    application.add_handler(CallbackQueryHandler(evt_cancel, pattern="^cancel_event$"))
    
    # ПРОСМОТР СОСТАВА И УДАЛЕНИЕ
    application.add_handler(CallbackQueryHandler(evt_view_participants, pattern=r"^evt_view:"))
    application.add_handler(CallbackQueryHandler(evt_delete_event, pattern=r"^evt_del:"))
    application.add_handler(CallbackQueryHandler(back_to_crm_menu, pattern="^back_to_crm_menu$"))
    
    # ЗАПИСЬ ИГРОКОВ
    application.add_handler(CallbackQueryHandler(handle_event_action, pattern=r"^event_(join|leave):"))
    
    # ==========================================
    # 7. Микс (Турнир)
    # ==========================================
    
    # ВАЖНО: ConversationHandler должен стоять ДО обычных MessageHandler с текстом!
    application.add_handler(mix_conv_handler)
    
    # ==========================================
    # 8. Настройки (Settings Callbacks)
    # ==========================================
    
    application.add_handler(CallbackQueryHandler(settings_del_user_start, pattern="^settings_del_user$"))
    application.add_handler(CallbackQueryHandler(settings_info, pattern="^settings_info$"))
    
    # ==========================================
    # 9. Текстовый ввод (Unified Handler)
    # ==========================================
    
    # Обработчик текста в ЛС (диспетчер состояний)
    application.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND,
            dispatch_private_text
        )
    )
    
    # ==========================================
    # ЗАПУСК
    # ==========================================
    
    # ЗАПУСК ПЛАНИРОВЩИКА (Отправка уведомлений о матчах)
    start_scheduler(application)
    
    # ВОССТАНОВЛЯЕМ ФУНКЦИЮ run_polling
    application.run_polling()

if __name__ == "__main__":
    main()