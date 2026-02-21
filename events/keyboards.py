"""
keyboards.py
Генерация клавиатур (UI) для модуля событий.
"""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from datetime import datetime, timedelta

from .utils import DATE_FORMAT, MSK_TZ
import state

# ==========================================
# Клавиатуры списка событий
# ==========================================

def get_events_list_kb(events, is_admin: bool) -> InlineKeyboardMarkup:
    """Клавиатура списка событий (Главная страница модуля)"""
    keyboard = []
    
    if events:
        for ev in events:
            ev_time = datetime.strptime(ev.event_time, DATE_FORMAT)
            time_str = ev_time.strftime("%d.%m %H:%M")
            btn_text = f"🗓 {ev.title} • {time_str}"
            keyboard.append([
                InlineKeyboardButton(btn_text, callback_data=f"evt_detail:{ev.id}")
            ])
    
    # Админ-функция: Создать игру
    if is_admin:
        keyboard.append([
            InlineKeyboardButton("➕ Создать новую игру", callback_data="crm_create_event")
        ])
    
    keyboard.append([InlineKeyboardButton("🏠 В главное меню", callback_data=state.CD_BACK_TO_MENU)])
    
    return InlineKeyboardMarkup(keyboard)

# ==========================================
# Клавиатура деталировки события
# ==========================================

def get_event_detail_kb(event_id: int, is_joined: bool, is_admin: bool, 
                        event_status: str, has_lineup: bool = False) -> InlineKeyboardMarkup:
    """Клавиатура просмотра конкретного события"""
    keyboard = []
    
    # Если событие завершено – только кнопка назад
    if event_status == 'completed':
        keyboard.append([InlineKeyboardButton("⬅️ К списку", callback_data="back_to_evt_list")])
        return InlineKeyboardMarkup(keyboard)
    
    # Кнопка записи/отписки (доступна всегда, пока ивент не завершён)
    if is_joined:
        keyboard.append([
            InlineKeyboardButton("❌ Отписаться", callback_data=f"event_leave:{event_id}")
        ])
    else:
        keyboard.append([
            InlineKeyboardButton("✅ Записаться", callback_data=f"event_join:{event_id}")
        ])
    
    # Админские кнопки
    if is_admin:
        # Этап: можно делать микс (событие активно и нет зафиксированного состава)
        if event_status == 'active' and not has_lineup:
            keyboard.append([InlineKeyboardButton("🎲 Умный микс", callback_data=f"event_mix:{event_id}")])
        
        # Этап: состав зафиксирован, можно оценивать и завершать
        # Показываем кнопки оценивания и завершения, если состав зафиксирован и событие не завершено
        if has_lineup and event_status != 'completed':
            keyboard.append([InlineKeyboardButton("📝 Оценить игру", callback_data=f"event_rate:{event_id}")])
            keyboard.append([InlineKeyboardButton("✅ Завершить ивент", callback_data=f"event_complete:{event_id}")])
        
        # Кнопки редактирования и удаления (доступны всегда, пока ивент не завершён)
        if event_status != 'completed':
            admin_row = [
                InlineKeyboardButton("✏️ Редактировать", callback_data=f"evt_edit:{event_id}"),
                InlineKeyboardButton("🗑 Удалить", callback_data=f"evt_del:{event_id}")
            ]
            keyboard.append(admin_row)
    
    keyboard.append([InlineKeyboardButton("⬅️ К списку", callback_data="back_to_evt_list")])
    
    return InlineKeyboardMarkup(keyboard)

# ==========================================
# Клавиатуры создания события (Визуальный календарь)
# ==========================================

def get_create_date_kb() -> InlineKeyboardMarkup:
    """Выбор даты (на неделю вперед)"""
    keyboard = []
    now = datetime.now(MSK_TZ)
    
    for i in range(0, 8):
        event_date = now + timedelta(days=i)
        day_name = event_date.strftime("%d %b (%a)")
        keyboard.append([
            InlineKeyboardButton(day_name, callback_data=f"evt_day:{i}")
        ])
    
    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="cancel_event")])
    return InlineKeyboardMarkup(keyboard)

def get_create_hour_kb() -> InlineKeyboardMarkup:
    """Выбор часа (сетка 4x6)"""
    keyboard = []
    row = []
    for i in range(0, 24):
        row.append(InlineKeyboardButton(f"{i:02d}", callback_data=f"evt_hour:{i}"))
        if len(row) == 4:
            keyboard.append(row)
            row = []
    if row: keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("⬅ Назад", callback_data="evt_back_day")])
    return InlineKeyboardMarkup(keyboard)

def get_create_minute_kb(selected_hour: int) -> InlineKeyboardMarkup:
    """Выбор минут (шаг 15 мин)"""
    keyboard = [
        [
            InlineKeyboardButton("00", callback_data="evt_min:00"),
            InlineKeyboardButton("15", callback_data="evt_min:15"),
            InlineKeyboardButton("30", callback_data="evt_min:30"),
            InlineKeyboardButton("45", callback_data="evt_min:45")
        ],
        [InlineKeyboardButton("⬅ Назад", callback_data="evt_back_hour")]
    ]
    return InlineKeyboardMarkup(keyboard)