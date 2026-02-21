"""
Модуль профиля игрока.
"""
from telegram import Update
from telegram.ext import ContextTypes

from config import ADMIN_IDS, logger
from db import User, ROLE_NAMES, ROLE_TO_MODEL, Session, get_user_statistics


async def _get_user_profile_text(user_id: int, fallback_name: str) -> str:
    """
    Генерирует текст профиля по ID пользователя.
    """
    session = Session()
    try:
        db_user = session.query(User).filter_by(user_id=user_id).first()

        if not db_user:
            return (
                f"❓ Пользователь {fallback_name} не найден в базе данных.\n"
                f"Возможно, он еще не писал в группе с ботом."
            )

        # Собираем роли
        roles_list = []
        id_ml_list = []

        for role_key, Model in ROLE_TO_MODEL.items():
            role_entry = session.query(Model).filter_by(user_id=user_id).first()
            if role_entry:
                roles_list.append(f"🔹 {ROLE_NAMES[role_key]}")
                id_ml_list.append(f"{ROLE_NAMES[role_key]}: {role_entry.id_ml}")

        if not roles_list:
            role_text = "🔹 Нет ролей"
        else:
            role_text = "\n".join(roles_list)

        id_text = "\n".join(id_ml_list) if id_ml_list else "Не указан"

        is_admin = "Да" if user_id in ADMIN_IDS else "Нет"

        # Получаем статистику
        stats = await get_user_statistics(user_id)  # асинхронная обёртка

        stats_lines = []
        if stats['played_matches'] > 0:
            stats_lines.append(f"📊 <b>Статистика:</b>")
            stats_lines.append(f"• Сыграно матчей: {stats['played_matches']}")
            if stats['avg_rating']:
                stats_lines.append(f"• Средняя оценка: {stats['avg_rating']}")
            if stats['spectator_count']:
                stats_lines.append(f"• Зрителем: {stats['spectator_count']} раз")
            if stats['role_stats']:
                stats_lines.append("\n<b>Оценки по ролям:</b>")
                for role, data in stats['role_stats'].items():
                    role_name = ROLE_NAMES.get(role, role.capitalize()) if role != 'unknown' else 'Без роли'
                    stats_lines.append(f"  {role_name}: {data['avg']} (оценок: {data['count']})")
        else:
            stats_lines.append("📊 Статистики пока нет.")

        text = (
            f"👤 <b>Профиль игрока</b>\n\n"
            f"🏷 Имя: {db_user.first_name} {db_user.last_name or ''}\n"
            f"🔗 Ник: @{db_user.username if db_user.username else 'скрыт'}\n"
            f"🆔 ID TG: {db_user.user_id}\n"
            f"👑 Админ: {is_admin}\n\n"
            f"⚔️ <b>Роли:</b>\n{role_text}\n\n"
            f"🎮 <b>Игровые ID:</b>\n{id_text}\n\n"
            f"{chr(10).join(stats_lines)}"
        )
        return text

    finally:
        session.close()


async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Команда /me. Доступна всем (в ЛС и в группе).
    Показывает профиль того, кто вызвал команду.
    """
    user = update.effective_user
    text = await _get_user_profile_text(user.id, user.first_name)
    await update.message.reply_text(text, parse_mode="HTML")


async def who_is_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Реакция на сообщение "Кто" (или "кто") в ответ на сообщение пользователя.
    Работает только в группах.
    """
    if update.effective_chat.type not in ["group", "supergroup"]:
        return

    if not update.message or not update.message.reply_to_message:
        return

    if not update.message.text or update.message.text.strip().lower() != "кто":
        return

    target_user = update.message.reply_to_message.from_user

    if target_user.id == context.bot.id:
        await update.message.reply_text("Я всего лишь бот 🤖")
        return

    text = await _get_user_profile_text(target_user.id, target_user.first_name)
    await update.message.reply_text(text, parse_mode="HTML")