"""
Файл конфигурации бота.
Все настройки вынесены в отдельный файл для удобства управления.
"""
import os
import logging
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# === ЛОГИРОВАНИЕ ===
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# === ОСНОВНЫЕ НАСТРОЙКИ ===

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN не найден в .env файле!")

# Список ID администраторов (через запятую в .env)
# === АДМИНЫ ===

ADMIN_IDS = [
    int(uid.strip()) 
    for uid in os.getenv("ADMIN_IDS", "").split(",") 
    if uid.strip()
]

def is_user_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


# ID группы для уведомлений (обязательный параметр)
# Пример: GROUP_ID=-100XXXXXXXXXX
GROUP_ID = int(os.getenv("GROUP_ID", "0"))
if not GROUP_ID:
    logger.warning("⚠️ GROUP_ID не указан в .env! Будет использован автоопределение группы.")

# === НАСТРОЙКИ БАЗЫ ДАННЫХ ===

DB_NAME = os.getenv("DB_NAME", "bot_users.db")

# === НАСТРОЙКИ ПЛАНИРОВЩИКА ===

SCHEDULER_INTERVAL_MINUTES = int(os.getenv("SCHEDULER_INTERVAL_MINUTES", "1"))

# === ЛОГИРОВАНИЕ НАСТРОЕК ПРИ СТАРТЕ ===

def log_config():
    """Выводит текущую конфигурацию при запуске бота"""
    logger.info("=" * 50)
    logger.info("📋 КОНФИГУРАЦИЯ БОТА:")
    logger.info(f"  • ADMIN_IDS: {ADMIN_IDS}")
    logger.info(f"  • GROUP_ID: {GROUP_ID if GROUP_ID else 'Автоопределение'}")
    logger.info(f"  • DB_NAME: {DB_NAME}")
    logger.info(f"  • SCHEDULER_INTERVAL: {SCHEDULER_INTERVAL_MINUTES} мин.")
    logger.info("=" * 50)
