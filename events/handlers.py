"""
handlers.py
Обработчики событий. Используют HTML-форматирование.
"""
import html  # Для экранирования текста
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from datetime import datetime, timedelta

from db import Session, Event, EventParticipant, User
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

# ==========================================
# ГЛАВНОЕ МЕНЮ СОБЫТИЙ
# ==========================================

async def events_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
            text = "🗓 <b>Расписание пусто</b>\n\nНет запланированных игр. Время отдыхать!"
        else:
            text = "🗓 <b>Расписание игр</b>\nВыберите событие для деталей:"

        reply_markup = get_events_list_kb(events, is_admin)

        if query:
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode="HTML")
        else:
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="HTML")

    finally:
        session.close()


# ==========================================
# ПРОСМОТР И ДЕЙСТВИЯ
# ==========================================

async def show_event_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

        ev_time = datetime.strptime(event.event_time, DATE_FORMAT)
        time_str = ev_time.strftime("%d %b %Y, %H:%M")
        participants = get_event_participants(session, event_id)
        is_joined = is_user_participant(session, event_id, user_id)

        # Экранируем название события
        safe_title = html.escape(event.title)

        lines = [
            f"🎯 <b>{safe_title}</b>",
            f"🕒 <b>Время:</b> {time_str} (МСК)",
            f"\n-------------------"
        ]

        if not participants:
            lines.append("\n👻 <b>Участников пока нет</b>\nСтаньте первым!")
        else:
            lines.append(f"\n👥 <b>Участники ({len(participants)}):</b>")

            p_user_ids = [p.user_id for p in participants]
            users = session.query(User).filter(User.user_id.in_(p_user_ids)).all() if p_user_ids else []
            user_map = {u.user_id: u for u in users}

            for i, p in enumerate(participants, 1):
                u = user_map.get(p.user_id)
                lines.append(f"{i}. {format_user_mention(u)}")

        reply_markup = get_event_detail_kb(event_id, is_joined, is_admin)

        await query.edit_message_text(
            "\n".join(lines),
            reply_markup=reply_markup,
            parse_mode="HTML"
        )

    finally:
        session.close()


async def handle_event_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
            await query.answer("✅ Вы успешно записались!")

            # Отправляем уведомление в группу
            await notify_group_about_join(context, event, query.from_user)

        elif action == "event_leave":
            if existing:
                session.delete(existing)
                logger.info(f"❌ User {user_id} left event {event_id}")
                await query.answer("❌ Вы отписались.")

                # Отправляем уведомление в группу
                await notify_group_about_leave(context, event, query.from_user)
            else:
                return await query.answer("Вы не были записаны.")

        session.commit()

        query.data = f"evt_detail:{event_id}"
        await show_event_detail(update, context)

    except Exception as e:
        session.rollback()
        logger.error(f"Event action error: {e}")
        await query.answer("Ошибка обработки.", show_alert=True)
    finally:
        session.close()


async def notify_group_about_join(context, event, tg_user):
    """Отправляет уведомление в группу о записи на игру"""
    group_id = get_group_id(context)
    if not group_id:
        return

    safe_title = html.escape(event.title)
    mention = f"@{tg_user.username}" if tg_user.username else f'<a href="tg://user?id={tg_user.id}">{html.escape(tg_user.first_name)}</a>'

    text = (
        f"📢 <b>НОВЫЙ УЧАСТНИК!</b>\n\n"
        f"{mention} записался(лась) на игру\n"
        f"🎯 <b>{safe_title}</b>\n"
        f"🕒 {event.event_time} (МСК)"
    )

    try:
        await context.bot.send_message(chat_id=group_id, text=text, parse_mode="HTML")
    except Exception as e:
        logger.warning(f"Group notification error (join): {e}")


async def notify_group_about_leave(context, event, tg_user):
    """Отправляет уведомление в группу об отписке от игры"""
    group_id = get_group_id(context)
    if not group_id:
        return

    safe_title = html.escape(event.title)
    mention = f"@{tg_user.username}" if tg_user.username else f'<a href="tg://user?id={tg_user.id}">{html.escape(tg_user.first_name)}</a>'

    text = (
        f"👋 <b>УЧАСТНИК ОТПИСАЛСЯ</b>\n\n"
        f"{mention} отписался(лась) от игры\n"
        f"🎯 <b>{safe_title}</b>"
    )

    try:
        await context.bot.send_message(chat_id=group_id, text=text, parse_mode="HTML")
    except Exception as e:
        logger.warning(f"Group notification error (leave): {e}")


