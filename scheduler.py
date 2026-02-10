import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from events import check_and_notify_events

scheduler = AsyncIOScheduler()

async def run_and_start_scheduler(application):
    """
    Запуска планировщика. Эта функция сама является асинхронной (async def),
    поэтому application.add_task корректно запустит её.
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
    Добавляем задачу планировщика в очередь бота.
    """
    # Используем application.add_task для безопасного запуска асинхронной функции.
    # application.run_polling перед запуском выполнит все post_init, поэтому
    # create_task увидит живой event loop.
    application.add_task(run_and_start_scheduler(application))