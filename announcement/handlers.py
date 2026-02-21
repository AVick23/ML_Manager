"""
Обработчики для объявлений.
"""
import html
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from config import ADMIN_IDS, logger
from db import get_all_users
from events.utils import get_group_id
import state

# Состояние для ожидания текста объявления
ANNOUNCE_STATE = "awaiting_announce_text"


async def announce_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Вход в режим создания объявления"""
    query = update.callback_query
    await query.answer()

    if query.from_user.id not in ADMIN_IDS:
        await query.edit_message_text("❌ Нет прав.")
        return

    context.user_data["announce_state"] = ANNOUNCE_STATE
    await query.edit_message_text(
        "📢 <b>Создание объявления</b>\n\n"
        "Введите текст объявления (можно использовать HTML):\n"
        "(например, <b>жирный</b>, <i>курсив</i>, <a href='ссылка'>ссылка</a>)\n\n"
        "Это сообщение будет отправлено в группу с упоминанием всех пользователей бота."
    )


async def receive_announce_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение текста объявления и показ предпросмотра"""
    if context.user_data.get("announce_state") != ANNOUNCE_STATE:
        return

    text = update.message.text.strip()
    if not text:
        await update.message.reply_text("❌ Текст не может быть пустым.")
        return

    context.user_data["announce_text"] = text
    context.user_data.pop("announce_state", None)  # выходим из режима ввода

    # Клавиатура для подтверждения
    keyboard = [
        [
            InlineKeyboardButton("✅ Отправить", callback_data="announce_confirm"),
            InlineKeyboardButton("✏️ Редактировать", callback_data="announce_edit"),
        ],
        [InlineKeyboardButton("❌ Отмена", callback_data="announce_cancel")],
    ]

    await update.message.reply_text(
        f"📄 <b>Предпросмотр:</b>\n\n{text}\n\nОтправить это объявление в группу?",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )


async def announce_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подтверждение отправки объявления"""
    query = update.callback_query
    await query.answer()

    text = context.user_data.get("announce_text")
    if not text:
        await query.edit_message_text("❌ Ошибка: текст объявления утерян. Начните заново.")
        return

    group_id = get_group_id(context)
    if not group_id:
        await query.edit_message_text("❌ Не удалось определить группу для отправки.")
        return

    # Получаем всех пользователей из базы
    users = await get_all_users()
    if not users:
        await query.edit_message_text("❌ В базе данных нет пользователей для упоминания.")
        return

    # Формируем список упоминаний
    mentions = []
    for u in users:
        if u.username:
            mentions.append(f"@{u.username}")
        else:
            name = html.escape(u.first_name or "Игрок")
            mentions.append(f'<a href="tg://user?id={u.user_id}">{name}</a>')

    # Отправляем само объявление
    try:
        await context.bot.send_message(chat_id=group_id, text=text, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Ошибка отправки объявления: {e}")
        await query.edit_message_text("❌ Не удалось отправить объявление. Проверьте формат HTML.")
        return

    # Отправляем упоминания частями (по 5, чтобы не превысить лимит)
    chunk_size = 5
    for i in range(0, len(mentions), chunk_size):
        chunk = mentions[i:i+chunk_size]
        msg = " ".join(chunk)
        try:
            await context.bot.send_message(chat_id=group_id, text=msg, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Ошибка отправки упоминаний: {e}")
            # Продолжаем, не прерываем

    logger.info(f"📢 Администратор {query.from_user.id} отправил объявление в группу {group_id}")

    # Очищаем данные и возвращаемся в меню настроек
    context.user_data.clear()
    await query.edit_message_text(
        "✅ Объявление успешно отправлено в группу!",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅ Назад в настройки", callback_data=state.CD_MENU_SETTINGS)]
        ])
    )


async def announce_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Возврат к редактированию текста"""
    query = update.callback_query
    await query.answer()
    context.user_data["announce_state"] = ANNOUNCE_STATE
    await query.edit_message_text(
        "📢 Введите новый текст объявления:"
    )


async def announce_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена создания объявления"""
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    await query.edit_message_text(
        "❌ Создание объявления отменено.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅ Назад в настройки", callback_data=state.CD_MENU_SETTINGS)]
        ])
    )