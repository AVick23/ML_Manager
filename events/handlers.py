"""
handlers.py
Обработчики событий. Используют HTML-форматирование.
"""
import html
import random
from datetime import datetime, timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from db import (
    Session, Event, EventParticipant, User,
    EventMatch, MatchParticipant, RoleRating,
    ROLE_TO_MODEL, ROLE_LIST
)
from config import ADMIN_IDS, logger
import state

from events.utils import (
    get_group_id, save_user_from_tg, get_event_by_id,
    get_upcoming_events, get_event_participants, is_user_participant,
    format_user_mention, DATE_FORMAT, MSK_TZ, get_user_role
)
from events.keyboards import (
    get_events_list_kb, get_event_detail_kb,
    get_create_date_kb, get_create_hour_kb, get_create_minute_kb
)


# ==========================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ ФОРМАТИРОВАНИЯ
# ==========================================

def format_user_mention_from_tg(tg_user):
    """Создает упоминание пользователя из объекта Telegram User"""
    name = html.escape(tg_user.first_name)
    if tg_user.username:
        return f"@{tg_user.username}"
    else:
        return f"<a href='tg://user?id={tg_user.id}'>{name}</a>"


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
    """Показывает детали события с актуальным списком участников"""
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

        # Проверяем, есть ли уже зафиксированный состав
        has_lineup = session.query(EventMatch).filter_by(event_id=event_id).first() is not None

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

        reply_markup = get_event_detail_kb(event_id, is_joined, is_admin, event.status, has_lineup)

        await query.edit_message_text(
            "\n".join(lines),
            reply_markup=reply_markup,
            parse_mode="HTML"
        )

    finally:
        session.close()


