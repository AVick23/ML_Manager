# scheduler.py

import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from events import check_and_notify_events

scheduler = AsyncIOScheduler()

async def run_and_start_scheduler(application):
    """
    Запуска планировщика.
    """
    print("🔄 Инициализация планировщика...")
    
    scheduler.add_job(
        check_and_notify_events,
        trigger=IntervalTrigger(minutes=1), 
        args=(application,)
    )
    
    if scheduler.state:
        scheduler.start()
        print("📅 Планировщик запущен и работает.")
    else:
        print("📅 Планировщик уже был запущен.")

def start_scheduler(application):
    """
    Запускает планировщика в фоне.
    """
    # Используем ensure_future для совместимости с Python 3.10
    asyncio.ensure_future(run_and_start_scheduler(application))