"""
keyboards.py
Генерация клавиатур (UI) для модуля событий.
"""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from datetime import datetime, timedelta

from db import Session, User
from .utils import DATE_FORMAT, MSK_TZ, get_event_participants, format_user_mention
import state

# ==========================================
# Клавиатуры списка событий
# ==========================================

def get_events_list_kb(events, is_admin: bool) -> InlineKeyboardMarkup:
    """Клавиатура списка событий (Главная страница модуля)"""
    keyboard = []
    
    if not events:
        text = "🗓 Список пуст"
    else:
        for ev in events:
            ev_time = datetime.strptime(ev.event_time, DATE_FORMAT)
            time_str = ev_time.strftime("%d.%m %H:%M")
            # Компактный формат кнопки
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

def get_event_detail_kb(event_id: int, is_joined: bool, is_admin: bool) -> InlineKeyboardMarkup:
    """Клавиатура просмотра конкретного события"""
    keyboard = []
    
    # Основное действие
    if is_joined:
        keyboard.append([
            InlineKeyboardButton("❌ Отписаться", callback_data=f"event_leave:{event_id}")
        ])
    else:
        keyboard.append([
            InlineKeyboardButton("✅ Записаться", callback_data=f"event_join:{event_id}")
        ])
    
    # Админ-функция: Удалить
    if is_admin:
        keyboard.append([
            InlineKeyboardButton("🗑 Удалить игру", callback_data=f"evt_del:{event_id}")
        ])
    
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