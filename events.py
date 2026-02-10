from datetime import datetime, timedelta, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from db import (
    Event, EventParticipant, User, Session, 
    is_user_admin, ADMIN_IDS
)
import state

# Формат даты для хранения в БД
DATE_FORMAT = "%Y-%m-%d %H:%M"

# Часовой пояс Москвы (UTC+3)
MSK_TZ = timezone(timedelta(hours=3))

def escape_markdown(text):
    """ Экранирует спецсимволы Markdown """
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return ''.join(f'\\{char}' if char in escape_chars else char for char in str(text))

# --- АДМИНСКАЯ ЧАСТЬ ---

async def crm_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query: await query.answer()
    
    user_id = query.from_user.id if query else update.effective_user.id
    if not await is_user_admin(user_id):
        msg = "❌ Эта функция доступна только администраторам."
        if query: return await query.edit_message_text(msg)
        else: return await update.message.reply_text(msg)

    session = Session()
    try:
        events = session.query(Event).filter(Event.status == 'Scheduled').order_by(Event.event_time).all()
    finally:
        session.close()
    
    text = "📅 **Планирование игр (CRM)**\n\n"
    
    if not events:
        text += "Активных игр нет."
        keyboard = [
            [InlineKeyboardButton("➕ Создать игру", callback_data="crm_create_event")],
            [InlineKeyboardButton("⬅ Назад в меню", callback_data=state.CD_BACK_TO_MENU)]
        ]
    else:
        for ev in events:
            count = session.query(EventParticipant).filter_by(event_id=ev.id).count()
            safe_title = escape_markdown(ev.title)
            text += f"📆 {safe_title}\n"
            text += f"🕒 {ev.event_time} (МСК)\n"
            text += f"👥 Участников: {count}\n\n"
        
        # Генерируем клавиатуру с кнопками для каждой игры
        keyboard = []
        for ev in events:
            btn_view = InlineKeyboardButton("👥 Состав", callback_data=f"evt_view:{ev.id}")
            btn_del = InlineKeyboardButton("🗑 Удалить", callback_data=f"evt_del:{ev.id}")
            keyboard.append([btn_view, btn_del])
        
        keyboard.append([InlineKeyboardButton("➕ Создать игру", callback_data="crm_create_event")])
        keyboard.append([InlineKeyboardButton("⬅ Назад в меню", callback_data=state.CD_BACK_TO_MENU)])
    
    if query:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def crm_create_event_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ Шаг 1: Ввод названия """
    query = update.callback_query
    if query: await query.answer()
    
    context.user_data["crm_state"] = "awaiting_title"
    
    text = (
        "➕ **Создание новой игры**\n\n"
        "1. Введите название игры (например: Турнир против Team Alpha)."
    )
    
    if query:
        await query.edit_message_text(text)
    else:
        await update.message.reply_text(text)

# --- ФУНКЦИЯ ПРОСМОТРА СОСТАВА (НОВАЯ) ---

async def evt_view_participants(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ Показывает, кто записан на конкретную игру """
    query = update.callback_query
    await query.answer()
    
    # Парсинг ID
    event_id_str = query.data.split(":")[1]
    event_id = int(event_id_str)
    
    session = Session()
    try:
        event = session.query(Event).get(event_id)
        if not event:
            return await query.message.reply_text("Игра не найдена.")
        
        participants = session.query(EventParticipant).filter_by(event_id=event_id).all()
        users = session.query(User).filter(User.user_id.in_([p.user_id for p in participants])).all()
        
        text = f"📋 **Состав игры:** {escape_markdown(event.title)}\n\n"
        
        if not users:
            text += "Пока никто не записался."
        else:
            for u in users:
                name = f"{u.first_name} (@{u.username})" if u.username else u.first_name
                text += f"• {name}\n"
        
        # Кнопка возврата
        keyboard = [[InlineKeyboardButton("⬅ Назад", callback_data="back_to_crm_menu")]]
        
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        
    finally:
        session.close()

# --- ФУНКЦИЯ УДАЛЕНИЯ ИГРЫ (НОВАЯ) ---

