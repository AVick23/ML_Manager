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
        print("📅 Planner is running.")
    else:
        print("📅 Planner already started.")

def start_scheduler(application):
    """
    Запускает планировщик в фоне.
    """
    # Получаем текущий цикл (он уже создан ботом к этому моменту)
    loop = asyncio.get_running_loop()
    
    # Запускаем асинхронную функцию через ensure_future
    asyncio.ensure_future(run_and_start_scheduler(application))