# ==========================================
# СОЗДАНИЕ (АДМИН)
# ==========================================

async def create_event_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()

    user_id = query.from_user.id if query else update.effective_user.id
    if user_id not in ADMIN_IDS:
        if query:
            return await query.answer("🔒 Только админы могут создавать игры.", show_alert=True)
        else:
            return await update.message.reply_text("🔒 Только админы могут создавать игры.")

    context.user_data["crm_state"] = "awaiting_title"
    context.user_data.pop("editing_event_id", None)  # Очищаем режим редактирования

    text = "📝 <b>Создание игры</b>\n\nВведите название события:"
    keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data="cancel_event")]]

    if query:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
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


async def _render_date_selection(update: Update, context: ContextTypes.DEFAULT_TYPE, title: str):
    """Отрисовывает выбор даты (без ответа на callback)"""
    safe_title = html.escape(title)
    text = f"📅 <b>{safe_title}</b>\n\nВыберите дату:"
    reply_markup = get_create_date_kb()
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode="HTML")
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="HTML")


async def ask_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    title = context.user_data.get('event_title', 'Игра')
    await _render_date_selection(update, context, title)


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
        editing_event_id = context.user_data.get("editing_event_id")
        if editing_event_id:
            # Режим редактирования
            event = get_event_by_id(session, editing_event_id)
            if not event:
                await query.edit_message_text("❌ Событие не найдено.")
                return
            old_time = event.event_time
            event.event_time = event_time_str
            session.commit()
            safe_title = html.escape(event.title)
            await query.edit_message_text(
                f"✅ <b>Время события изменено</b>\n\n"
                f"🎯 {safe_title}\n"
                f"Старое время: {old_time}\n"
                f"Новое время: {event_time_str}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 К событию", callback_data=f"evt_detail:{editing_event_id}")]
                ]),
                parse_mode="HTML"
            )
            logger.info(f"✏️ Admin {query.from_user.id} changed event {editing_event_id} time: {old_time} -> {event_time_str}")
            context.user_data.clear()
            return
        else:
            # Создание нового события
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

    # Если создание — отправляем уведомление в группу
    group_id = get_group_id(context)
    if group_id:
        try:
            safe_title = html.escape(title)
            notify_text = (
                f"📢 <b>НОВАЯ ИГРА!</b>\n\n"
                f"🎯 {safe_title}\n"
                f"🗓 {event_time_str} (МСК)\n\n"
                f"Откройте бота, чтобы записаться!"
            )
            await context.bot.send_message(chat_id=group_id, text=notify_text, parse_mode="HTML")
        except Exception as e:
            logger.warning(f"Notify error: {e}")

    context.user_data.clear()

    safe_title = html.escape(title)
    await query.message.reply_text(f"✅ Игра <b>{safe_title}</b> создана!", parse_mode="HTML")
    await events_menu(update, context)


# ==========================================
# РЕДАКТИРОВАНИЕ СОБЫТИЙ (АДМИН)
# ==========================================

async def edit_event_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Вход в меню редактирования события"""
    query = update.callback_query
    await query.answer()
    if query.from_user.id not in ADMIN_IDS:
        return await query.answer("🔒 Только для админов", show_alert=True)

    event_id = int(query.data.split(":")[1])
    context.user_data["editing_event_id"] = event_id

    session = Session()
    try:
        event = get_event_by_id(session, event_id)
        if not event:
            await query.edit_message_text("❌ Событие не найдено.")
            return
        safe_title = html.escape(event.title)
        text = f"✏️ <b>Редактирование события</b>\n\n<b>{safe_title}</b>\n\nВыберите, что изменить:"
    finally:
        session.close()

    keyboard = [
        [InlineKeyboardButton("📝 Изменить название", callback_data="evt_edit_title")],
        [InlineKeyboardButton("🕒 Изменить время", callback_data="evt_edit_time")],
        [InlineKeyboardButton("⬅ Назад", callback_data=f"evt_detail:{event_id}")]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


async def edit_title_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запрос нового названия"""
    query = update.callback_query
    await query.answer()
    event_id = context.user_data.get("editing_event_id")
    if not event_id:
        await query.edit_message_text("❌ Ошибка сессии. Начните заново.")
        return

    session = Session()
    try:
        event = get_event_by_id(session, event_id)
        if not event:
            await query.edit_message_text("❌ Событие не найдено.")
            return
        safe_title = html.escape(event.title)
        text = f"📝 <b>Введите новое название</b>\n\nТекущее: {safe_title}\n\n(или нажмите Отмена)"
    finally:
        session.close()

    context.user_data["state"] = "EDITING_TITLE"
    keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data="evt_edit_cancel")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