async def evt_delete_event(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ Удаляет игру и всех участников """
    query = update.callback_query
    await query.answer()
    
    # Парсинг ID
    event_id_str = query.data.split(":")[1]
    event_id = int(event_id_str)
    
    session = Session()
    try:
        event = session.query(Event).get(event_id)
        if not event:
            return await query.message.reply_text("Игра не найдена.")
        
        # Сначала удаляем участников (чтобы не оставалось мусора в БД)
        session.query(EventParticipant).filter_by(event_id=event_id).delete()
        
        # Потом удаляем саму игру
        session.delete(event)
        session.commit()
        
        await query.message.reply_text(f"✅ Игра {escape_markdown(event.title)} удалена.")
        # Обновляем меню
        return await crm_menu(update, context)
        
    except Exception as e:
        session.rollback()
        await query.message.reply_text(f"❌ Ошибка при удалении: {e}")
    finally:
        session.close()

async def back_to_crm_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ Возврат в CRM меню из просмотра состава """
    query = update.callback_query
    if query: await query.answer()
    return await crm_menu(update, context)

# --- СОЗДАНИЕ ИГРЫ (Календарь) ---

async def ask_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ Шаг 2: Выбор даты (Сегодня + 7 дней) """
    query = update.callback_query
    if query: await query.answer()

    title = context.user_data.get('event_title', 'Неизвестно')
    text = f"✅ Название: {title}\n\n"
    text += "2. Выберите дату игры:"
    
    keyboard = []
    now = datetime.now(MSK_TZ)
    for i in range(0, 8):
        event_date = now + timedelta(days=i)
        day_name = event_date.strftime("%d %b (%a)")
        btn = InlineKeyboardButton(day_name, callback_data=f"evt_day:{i}")
        keyboard.append([btn])

    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="cancel_event")])

    if query:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def ask_hour(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ Шаг 3: Выбор часа (00-23) """
    query = update.callback_query
    if query: await query.answer()

    text += "3. Выберите час:"
    keyboard = []
    
    row = []
    for i in range(0, 24):
        hour_str = f"{i:02d}"
        row.append(InlineKeyboardButton(hour_str, callback_data=f"evt_hour:{i}"))
        if len(row) == 4:
            keyboard.append(row)
            row = []
    if row: keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("⬅ Назад", callback_data="evt_back_day")])

    if query:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def ask_minute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ Шаг 4: Выбор минут (00, 15, 30, 45) """
    query = update.callback_query
    if query: await query.answer()
    
    selected_hour = context.user_data.get("crm_hour", "00")
    text += f"3. Выбранное время: {selected_hour}:XX\n\n"
    text += "4. Выберите минуты:"
    
    keyboard = [
        [
            InlineKeyboardButton("00", callback_data="evt_min:00"),
            InlineKeyboardButton("15", callback_data="evt_min:15"),
            InlineKeyboardButton("30", callback_data="evt_min:30"),
            InlineKeyboardButton("45", callback_data="evt_min:45")
        ],
        [InlineKeyboardButton("⬅ Назад", callback_data="evt_back_hour")]
    ]
    
    if query:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

# --- ХЕНДЛЕРЫ ВВОДА И ВЫБОРА ---

async def handle_crm_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ Обработка ввода названия """
    if not await is_user_admin(update.effective_user.id):
        return await update.message.reply_text("❌ Нет прав.")

    state_curr = context.user_data.get("crm_state")
    
    if state_curr == "awaiting_title":
        title = update.message.text.strip()
        if not title:
            return await update.message.reply_text("❌ Название не может быть пустым.")
        
        context.user_data["event_title"] = title
        context.user_data["crm_state"] = "awaiting_date"
        return await ask_date(update, context)

async def evt_select_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    _, offset_str = query.data.split(":")
    offset = int(offset_str)
    
    context.user_data["crm_day_offset"] = offset
    context.user_data["crm_state"] = "awaiting_hour"
    
    return await ask_hour(update, context)

async def evt_back_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["crm_state"] = "awaiting_date"
    return await ask_date(update, context)

