import asyncio
import signal
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from events import check_and_notify_events

scheduler = AsyncIOScheduler()

async def wrapper_job(app):
    """Обертка для функции проверки событий"""
    await check_and_notify_events(app)

async def run_scheduler(application):
    """
    Эта функция будет выполнена как отдельная задача (task) в цикле событий.
    """
    print("🔄 Инициализация планировщика...")
    
    scheduler.add_job(
        wrapper_job, 
        trigger=IntervalTrigger(minutes=1), 
        args=(application,)
    )
    scheduler.start()
    print("📅 Планировщик запущен и работает.")
    
    # Создаем событие завершения
    stop_event = asyncio.Event()
    
    # Хук для корректной остановки при Ctrl+C
    def signal_handler():
        print("\n⏳ Получен сигнал остановки, завершаем работу планировщика...")
        stop_event.set()
    
    # Привязываем SIGINT (Ctrl+C) и SIGTERM к нашему хендлеру
    # Важно: loop.add_signal_handler работает только в главном потоке, но bot.run_polling запускается в нем.
    # Здесь мы просто ждем.
    
    try:
        await stop_event.wait()
    except asyncio.CancelledError:
        print("🛑 Планировщик остановлен принудительно.")
    finally:
        print("🛑 Выключаем планировщик...")
        scheduler.shutdown()
        print("✅ Планировщик выключен.")

def start_scheduler(application):
    """
    Эта функция вызывается в main.py ДО start_polling.
    Мы создаем asyncio.Task, но используем стандартную библиотеку asyncio.
    """
    loop = asyncio.get_event_loop()
    loop.create_task(run_scheduler(application))