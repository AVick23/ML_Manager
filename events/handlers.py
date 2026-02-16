"""
handlers.py
Обработчики команды и callback-запросов для событий.
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup  # ДОБАВЛЕН ИМПОРТ КНОПОК
from telegram.ext import ContextTypes

from db import Session, Event, EventParticipant, User  # ДОБАВЛЕН ИМПОРТ User
from config import ADMIN_IDS, logger
import state

from events.utils import (
    get_group_id, save_user_from_tg, get_event_by_id, 
    get_upcoming_events, get_event_participants, is_user_participant,
    format_user_mention, DATE_FORMAT, MSK_TZ
)
from events.keyboards import (
    get_events_list_kb, get_event_detail_kb,
    get_create_date_kb, get_create_hour_kb, get_create_minute_kb
)
from datetime import datetime, timedelta

# ==========================================
# ГЛАВНОЕ МЕНЮ СОБЫТИЙ (Entry Point)
# ==========================================

async def events_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Единая точка входа.
    Показывает список игр всем пользователям.
    Админы видят кнопку создания.
    """
    query = update.callback_query
    
    if query:
        await query.answer()
        user_id = query.from_user.id
    else:
        user_id = update.effective_user.id

    is_admin = user_id in ADMIN_IDS
    
    session = Session()
    try:
        events = get_upcoming_events(session)
        
        if not events:
            text = "🗓 *Расписание пусто*\n\nНет запланированных игр. Время отдыхать!"
        else:
            text = "🗓 *Расписание игр*\nВыберите событие для деталей:"
        
        reply_markup = get_events_list_kb(events, is_admin)
        
        if query:
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")
        else:
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")
            
    finally:
        session.close()

# ==========================================
# ПРОСМОТР И ДЕЙСТВИЯ (ЗАПИСЬ/ОТПИСКА)
# ==========================================

async def show_event_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Карточка события: время, участники, кнопки действий"""
    query = update.callback_query
    await query.answer()
    
    event_id = int(query.data.split(":")[1])
    user_id = query.from_user.id
    is_admin = user_id in ADMIN_IDS

    session = Session()
    try:
        event = get_event_by_id(session, event_id)
        if not event:
            return await query.edit_message_text("❌ Событие не найдено или удалено.")

        # Данные
        ev_time = datetime.strptime(event.event_time, DATE_FORMAT)
        time_str = ev_time.strftime("%d %b %Y, %H:%M")
        participants = get_event_participants(session, event_id)
        
        # Проверка статуса пользователя
        is_joined = is_user_participant(session, event_id, user_id)
        
        # --- Формирование текста ---
        lines = [
            f"🎯 *{event.title}*",
            f"🕒 *Время:* {time_str} (МСК)",
            f"\n-------------------"
        ]

        if not participants:
            lines.append("\n👻 *Участников пока нет*\nСтаньте первым!")
        else:
            lines.append(f"\n👥 *Участники ({len(participants)}):*")
            
            # Собираем имена
            p_user_ids = [p.user_id for p in participants]
            # Используем импортированный User
            users = session.query(User).filter(User.user_id.in_(p_user_ids)).all() if p_user_ids else []
            user_map = {u.user_id: u for u in users}
            
            for i, p in enumerate(participants, 1):
                u = user_map.get(p.user_id)
                lines.append(f"{i}. {format_user_mention(u)}")

        reply_markup = get_event_detail_kb(event_id, is_joined, is_admin)
        
        await query.edit_message_text(
            "\n".join(lines),
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        
    finally:
        session.close()

async def handle_event_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка записи/отписки"""
    query = update.callback_query
    await query.answer()
    
    action, event_id_str = query.data.split(":")
    event_id = int(event_id_str)
    user_id = query.from_user.id
    
    session = Session()
    try:
        event = get_event_by_id(session, event_id)
        if not event:
            return await query.answer("Событие было удалено.", show_alert=True)
        
        existing = session.query(EventParticipant).filter_by(
            event_id=event_id, user_id=user_id
        ).first()
        
        if action == "event_join":
            if existing:
                return await query.answer("Вы уже записаны!")
            
            session.add(EventParticipant(event_id=event_id, user_id=user_id))
            await save_user_from_tg(query.from_user)
            
            logger.info(f"✅ User {user_id} joined event {event_id}")
            await query.answer("Вы успешно записались!")
            
        elif action == "event_leave":
            if existing:
                session.delete(existing)
                logger.info(f"❌ User {user_id} left event {event_id}")
                await query.answer("Вы отписались.")
            else:
                return await query.answer("Вы не были записаны.")
        
        session.commit()
        
        # Обновляем сообщение
        query.data = f"evt_detail:{event_id}"
        await show_event_detail(update, context)
        
    except Exception as e:
        session.rollback()
        logger.error(f"Event action error: {e}")
        await query.answer("Ошибка обработки.", show_alert=True)
    finally:
        session.close()

# ==========================================
# АДМИНСКАЯ ЧАСТЬ: СОЗДАНИЕ
# ==========================================

async def create_event_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Шаг 1: Ввод названия (Только админ)"""
    query = update.callback_query
    if query: await query.answer()
    
    user_id = query.from_user.id if query else update.effective_user.id
    if user_id not in ADMIN_IDS:
        return await query.answer("🔒 Только админы могут создавать игры.", show_alert=True)
    
    context.user_data["crm_state"] = "awaiting_title"
    
    text = "📝 *Создание игры*\n\nВведите название события:"
    keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data="cancel_event")]]
    
    if query:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текстового ввода названия"""
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        return

    state_curr = context.user_data.get("crm_state")
    
    if state_curr == "awaiting_title":
        title = update.message.text.strip()
        if len(title) < 3:
            return await update.message.reply_text("Слишком коротко. Введите название:")
        
        context.user_data["event_title"] = title
        context.user_data["crm_state"] = "awaiting_date"
        return await ask_date(update, context)

