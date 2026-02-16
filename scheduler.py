"""
Планировщик задач для уведомлений о событиях.
Использует APScheduler для периодического запуска проверки событий.
"""
import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.schedulers.base import STATE_RUNNING

from config import logger, SCHEDULER_INTERVAL_MINUTES
from events.handlers import check_and_notify_events

# Инициализация планировщика
scheduler = AsyncIOScheduler()


async def run_and_start_scheduler(application):
    """
    Запуск планировщика с обработкой ошибок.
    
    ИСПРАВЛЕНО: Убрана некорректная проверка scheduler.state.
    Теперь вызываем start() напрямую с обработкой исключений.
    """
    logger.info("🔄 Инициализация планировщика...")
    
    try:
        # Добавляем задачу проверки событий
        scheduler.add_job(
            check_and_notify_events,
            trigger=IntervalTrigger(minutes=SCHEDULER_INTERVAL_MINUTES),
            args=(application,),
            id='check_events',
            name='Проверка событий',
            replace_existing=True  # Заменяет задачу, если она уже существует
        )
        
        # Проверяем, не запущен ли уже планировщик
        if scheduler.state != STATE_RUNNING:
            scheduler.start()
            logger.info(f"📅 Планировщик запущен. Интервал: {SCHEDULER_INTERVAL_MINUTES} мин.")
        else:
            logger.info("📅 Планировщик уже работает.")
            
    except Exception as e:
        logger.error(f"❌ Ошибка запуска планировщика: {e}")
        # Пробуем запустить ещё раз через 5 секунд
        await asyncio.sleep(5)
        try:
            scheduler.start()
            logger.info("📅 Планировщик запущен (повторная попытка).")
        except Exception as e2:
            logger.error(f"❌ Критическая ошибка планировщика: {e2}")


def stop_scheduler():
    """
    Корректная остановка планировщика.
    """
    if scheduler.state == STATE_RUNNING:
        scheduler.shutdown(wait=False)
        logger.info("📅 Планировщик остановлен.")


def start_scheduler(application):
    """
    Запускает планировщик в фоновом режиме.
    Совместимость с Python 3.10+.
    """
    asyncio.ensure_future(run_and_start_scheduler(application))


def get_scheduler_status() -> str:
    """
    Возвращает текущий статус планировщика.
    
    Returns:
        str: 'running', 'stopped', или 'paused'
    """
    states = {0: 'stopped', 1: 'running', 2: 'paused'}
    return states.get(scheduler.state, 'unknown')
