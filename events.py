"""
Модуль управления событиями (играми).
Содержит функции для создания, просмотра, удаления игр и уведомлений.
"""
from datetime import datetime, timedelta, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.helpers import mention_html

from db import Event, EventParticipant, User, Session
from config import is_user_admin, ADMIN_IDS, GROUP_ID, logger
import state

# Формат даты для хранения в БД
DATE_FORMAT = "%Y-%m-%d %H:%M"

# Часовой пояс Москвы (UTC+3)
MSK_TZ = timezone(timedelta(hours=3))


def escape_markdown(text):
    """Экранирует спецсимволы Markdown"""
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return ''.join(f'\\{char}' if char in escape_chars else char for char in str(text))


def get_group_id(context: ContextTypes.DEFAULT_TYPE) -> int | None:
    """
    Получает ID группы для отправки уведомлений.
    
    Приоритет:
    1. GROUP_ID из config.py (из .env)
    2. last_admin_group_id из bot_data (автоопределение)
    
    Returns:
        int | None: ID группы или None
    """
    # Приоритет - GROUP_ID из конфига
    if GROUP_ID:
        return GROUP_ID
    
    # Fallback - автоопределение
    group_id = context.bot_data.get("last_admin_group_id")
    
    if not group_id:
        logger.warning("⚠️ GROUP_ID не настроен и не определён автоматически")
    
    return group_id


def format_user_mention(user: User) -> str:
    """
    Форматирует упоминание пользователя.
    Если есть username - возвращает @username
    Если нет - возвращает кликабельное упоминание через mention_html
    
    Args:
        user: Объект User из БД
        
    Returns:
        str: Форматированная строка для упоминания
    """
    if user.username:
        return f"@{user.username}"
    else:
        # Используем HTML-упоминание по ID
        return mention_html(user.user_id, user.first_name or "Игрок")


# ==========================================
# АДМИНСКАЯ ЧАСТЬ - CRM МЕНЮ
# ==========================================

async def crm_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Главное меню управления событиями (CRM)"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = query.from_user.id if query else update.effective_user.id
    
    # Проверка прав администратора
    if user_id not in ADMIN_IDS:
        msg = "❌ Эта функция доступна только администраторам."
        if query:
            return await query.edit_message_text(msg)
        else:
            return await update.message.reply_text(msg)

    session = Session()
    try:
        events = session.query(Event).filter(
            Event.status == 'Scheduled'
        ).order_by(Event.event_time).all()
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
            # Считаем участников
            session2 = Session()
            try:
                count = session2.query(EventParticipant).filter_by(event_id=ev.id).count()
            finally:
                session2.close()
            
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
        await query.edit_message_text(
            text, 
            reply_markup=InlineKeyboardMarkup(keyboard), 
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            text, 
            reply_markup=InlineKeyboardMarkup(keyboard), 
            parse_mode='Markdown'
        )


async def crm_create_event_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Шаг 1: Ввод названия игры"""
    query = update.callback_query
    if query:
        await query.answer()
    
    context.user_data["crm_state"] = "awaiting_title"
    
    text = "➕ **Создание новой игры**\n\n"
    text += "1. Введите название игры (например: Турнир против Team Alpha)."
    
    if query:
        await query.edit_message_text(text)
    else:
        await update.message.reply_text(text)


async def ask_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Шаг 2: Выбор даты (Сегодня + 7 дней)"""
    query = update.callback_query
    if query:
        await query.answer()

    title = context.user_data.get('event_title', 'Неизвестно')
    text = f"✅ Название: {title}\n\n"
    text += "2. Выберите дату игры (по МСК):"
    
    keyboard = []
    now = datetime.now(MSK_TZ)
    
    # Генерируем кнопки на ближайшие 7 дней
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
    """Шаг 3: Выбор часа (00-23)"""
    query = update.callback_query
    if query:
        await query.answer()

    title = context.user_data.get('event_title', 'Неизвестно')
    text = f"✅ Название: {title}\n\n"
    text += "3. Выберите час (по МСК):"
    
    keyboard = []
    
    row = []
    for i in range(0, 24):
        hour_str = f"{i:02d}"
        row.append(InlineKeyboardButton(hour_str, callback_data=f"evt_hour:{i}"))
        if len(row) == 4:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("⬅ Назад", callback_data="evt_back_day")])

    if query:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def ask_minute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Шаг 4: Выбор минут (00, 15, 30, 45)"""
    query = update.callback_query
    if query:
        await query.answer()
    
    title = context.user_data.get('event_title', 'Неизвестно')
    selected_hour = context.user_data.get("crm_hour", "00")
    text = f"✅ Название: {title}\n"
    text += f"🕒 Выбранное время (МСК): {selected_hour}:XX\n\n"
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


# ==========================================
# ХЕНДЛЕРЫ ВВОДА
# ==========================================

async def handle_crm_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода названия игры"""
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        return await update.message.reply_text("❌ Нет прав.")

    state_curr = context.user_data.get("crm_state")
    
    if state_curr == "awaiting_title":
        title = update.message.text.strip()
        if not title:
            return await update.message.reply_text("❌ Название не может быть пустым.")
        
        context.user_data["event_title"] = title
        context.user_data["crm_state"] = "awaiting_date"
        
        # Вызываем функцию с кнопками даты
        return await ask_date(update, context)