async def ask_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Шаг 2: Выбор даты"""
    query = update.callback_query
    if query: await query.answer()

    title = context.user_data.get('event_title', 'Игра')
    text = f"📅 *{title}*\n\nВыберите дату:"
    
    reply_markup = get_create_date_kb()

    if query:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")

async def select_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    offset = int(query.data.split(":")[1])
    context.user_data["crm_day_offset"] = offset
    context.user_data["crm_state"] = "awaiting_hour"
    return await ask_hour(update, context)

async def ask_hour(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = "🕒 Выберите час:"
    await query.edit_message_text(text, reply_markup=get_create_hour_kb())

async def select_hour(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    hour = int(query.data.split(":")[1])
    context.user_data["crm_hour"] = hour
    context.user_data["crm_state"] = "awaiting_minute"
    return await ask_minute(update, context)

async def ask_minute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    h = context.user_data.get("crm_hour", 0)
    text = f"🕒 Время: {h:02d}:XX\nВыберите минуты:"
    await query.edit_message_text(text, reply_markup=get_create_minute_kb(h))

async def select_minute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Финал: Создание события в БД"""
    query = update.callback_query
    await query.answer()
    
    minute = int(query.data.split(":")[1])
    offset = context.user_data.get("crm_day_offset", 0)
    hour = context.user_data.get("crm_hour", 0)
    title = context.user_data.get("event_title")
    
    if not title:
        return await query.message.reply_text("❌ Ошибка: название утеряно.")
    
    now_msk = datetime.now(MSK_TZ)
    target_date_msk = now_msk + timedelta(days=offset)
    target_date_msk = target_date_msk.replace(hour=hour, minute=minute, second=0, microsecond=0)
    event_time_str = target_date_msk.strftime(DATE_FORMAT)
    
    session = Session()
    try:
        new_event = Event(title=title, event_time=event_time_str)
        session.add(new_event)
        session.commit()
        event_id = new_event.id
        logger.info(f"✅ Created event #{event_id}: '{title}' at {event_time_str}")
    except Exception as e:
        session.rollback()
        logger.error(f"DB Error: {e}")
        return await query.message.reply_text("❌ Ошибка БД.")
    finally:
        session.close()
    
    group_id = get_group_id(context)
    if group_id:
        try:
            notify_text = (
                f"📢 *НОВАЯ ИГРА!*\n\n"
                f"🎯 {title}\n"
                f"🗓 {event_time_str} (МСК)\n\n"
                f"Откройте бота, чтобы записаться!"
            )
            await context.bot.send_message(chat_id=group_id, text=notify_text, parse_mode="Markdown")
        except Exception as e:
            logger.warning(f"Notify error: {e}")
    
    context.user_data.clear()
    
    await query.message.reply_text(f"✅ Игра *{title}* создана!", parse_mode="Markdown")
    await events_menu(update, context)

# ==========================================
# АДМИНСКАЯ ЧАСТЬ: УДАЛЕНИЕ И ОТМЕНА
# ==========================================

async def delete_event(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удаление события"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    if user_id not in ADMIN_IDS:
        return await query.answer("Нет прав.", show_alert=True)
    
    event_id = int(query.data.split(":")[1])
    session = Session()
    try:
        event = get_event_by_id(session, event_id)
        if event:
            session.query(EventParticipant).filter_by(event_id=event_id).delete()
            session.delete(event)
            session.commit()
            await query.answer("Игра удалена.")
    except Exception as e:
        session.rollback()
        logger.error(f"Del error: {e}")
    finally:
        session.close()
    
    return await events_menu(update, context)

async def cancel_creation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    await query.edit_message_text("❌ Создание отменено.")
    return await events_menu(update, context)

async def back_to_events_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query: await update.callback_query.answer()
    return await events_menu(update, context)

async def back_to_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    return await ask_date(update, context)

async def back_to_hour(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    return await ask_hour(update, context)

# ==========================================
# ПЛАНИРОВЩИК (Уведомления)
# ==========================================

async def check_and_notify_events(context: ContextTypes.DEFAULT_TYPE):
    """Умные уведомления о начале игры"""
    session = Session()
    try:
        now_msk = datetime.now(MSK_TZ)
        now_str = now_msk.strftime(DATE_FORMAT)
        window = (now_msk + timedelta(minutes=1)).strftime(DATE_FORMAT)
        
        events = session.query(Event).filter(
            Event.event_time >= now_str,
            Event.event_time <= window,
            Event.status == 'Scheduled'
        ).all()
        
        if not events: return
        
        group_id = get_group_id(context)
        if not group_id: return
        
        for ev in events:
            participants = get_event_participants(session, ev.id)
            user_ids = [p.user_id for p in participants]
            # Используем импортированный User
            users = session.query(User).filter(User.user_id.in_(user_ids)).all() if user_ids else []
            
            notify_blocks = []
            header = (
                f"📢 *ИГРА НАЧИНАЕТСЯ!*\n"
                f"🎯 {ev.title}\n\n"
                f"⚔️ Призыв игроков:"
            )
            
            lines = [header]
            for u in users:
                lines.append(f"• {format_user_mention(u)}")
                if len(lines) >= 10:
                    notify_blocks.append("\n".join(lines))
                    lines = []
            
            if lines:
                notify_blocks.append("\n".join(lines))
            
            for block in notify_blocks:
                await context.bot.send_message(chat_id=group_id, text=block, parse_mode="Markdown")
            
            ev.status = 'Done'
        
        session.commit()
        
    except Exception as e:
        logger.error(f"Scheduler error: {e}")
        session.rollback()
    finally:
        session.close()