async def evt_select_hour(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    _, hour_str = query.data.split(":")
    hour = int(hour_str)
    
    context.user_data["crm_hour"] = hour
    context.user_data["crm_state"] = "awaiting_minute"
    
    return await ask_minute(update, context)

async def evt_back_hour(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["crm_state"] = "awaiting_hour"
    return await ask_hour(update, context)

async def evt_select_minute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ Создание игры """
    query = update.callback_query
    await query.answer()
    
    _, minute_str = query.data.split(":")
    minute = int(minute_str)
    
    offset = context.user_data.get("crm_day_offset", 0)
    hour = context.user_data.get("crm_hour", 0)
    title = context.user_data.get("event_title")
    
    if not title:
        return await query.message.reply_text("❌ Ошибка: Название утеряно. Начните заново.")
    
    # Формируем дату и время по МСК
    now_msk = datetime.now(MSK_TZ)
    target_date_msk = now_msk + timedelta(days=offset)
    target_date_msk = target_date_msk.replace(hour=hour, minute=minute, second=0, microsecond=0)
    
    # Сохраняем в БД
    event_time_str = target_date_msk.strftime(DATE_FORMAT)
    
    session = Session()
    try:
        new_event = Event(title=title, event_time=event_time_str)
        session.add(new_event)
        session.commit()
        event_id = new_event.id
    finally:
        session.close()
    
    context.user_data.clear()
    
    msg = (
        f"✅ Игра создана!\n"
        f"Название: {title}\n"
        f"Время: {event_time_str} (МСК)"
    )
    await query.message.reply_text(msg)
    return await crm_menu(update, context)

async def evt_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    await query.edit_message_text("❌ Отмена.")
    return await crm_menu(update, context)

# --- ИГРОКОВАЯ ЧАСТЬ ---

async def join_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ Команда для игрока: записаться на игру """
    query = update.callback_query
    if query: await query.answer()
    
    user_id = query.from_user.id if query else update.effective_user.id
    
    session = Session()
    try:
        events = session.query(Event).filter(Event.status == 'Scheduled').order_by(Event.event_time).all()
    finally:
        session.close()
    
    if not events:
        msg = "Сейчас нет запланированных игр."
        if query:
            return await query.edit_message_text(msg)
        else:
            return await update.message.reply_text(msg)
    
    text = "📋 **Выберите игру для записи:**\n\n"
    keyboard = []
    
    for ev in events:
        is_joined = session.query(EventParticipant).filter_by(event_id=ev.id, user_id=user_id).first()
        btn_text = f"{'✅' if is_joined else '➕'} {ev.title} ({ev.event_time})"
        cb_data = f"event_join:{ev.id}" if not is_joined else f"event_leave:{ev.id}"
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=cb_data)])
    
    if query:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def handle_event_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ Запись или отписка """
    query = update.callback_query
    await query.answer()
    
    action, event_id_str = query.data.split(":")
    event_id = int(event_id_str)
    user_id = query.from_user.id
    
    session = Session()
    try:
        event = session.query(Event).get(event_id)
        if not event:
            return await query.message.reply_text("Игра не найдена.")
        
        existing = session.query(EventParticipant).filter_by(event_id=event_id, user_id=user_id).first()
        
        if action == "event_join":
            if existing:
                return await query.answer("Вы уже записаны.")
            new_part = EventParticipant(event_id=event_id, user_id=user_id)
            session.add(new_part)
            msg = f"✅ Вы записались на: {event.title}"
        elif action == "event_leave":
            if existing:
                session.delete(existing)
                msg = f"❌ Вы отписались от: {event.title}"
            else:
                return await query.answer("Вы не были записаны.")
        
        session.commit()
        await join_menu(update, context)
        
    except Exception as e:
        session.rollback()
        await query.message.reply_text(f"Ошибка: {e}")
    finally:
        session.close()

# --- СИСТЕМА УВЕДОМЛЕНИЙ ---

async def check_and_notify_events(context: ContextTypes.DEFAULT_TYPE):
    """ Функция запускается раз в минуту шедулером """
    session = Session()
    try:
        now_str = datetime.now(MSK_TZ).strftime(DATE_FORMAT)
        
        events = session.query(Event).filter(
            Event.event_time == now_str,
            Event.status == 'Scheduled'
        ).all()
        
        for ev in events:
            participants = session.query(EventParticipant).filter_by(event_id=ev.id).all()
            users = session.query(User).filter(User.user_id.in_([p.user_id for p in participants])).all()
            
            usernames = [f"@{u.username}" for u in users if u.username]
            tags = " ".join(usernames)
            
            if tags:
                safe_title = escape_markdown(ev.title)
                message = (
                    f"📢 **НАЧАЛО ИГРЫ!**\n\n"
                    f"Мероприятие: {safe_title}\n"
                    f"Время: {ev.event_time}\n\n"
                    f"Призыв:\n{tags}\n\n"
                    f"Гоу ребят!"
                )
                group_id = context.bot_data.get("last_admin_group_id")
                if group_id:
                    try:
                        await context.bot.send_message(chat_id=group_id, text=message, parse_mode='Markdown')
                    except Exception as e:
                        print(f"Не могу отправить в чат {group_id}: {e}")
            
            ev.status = 'Done'
            session.commit()
            
    finally:
        session.close()