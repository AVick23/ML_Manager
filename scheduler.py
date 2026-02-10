import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from events import check_and_notify_events

scheduler = AsyncIOScheduler()

def start_scheduler(application):
    """
    Добавляет проверку событий в цикл выполнения бота.
    """
    # Создаем задачу (coroutine), которая запустит планировщик.
    # application.create_task добавит её в цикл бота.
    async def run_and_start_scheduler():
        print("🔄 Инициализация планировщика...")
        scheduler.add_job(
            check_and_notify_events,
            trigger=IntervalTrigger(minutes=1), 
            args=(application,)
        )
        scheduler.start()
        print("📅 Планировщик запущен и работает.")
        
        # Ждем завершения (чтобы планировщик не "похерился", пока бот работает)
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            print("🛑 Остановка планировщика по сигналу...")
            scheduler.shutdown()

    application.create_task(run_and_start_scheduler())