async def handle_event_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает запись/отписку от события"""
    query = update.callback_query
    await query.answer()

    action, event_id_str = query.data.split(":")
    event_id = int(event_id_str)
    user_id = query.from_user.id
    tg_user = query.from_user

    session = Session()
    try:
        event = get_event_by_id(session, event_id)
        if not event:
            return await query.answer("Событие было удалено.", show_alert=True)

        # Нельзя записываться/отписываться, если ивент завершён
        if event.status == 'completed':
            return await query.answer("Ивент уже завершён.", show_alert=True)

        existing = session.query(EventParticipant).filter_by(
            event_id=event_id, user_id=user_id
        ).first()

        action_text = ""
        participants_count = 0

        if action == "event_join":
            if existing:
                return await query.answer("Вы уже записаны!")

            session.add(EventParticipant(event_id=event_id, user_id=user_id))
            await save_user_from_tg(tg_user)

            participants_count = session.query(EventParticipant).filter_by(event_id=event_id).count()
            logger.info(f"✅ User {user_id} joined event {event_id}")

            await send_private_confirmation(context, tg_user, event, "join", participants_count)
            await notify_group_about_join(context, event, tg_user)

            action_text = f"✅ Вы записаны! Всего участников: {participants_count}"

        elif action == "event_leave":
            if existing:
                session.delete(existing)
                participants_count = session.query(EventParticipant).filter_by(event_id=event_id).count()
                logger.info(f"❌ User {user_id} left event {event_id}")

                await send_private_confirmation(context, tg_user, event, "leave", participants_count)
                await notify_group_about_leave(context, event, tg_user)

                action_text = f"❌ Вы отписались. Осталось участников: {participants_count}"
            else:
                return await query.answer("Вы не были записаны.")

        session.commit()
        await query.answer(action_text)

        # Обновляем карточку
        query.data = f"evt_detail:{event_id}"
        await show_event_detail(update, context)

    except Exception as e:
        session.rollback()
        logger.error(f"Event action error: {e}")
        await query.answer("Ошибка обработки.", show_alert=True)
    finally:
        session.close()


async def send_private_confirmation(context, tg_user, event, action, participants_count):
    """Отправляет подтверждение пользователю в личные сообщения"""
    safe_title = html.escape(event.title)

    if action == "join":
        text = (
            f"✅ <b>Вы успешно записались на игру!</b>\n\n"
            f"🎯 {safe_title}\n"
            f"🕒 {event.event_time} (МСК)\n"
            f"👥 Всего участников: {participants_count}\n\n"
            f"📢 Уведомление о начале игры придёт в группу.\n"
            f"Удачной игры! ⚔️"
        )
    else:
        text = (
            f"❌ <b>Вы отписались от игры</b>\n\n"
            f"🎯 {safe_title}\n"
            f"🕒 {event.event_time} (МСК)\n"
            f"👥 Осталось участников: {participants_count}\n\n"
            f"Жаль, что не получится сыграть. В следующий раз обязательно присоединяйтесь! 👋"
        )

    try:
        await context.bot.send_message(chat_id=tg_user.id, text=text, parse_mode="HTML")
        logger.info(f"📨 Private confirmation sent to {tg_user.id} for {action}")
    except Exception as e:
        logger.warning(f"Failed to send private confirmation to {tg_user.id}: {e}")


async def notify_group_about_join(context, event, tg_user):
    group_id = get_group_id(context)
    if not group_id:
        return

    safe_title = html.escape(event.title)
    mention = format_user_mention_from_tg(tg_user)

    session = Session()
    try:
        participants_count = session.query(EventParticipant).filter_by(event_id=event.id).count()
    finally:
        session.close()

    text = (
        f"📢 <b>НОВЫЙ УЧАСТНИК!</b>\n\n"
        f"{mention} записался(лась) на игру\n"
        f"🎯 <b>{safe_title}</b>\n"
        f"🕒 {event.event_time} (МСК)\n"
        f"👥 Теперь участников: {participants_count}"
    )
    try:
        await context.bot.send_message(chat_id=group_id, text=text, parse_mode="HTML")
    except Exception as e:
        logger.warning(f"Group notification error (join): {e}")


async def notify_group_about_leave(context, event, tg_user):
    group_id = get_group_id(context)
    if not group_id:
        return

    safe_title = html.escape(event.title)
    mention = format_user_mention_from_tg(tg_user)

    session = Session()
    try:
        participants_count = session.query(EventParticipant).filter_by(event_id=event.id).count()
    finally:
        session.close()

    text = (
        f"👋 <b>УЧАСТНИК ОТПИСАЛСЯ</b>\n\n"
        f"{mention} отписался(лась) от игры\n"
        f"🎯 <b>{safe_title}</b>\n"
        f"👥 Осталось участников: {participants_count}"
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
    context.user_data.pop("editing_event_id", None)

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

            group_id = get_group_id(context)
            if group_id:
                try:
                    group_text = (
                        f"🕒 <b>Время игры изменено!</b>\n\n"
                        f"🎯 {safe_title}\n"
                        f"Старое время: {old_time}\n"
                        f"Новое время: {event_time_str}\n\n"
                        f"Изменено администратором."
                    )
                    await context.bot.send_message(chat_id=group_id, text=group_text, parse_mode="HTML")
                except Exception as e:
                    logger.warning(f"Group notification error (time edit): {e}")

            context.user_data.clear()
            return
        else:
            # Создание нового события
            new_event = Event(title=title, event_time=event_time_str, status='active')
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
        context.user_data["event_title"] = title
    finally:
        session.close()

    await _render_date_selection(update, context, title)


async def receive_edited_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        old_title_safe = html.escape(old_title)

        await update.message.reply_text(
            f"✅ <b>Название изменено</b>\n\n"
            f"Старое: {old_title_safe}\n"
            f"Новое: {safe_new}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 К событию", callback_data=f"evt_detail:{event_id}")]
            ]),
            parse_mode="HTML"
        )
        logger.info(f"✏️ Admin {user_id} renamed event {event_id}: '{old_title}' -> '{new_title}'")

        group_id = get_group_id(context)
        if group_id:
            try:
                group_text = (
                    f"📝 <b>Название игры изменено!</b>\n\n"
                    f"Старое название: {old_title_safe}\n"
                    f"Новое название: {safe_new}\n\n"
                    f"Изменено администратором."
                )
                await context.bot.send_message(chat_id=group_id, text=group_text, parse_mode="HTML")
            except Exception as e:
                logger.warning(f"Group notification error (title edit): {e}")

    except Exception as e:
        session.rollback()
        logger.error(f"Error renaming event: {e}")
        await update.message.reply_text("❌ Ошибка при сохранении.")
    finally:
        session.close()

    context.user_data.clear()


async def cancel_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    event_id = context.user_data.get("editing_event_id")
    context.user_data.clear()
    if event_id:
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
            event_title = event.title
            safe_title = html.escape(event_title)

            # Удаляем всё связанное
            session.query(EventParticipant).filter_by(event_id=event_id).delete()
            # Удаляем матчи и их участников (каскадно? но проще почистить отдельно)
            matches = session.query(EventMatch).filter_by(event_id=event_id).all()
            for m in matches:
                session.query(MatchParticipant).filter_by(match_id=m.id).delete()
                session.delete(m)
            session.delete(event)
            session.commit()
            await query.answer("Игра удалена.")

            group_id = get_group_id(context)
            if group_id:
                try:
                    group_text = (
                        f"🗑 <b>Игра отменена</b>\n\n"
                        f"🎯 {safe_title}\n"
                        f"Игра была удалена администратором."
                    )
                    await context.bot.send_message(chat_id=group_id, text=group_text, parse_mode="HTML")
                except Exception as e:
                    logger.warning(f"Group notification error (delete): {e}")

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
# УМНЫЙ МИКС (с учётом ролей)
# ==========================================

async def smart_mix(users, session):
    """
    Распределяет участников по командам, стараясь учесть их роли.
    Возвращает словарь: {'red': [...], 'blue': [...], 'spectators': [...]}
    """
    if len(users) < 2:
        return {'red': [], 'blue': [], 'spectators': []}

    # Получаем роли пользователей
    user_roles = {}
    for u in users:
        role = get_user_role(session, u.user_id)
        if role:
            user_roles[u.user_id] = role

    # Группируем игроков по ролям
    role_buckets = {role: [] for role in ROLE_LIST}
    no_role = []
    for u in users:
        role = user_roles.get(u.user_id)
        if role and role in role_buckets:
            role_buckets[role].append(u)
        else:
            no_role.append(u)

    # Перемешиваем каждую группу
    for role in role_buckets:
        random.shuffle(role_buckets[role])
    random.shuffle(no_role)

    red = []
    blue = []
    # Распределяем по ролям: по одному в каждую команду, чередуя
    # Для каждой роли по очереди добавляем игроков в red и blue
    # Пока есть игроки в role_buckets[role]
    # Но чтобы не создавать дисбаланс, будем заполнять по кругу
    # Сначала соберём всех игроков с ролями в общий список с пометкой роли
    players_with_roles = []
    for role in ROLE_LIST:
        for player in role_buckets[role]:
            players_with_roles.append((role, player))

    # Перемешаем этот список, чтобы разнообразить порядок
    random.shuffle(players_with_roles)

    # Теперь распределяем по командам, стараясь сохранить баланс ролей
    # Для простоты будем просто по очереди добавлять в red и blue
    for i, (role, player) in enumerate(players_with_roles):
        if i % 2 == 0:
            if len(red) < 5:
                red.append(player)
            else:
                blue.append(player)
        else:
            if len(blue) < 5:
                blue.append(player)
            else:
                red.append(player)

    # Теперь заполняем оставшиеся места случайными игроками без роли
    for player in no_role:
        if len(red) < 5:
            red.append(player)
        elif len(blue) < 5:
            blue.append(player)
        else:
            break

    # Если после заполнения остались игроки (больше 10), они становятся зрителями
    in_teams = set(red + blue)
    spectators = [u for u in users if u not in in_teams]

    return {'red': red[:5], 'blue': blue[:5], 'spectators': spectators}


def format_mix_result(event_title, mix_result):
    """Форматирует результат микса в HTML"""
    lines = [f"🎯 <b>{html.escape(event_title)}</b>\n"]

    if mix_result['red']:
        lines.append("\n🔴 <b>КОМАНДА RED</b>")
        for u in mix_result['red']:
            name = f"@{u.username}" if u.username else u.first_name
            lines.append(f"• {html.escape(name)}")

    if mix_result['blue']:
        lines.append("\n🔵 <b>КОМАНДА BLUE</b>")
        for u in mix_result['blue']:
            name = f"@{u.username}" if u.username else u.first_name
            lines.append(f"• {html.escape(name)}")

    if mix_result['spectators']:
        lines.append("\n👀 <b>ЗРИТЕЛИ</b>")
        for u in mix_result['spectators']:
            name = f"@{u.username}" if u.username else u.first_name
            lines.append(f"• {html.escape(name)}")

    return "\n".join(lines)


async def event_mix(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запуск умного микса"""
    query = update.callback_query
    await query.answer()
    event_id = int(query.data.split(':')[1])

    session = Session()
    try:
        event = get_event_by_id(session, event_id)
        if not event:
            await query.edit_message_text("❌ Событие не найдено.")
            return

        # Проверяем, что событие активно и нет зафиксированного состава
        if event.status != 'active':
            await query.answer("Микс доступен только для активных событий.", show_alert=True)
            return

        has_lineup = session.query(EventMatch).filter_by(event_id=event_id).first() is not None
        if has_lineup:
            await query.answer("Состав уже зафиксирован. Нельзя перемешать.", show_alert=True)
            return

        participants = get_event_participants(session, event_id)
        user_ids = [p.user_id for p in participants]
        users = session.query(User).filter(User.user_id.in_(user_ids)).all()

        if len(users) < 2:
            await query.answer("❌ Слишком мало участников для микса (нужно хотя бы 2).", show_alert=True)
            return

        # Сохраняем в user_data для повторного микса
        context.user_data['mix_users'] = [u.user_id for u in users]
        context.user_data['mix_event_id'] = event_id

        mix_result = await smart_mix(users, session)
        text = format_mix_result(event.title, mix_result)

        keyboard = [
            [InlineKeyboardButton("🔄 Перемешать ещё", callback_data=f"event_mix_again:{event_id}")],
            [InlineKeyboardButton("✅ Зафиксировать состав", callback_data=f"event_fix_lineup:{event_id}")],
            [InlineKeyboardButton("❌ Отмена", callback_data=f"evt_detail:{event_id}")]
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

    except Exception as e:
        logger.error(f"Event mix error: {e}")
        await query.answer("❌ Ошибка при выполнении микса.", show_alert=True)
    finally:
        session.close()


async def event_mix_again(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Повторный микс"""
    query = update.callback_query
    await query.answer()
    event_id = int(query.data.split(':')[1])

    if context.user_data.get('mix_event_id') != event_id:
        await query.answer("❌ Данные устарели, начните заново.", show_alert=True)
        return

    user_ids = context.user_data['mix_users']
    session = Session()
    try:
        event = get_event_by_id(session, event_id)
        if not event:
            await query.edit_message_text("❌ Событие не найдено.")
            return

        users = session.query(User).filter(User.user_id.in_(user_ids)).all()
        mix_result = await smart_mix(users, session)
        text = format_mix_result(event.title, mix_result)

        keyboard = [
            [InlineKeyboardButton("🔄 Перемешать ещё", callback_data=f"event_mix_again:{event_id}")],
            [InlineKeyboardButton("✅ Зафиксировать состав", callback_data=f"event_fix_lineup:{event_id}")],
            [InlineKeyboardButton("❌ Отмена", callback_data=f"evt_detail:{event_id}")]
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

    except Exception as e:
        logger.error(f"Event mix again error: {e}")
        await query.answer("❌ Ошибка при повторном миксе.", show_alert=True)
    finally:
        session.close()


async def event_fix_lineup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Фиксация состава после микса"""
    query = update.callback_query
    await query.answer()
    event_id = int(query.data.split(':')[1])

    if context.user_data.get('mix_event_id') != event_id:
        await query.answer("❌ Данные утеряны, повторите микс.", show_alert=True)
        return

    user_ids = context.user_data['mix_users']
    session = Session()
    try:
        event = get_event_by_id(session, event_id)
        if not event:
            await query.edit_message_text("❌ Событие не найдено.")
            return

        # Проверяем, не зафиксирован ли уже состав
        existing_match = session.query(EventMatch).filter_by(event_id=event_id).first()
        if existing_match:
            await query.answer("Состав для этого события уже зафиксирован.", show_alert=True)
            return

        users = session.query(User).filter(User.user_id.in_(user_ids)).all()
        mix_result = await smart_mix(users, session)

        # Создаём запись матча
        event_match = EventMatch(event_id=event_id)
        session.add(event_match)
        session.flush()  # получаем id

        # Добавляем участников матча
        for team_name, team_users in mix_result.items():
            for u in team_users:
                role_played = get_user_role(session, u.user_id)  # какая роль была у игрока
                mp = MatchParticipant(
                    match_id=event_match.id,
                    user_id=u.user_id,
                    team=team_name,
                    role_played=role_played,
                    played=(team_name != 'spectators')
                )
                session.add(mp)

        # Обновляем статус события
        event.status = 'lineup_fixed'
        session.commit()

        # Отправляем финальный состав в группу
        group_id = get_group_id(context)
        if group_id:
            text = f"📢 <b>Состав на игру зафиксирован!</b>\n\n" + format_mix_result(event.title, mix_result)
            await context.bot.send_message(chat_id=group_id, text=text, parse_mode="HTML")

        # Возвращаемся в карточку с обновлёнными кнопками
        query.data = f"evt_detail:{event_id}"
        await show_event_detail(update, context)

    except Exception as e:
        session.rollback()
        logger.error(f"Fix lineup error: {e}")
        await query.answer("❌ Ошибка фиксации.", show_alert=True)
    finally:
        session.close()
        context.user_data.pop('mix_event_id', None)
        context.user_data.pop('mix_users', None)


# ==========================================
# ОЦЕНИВАНИЕ ИГРЫ
# ==========================================

async def start_rating(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало оценивания игроков"""
    query = update.callback_query
    await query.answer()
    event_id = int(query.data.split(':')[1])

    session = Session()
    try:
        event_match = session.query(EventMatch).filter_by(event_id=event_id).first()
        if not event_match:
            await query.edit_message_text("❌ Нет зафиксированного матча для этого ивента.")
            return

        # Берём участников, которые были в командах (играли)
        participants = session.query(MatchParticipant).filter(
            MatchParticipant.match_id == event_match.id,
            MatchParticipant.team.in_(['red', 'blue'])
        ).all()

        if not participants:
            await query.edit_message_text("❌ В матче нет игроков для оценки.")
            return

        # Сохраняем в user_data список id участников матча
        rating_list = [p.id for p in participants]
        context.user_data['rating_match_id'] = event_match.id
        context.user_data['rating_participants'] = rating_list
        context.user_data['rating_index'] = 0
        context.user_data['rating_event_id'] = event_id

        await show_rating_user(update, context, event_match.id, 0)

    except Exception as e:
        logger.error(f"Start rating error: {e}")
        await query.answer("❌ Ошибка запуска оценивания.", show_alert=True)
    finally:
        session.close()


async def show_rating_user(update, context, match_id, index):
    """Показывает одного участника для оценки"""
    session = Session()
    try:
        participants = context.user_data['rating_participants']
        if index >= len(participants):
            await finish_rating(update, context, match_id)
            return

        mp_id = participants[index]
        mp = session.query(MatchParticipant).get(mp_id)
        user = session.query(User).filter_by(user_id=mp.user_id).first()
        if not user:
            # Пропускаем
            context.user_data['rating_index'] = index + 1
            await show_rating_user(update, context, match_id, index + 1)
            return

        name = f"@{user.username}" if user.username else user.first_name
        role = mp.role_played or "не указана"

        text = f"📝 Оцените игру игрока:\n\n{html.escape(name)} (роль: {role})"
        keyboard = [
            [InlineKeyboardButton("5", callback_data=f"rate_user:{mp_id}:5"),
             InlineKeyboardButton("4", callback_data=f"rate_user:{mp_id}:4"),
             InlineKeyboardButton("3", callback_data=f"rate_user:{mp_id}:3")],
            [InlineKeyboardButton("2", callback_data=f"rate_user:{mp_id}:2"),
             InlineKeyboardButton("1", callback_data=f"rate_user:{mp_id}:1"),
             InlineKeyboardButton("❌ Не играл", callback_data=f"rate_user_not_played:{mp_id}")],
            [InlineKeyboardButton("⏭ Пропустить", callback_data=f"rate_skip:{match_id}"),
             InlineKeyboardButton("🏁 Завершить", callback_data=f"rate_finish:{match_id}")]
        ]
        await (update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
               if update.callback_query else update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML"))
    except Exception as e:
        logger.error(f"Show rating user error: {e}")
        await update.callback_query.answer("❌ Ошибка отображения.", show_alert=True)
    finally:
        session.close()


async def rate_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split(':')
    mp_id = int(data[1])
    rating = int(data[2])

    session = Session()
    try:
        mp = session.query(MatchParticipant).get(mp_id)
        if not mp:
            await query.answer("Ошибка: участник не найден", show_alert=True)
            return

        # Проверяем, не оценивал ли уже этот админ данного участника в этом матче
        existing = session.query(RoleRating).filter_by(
            match_participant_id=mp_id,
            rated_by=query.from_user.id
        ).first()
        if existing:
            await query.answer("Вы уже оценили этого игрока в этом матче.", show_alert=True)
            return

        rating_entry = RoleRating(
            match_participant_id=mp_id,
            user_id=mp.user_id,
            rating=rating,
            rated_by=query.from_user.id
        )
        session.add(rating_entry)
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"Rating error: {e}")
        await query.answer("❌ Ошибка сохранения оценки.", show_alert=True)
    finally:
        session.close()

    await rate_next(update, context)


async def rate_user_not_played(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    mp_id = int(query.data.split(':')[1])

    session = Session()
    try:
        mp = session.query(MatchParticipant).get(mp_id)
        if mp:
            mp.played = False
            session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"Rate not played error: {e}")
    finally:
        session.close()

    await rate_next(update, context)


async def rate_next(update: Update, context: ContextTypes.DEFAULT_TYPE):
    index = context.user_data.get('rating_index', 0) + 1
    context.user_data['rating_index'] = index
    match_id = context.user_data['rating_match_id']
    await show_rating_user(update, context, match_id, index)


async def rate_skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await rate_next(update, context)


async def rate_finish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    match_id = context.user_data['rating_match_id']
    await finish_rating(update, context, match_id)


async def finish_rating(update, context, match_id):
    event_id = context.user_data.get('rating_event_id')
    context.user_data.clear()

    if update.callback_query:
        await update.callback_query.edit_message_text(
            "✅ Оценивание завершено. Спасибо!",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 К событию", callback_data=f"evt_detail:{event_id}")]
            ])
        )
    else:
        await update.message.reply_text("✅ Оценивание завершено.")


# ==========================================
# ЗАВЕРШЕНИЕ ИВЕНТА
# ==========================================

async def complete_event(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    event_id = int(query.data.split(':')[1])

    session = Session()
    try:
        event = get_event_by_id(session, event_id)
        if not event:
            await query.edit_message_text("❌ Событие не найдено.")
            return
        if event.status == 'completed':
            await query.answer("Ивент уже завершён.", show_alert=True)
            return
    finally:
        session.close()

    keyboard = [
        [InlineKeyboardButton("✅ Да, завершить", callback_data=f"confirm_complete:{event_id}")],
        [InlineKeyboardButton("❌ Нет", callback_data=f"evt_detail:{event_id}")]
    ]
    await query.edit_message_text(
        "❓ Вы уверены, что хотите завершить ивент? Это действие нельзя отменить.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def confirm_complete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    event_id = int(query.data.split(':')[1])

    session = Session()
    try:
        event = session.query(Event).get(event_id)
        if event:
            event.status = 'completed'
            session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"Confirm complete error: {e}")
        await query.answer("❌ Ошибка завершения.", show_alert=True)
        return
    finally:
        session.close()

    query.data = f"evt_detail:{event_id}"
    await show_event_detail(update, context)


# ==========================================
# ПЛАНИРОВЩИК
# ==========================================

async def check_and_notify_events(context: ContextTypes.DEFAULT_TYPE):
    session = Session()
    try:
        now_msk = datetime.now(MSK_TZ)
        now_str = now_msk.strftime(DATE_FORMAT)
        window = (now_msk + timedelta(minutes=1)).strftime(DATE_FORMAT)

        # Ищем события, которые должны начаться в ближайшую минуту и ещё не завершены
        events = session.query(Event).filter(
            Event.event_time >= now_str,
            Event.event_time <= window,
            Event.status != 'completed'
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

            # Не меняем статус, оставляем как есть

    except Exception as e:
        logger.error(f"Scheduler error: {e}")
        session.rollback()
    finally:
        session.close()