async def evt_select_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка нажатия на дату"""
    query = update.callback_query
    await query.answer()
    
    _, offset_str = query.data.split(":")
    offset = int(offset_str)
    
    context.user_data["crm_day_offset"] = offset
    context.user_data["crm_state"] = "awaiting_hour"
    
    return await ask_hour(update, context)


async def evt_back_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Возврат к выбору даты"""
    query = update.callback_query
    await query.answer()
    context.user_data["crm_state"] = "awaiting_date"
    return await ask_date(update, context)


async def evt_select_hour(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка нажатия на час"""
    query = update.callback_query
    await query.answer()
    
    _, hour_str = query.data.split(":")
    hour = int(hour_str)
    
    context.user_data["crm_hour"] = hour
    context.user_data["crm_state"] = "awaiting_minute"
    
    return await ask_minute(update, context)


async def evt_back_hour(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Возврат к выбору часа"""
    query = update.callback_query
    await query.answer()
    context.user_data["crm_state"] = "awaiting_hour"
    return await ask_hour(update, context)


async def evt_select_minute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обработка нажатия на минуту и СОЗДАНИЕ ИГРЫ.
    
    ИСПРАВЛЕНО: Добавлено уведомление в группу при создании игры.
    """
    query = update.callback_query
    await query.answer()
    
    _, minute_str = query.data.split(":")
    minute = int(minute_str)
    
    # Считываем данные из контекста
    offset = context.user_data.get("crm_day_offset", 0)
    hour = context.user_data.get("crm_hour", 0)
    title = context.user_data.get("event_title")
    
    if not title:
        return await query.message.reply_text("❌ Ошибка: Название утеряно. Начните заново.")
    
    # Формируем дату и время по московскому времени
    now_msk = datetime.now(MSK_TZ)
    target_date_msk = now_msk + timedelta(days=offset)
    target_date_msk = target_date_msk.replace(
        hour=hour, 
        minute=minute, 
        second=0, 
        microsecond=0
    )
    
    # Сохраняем в БД
    event_time_str = target_date_msk.strftime(DATE_FORMAT)
    
    session = Session()
    try:
        new_event = Event(title=title, event_time=event_time_str)
        session.add(new_event)
        session.commit()
        event_id = new_event.id
        logger.info(f"✅ Создана игра #{event_id}: '{title}' на {event_time_str}")
    except Exception as e:
        session.rollback()
        logger.error(f"❌ Ошибка создания игры: {e}")
        await query.message.reply_text(f"❌ Ошибка создания игры: {e}")
        return
    finally:
        session.close()
    
    # === НОВОЕ: Уведомление в группу о создании игры ===
    group_id = get_group_id(context)
    
    if group_id:
        try:
            notify_text = (
                f"🎮 **Новая игра создана!**\n\n"
                f"📅 Название: {escape_markdown(title)}\n"
                f"🕒 Время: {event_time_str} (МСК)\n\n"
                f"📝 Для записи используйте /join в ЛС бота."
            )
            await context.bot.send_message(
                chat_id=group_id,
                text=notify_text,
                parse_mode='Markdown'
            )
            logger.info(f"📢 Уведомление о создании игры отправлено в группу {group_id}")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось отправить уведомление в группу: {e}")
    else:
        logger.warning("⚠️ GROUP_ID не настроен, уведомление в группу не отправлено")
    
    # Очищаем контекст
    context.user_data.clear()
    
    # Уведомление админу
    msg = (
        f"✅ Игра создана!\n"
        f"Название: {title}\n"
        f"Время: {event_time_str} (МСК)"
    )
    await query.message.reply_text(msg)
    
    # Возвращаемся в меню CRM
    return await crm_menu(update, context)


async def evt_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена создания игры"""
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    logger.info("❌ Создание игры отменено")
    await query.edit_message_text("❌ Отмена.")
    return await crm_menu(update, context)


# ==========================================
# ПРОСМОТР СОСТАВА И УДАЛЕНИЕ ИГРЫ
# ==========================================

async def evt_view_participants(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает, кто записан на конкретную игру"""
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
        
        # Получаем данные пользователей
        user_ids = [p.user_id for p in participants]
        users = session.query(User).filter(User.user_id.in_(user_ids)).all() if user_ids else []
        
        # Создаём мапу user_id -> User
        user_map = {u.user_id: u for u in users}
        
        text = f"📋 **Состав игры:** {escape_markdown(event.title)}\n\n"
        
        if not participants:
            text += "Пока никто не записался."
        else:
            for p in participants:
                u = user_map.get(p.user_id)
                if u:
                    text += f"• {format_user_mention(u)}\n"
                else:
                    text += f"• Пользователь ID: {p.user_id}\n"
        
        # Кнопка возврата
        keyboard = [[InlineKeyboardButton("⬅ Назад", callback_data="back_to_crm_menu")]]
        
        await query.edit_message_text(
            text, 
            reply_markup=InlineKeyboardMarkup(keyboard), 
            parse_mode='Markdown'
        )
        
    finally:
        session.close()


async def evt_delete_event(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удаляет игру и всех участников"""
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
        
        event_title = event.title
        
        # Сначала удаляем участников
        deleted_count = session.query(EventParticipant).filter_by(event_id=event_id).delete()
        
        # Потом удаляем саму игру
        session.delete(event)
        session.commit()
        
        logger.info(f"🗑 Игра '{event_title}' удалена. Удалено участников: {deleted_count}")
        
        await query.message.reply_text(f"✅ Игра {escape_markdown(event_title)} удалена.")
        
        # Обновляем меню
        return await crm_menu(update, context)
        
    except Exception as e:
        session.rollback()
        logger.error(f"❌ Ошибка при удалении игры: {e}")
        await query.message.reply_text(f"❌ Ошибка при удалении: {e}")
    finally:
        session.close()


async def back_to_crm_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Возврат в CRM меню из просмотра состава"""
    query = update.callback_query
    if query:
        await query.answer()
    return await crm_menu(update, context)


# ==========================================
# ИГРОКОВАЯ ЧАСТЬ (Запись / Отписка)
# ==========================================

async def join_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для игрока: записаться на игру"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = query.from_user.id if query else update.effective_user.id
    
    session = Session()
    try:
        events = session.query(Event).filter(
            Event.status == 'Scheduled'
        ).order_by(Event.event_time).all()
        
        if not events:
            msg = "Сейчас нет запланированных игр."
            if query:
                return await query.edit_message_text(msg)
            else:
                return await update.message.reply_text(msg)
        
        text = "📋 **Выберите игру для записи:**\n\n"
        keyboard = []
        
        for ev in events:
            # Проверяем, записан ли пользователь
            is_joined = session.query(EventParticipant).filter_by(
                event_id=ev.id, 
                user_id=user_id
            ).first()
            
            btn_text = f"{'✅' if is_joined else '➕'} {ev.title} ({ev.event_time})"
            cb_data = f"event_leave:{ev.id}" if is_joined else f"event_join:{ev.id}"
            keyboard.append([InlineKeyboardButton(btn_text, callback_data=cb_data)])
        
        if query:
            await query.edit_message_text(
                text, 
                reply_markup=InlineKeyboardMarkup(keyboard), 
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                text, 
                reply_markup=InlineKeyboardMarkup(keyboard), 
                parse_mode='Markdown'
            )
            
    finally:
        session.close()


async def handle_event_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запись или отписка от игры"""
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
        
        existing = session.query(EventParticipant).filter_by(
            event_id=event_id, 
            user_id=user_id
        ).first()
        
        if action == "event_join":
            if existing:
                return await query.answer("Вы уже записаны.")
            
            new_part = EventParticipant(event_id=event_id, user_id=user_id)
            session.add(new_part)
            msg = f"✅ Вы записались на: {event.title}"
            logger.info(f"👤 Пользователь {user_id} записался на игру '{event.title}'")
            
        elif action == "event_leave":
            if existing:
                session.delete(existing)
                msg = f"❌ Вы отписались от: {event.title}"
                logger.info(f"👤 Пользователь {user_id} отписался от игры '{event.title}'")
            else:
                return await query.answer("Вы не были записаны.")
        
        session.commit()
        
        # Обновляем меню
        await join_menu(update, context)
        
    except Exception as e:
        session.rollback()
        logger.error(f"❌ Ошибка при записи/отписке: {e}")
        await query.message.reply_text(f"Ошибка: {e}")
    finally:
        session.close()


# ==========================================
# СИСТЕМА УВЕДОМЛЕНИЙ
# ==========================================

async def check_and_notify_events(context: ContextTypes.DEFAULT_TYPE):
    """
    Функция запускается раз в минуту планировщиком.
    
    ИСПРАВЛЕНО:
    1. Использует диапазон времени ±1 минута для надёжности
    2. Получает GROUP_ID из config.py с fallback на bot_data
    3. Добавлено логирование
    4. Обрабатывает пользователей без username
    """
    session = Session()
    
    try:
        now_msk = datetime.now(MSK_TZ)
        now_str = now_msk.strftime(DATE_FORMAT)
        
        # === ИСПРАВЛЕНО: Диапазон времени ±1 минута ===
        now_minus_1 = (now_msk - timedelta(minutes=1)).strftime(DATE_FORMAT)
        now_plus_1 = (now_msk + timedelta(minutes=1)).strftime(DATE_FORMAT)
        
        logger.debug(f"🔍 Проверка событий: {now_str} (диапазон: {now_minus_1} - {now_plus_1})")
        
        # Ищем события в диапазоне
        events = session.query(Event).filter(
            Event.event_time >= now_minus_1,
            Event.event_time <= now_plus_1,
            Event.status == 'Scheduled'
        ).all()
        
        if not events:
            return  # Нет событий для уведомления
        
        logger.info(f"🎯 Найдено {len(events)} событий для уведомления")
        
        # Получаем ID группы
        group_id = get_group_id(context)
        
        if not group_id:
            logger.error("❌ Невозможно отправить уведомление: GROUP_ID не определён")
            return
        
        for ev in events:
            try:
                # Получаем участников
                participants = session.query(EventParticipant).filter_by(event_id=ev.id).all()
                
                if not participants:
                    logger.info(f"📢 Игра '{ev.title}': нет участников для уведомления")
                    ev.status = 'Done'
                    continue
                
                # Получаем данные пользователей
                user_ids = [p.user_id for p in participants]
                users = session.query(User).filter(User.user_id.in_(user_ids)).all()
                
                # Формируем упоминания
                mentions = [format_user_mention(u) for u in users]
                tags_text = " ".join(mentions)
                
                safe_title = escape_markdown(ev.title)
                
                # Отправляем уведомление
                if tags_text:
                    message = (
                        f"📢 **НАЧАЛО ИГРЫ!**\n\n"
                        f"Мероприятие: {safe_title}\n"
                        f"Время: {ev.event_time}\n\n"
                        f"Призыв:\n{tags_text}\n\n"
                        f"Гоу ребята!"
                    )
                    
                    await context.bot.send_message(
                        chat_id=group_id, 
                        text=message, 
                        parse_mode='Markdown'
                    )
                    
                    logger.info(f"📢 Уведомление для игры '{ev.title}' отправлено в группу {group_id}")
                
                # Меняем статус
                ev.status = 'Done'
                
            except Exception as e:
                logger.error(f"❌ Ошибка при отправке уведомления для игры '{ev.title}': {e}")
        
        session.commit()
        logger.info(f"✅ Статус {len(events)} игр обновлён на 'Done'")
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка в check_and_notify_events: {e}")
        session.rollback()
        
    finally:
        session.close()