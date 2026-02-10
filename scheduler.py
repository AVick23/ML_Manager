import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from events import check_and_notify_events

scheduler = AsyncIOScheduler()

def start_scheduler(application):
    """
    Добавляет планировщик в пост-инициализацию бота.
    Это гарантирует, что цикл событий уже запущен.
    """
    async def run_and_start_scheduler():
        print("🔄 Инициализация планировщика...")
        
        # Добавляем задачу, которая будет работать раз в минуту
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

    # Используем post_init, чтобы запустить планировщик сразу после старта цикла бота
    application.post_init = lambda app: asyncio.create_task(run_and_start_scheduler())