async def edit_time_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запуск выбора новой даты/времени"""
    query = update.callback_query
    await query.answer()
    event_id = context.user_data.get("editing_event_id")
    if not event_id:
        await query.edit_message_text("❌ Ошибка сессии. Начните заново.")
        return

    context.user_data["editing_field"] = "time"
    context.user_data["crm_state"] = "awaiting_date"

    session = Session()
    try:
        event = get_event_by_id(session, event_id)
        if not event:
            await query.edit_message_text("❌ Событие не найдено.")
            return
        title = event.title
    finally:
        session.close()

    # Показываем календарь без повторного answer
    await _render_date_selection(update, context, title)


async def receive_edited_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка введённого нового названия"""
    if context.user_data.get("state") != "EDITING_TITLE":
        return
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        return

    new_title = update.message.text.strip()
    if len(new_title) < 3:
        await update.message.reply_text("❌ Слишком коротко. Введите название (минимум 3 символа):")
        return

    event_id = context.user_data.get("editing_event_id")
    if not event_id:
        await update.message.reply_text("❌ Ошибка сессии. Начните заново.")
        context.user_data.clear()
        return

    session = Session()
    try:
        event = get_event_by_id(session, event_id)
        if not event:
            await update.message.reply_text("❌ Событие не найдено.")
            return

        old_title = event.title
        event.title = new_title
        session.commit()
        safe_new = html.escape(new_title)
        await update.message.reply_text(
            f"✅ <b>Название изменено</b>\n\n"
            f"Старое: {html.escape(old_title)}\n"
            f"Новое: {safe_new}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 К событию", callback_data=f"evt_detail:{event_id}")]
            ]),
            parse_mode="HTML"
        )
        logger.info(f"✏️ Admin {user_id} renamed event {event_id}: '{old_title}' -> '{new_title}'")
    except Exception as e:
        session.rollback()
        logger.error(f"Error renaming event: {e}")
        await update.message.reply_text("❌ Ошибка при сохранении.")
    finally:
        session.close()

    context.user_data.clear()


async def cancel_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена редактирования названия"""
    query = update.callback_query
    await query.answer()
    event_id = context.user_data.get("editing_event_id")
    context.user_data.clear()
    if event_id:
        # Вернуться к деталям события
        query.data = f"evt_detail:{event_id}"
        await show_event_detail(update, context)
    else:
        await events_menu(update, context)


# ==========================================
# УДАЛЕНИЕ И ОТМЕНА
# ==========================================

async def delete_event(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    if update.callback_query:
        await update.callback_query.answer()
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
# ПЛАНИРОВЩИК
# ==========================================

async def check_and_notify_events(context: ContextTypes.DEFAULT_TYPE):
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

        if not events:
            return

        group_id = get_group_id(context)
        if not group_id:
            return

        for ev in events:
            participants = get_event_participants(session, ev.id)
            user_ids = [p.user_id for p in participants]
            users = session.query(User).filter(User.user_id.in_(user_ids)).all() if user_ids else []

            notify_blocks = []
            safe_title = html.escape(ev.title)
            header = (
                f"📢 <b>ИГРА НАЧИНАЕТСЯ!</b>\n"
                f"🎯 {safe_title}\n\n"
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
                await context.bot.send_message(chat_id=group_id, text=block, parse_mode="HTML")

            ev.status = 'Done'

        session.commit()

    except Exception as e:
        logger.error(f"Scheduler error: {e}")
        session.rollback()
    finally:
        session.close()