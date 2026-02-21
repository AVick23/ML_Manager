#!/usr/bin/env python3
"""
Скрипт для ручного обновления базы данных.
Делает резервную копию, проверяет наличие всех необходимых полей и таблиц,
и при необходимости обновляет структуру БД.
"""
import os
import sys
import sqlite3
import shutil
from datetime import datetime
from typing import List, Tuple

# Настройка путей
DB_NAME = "bot_users.db"  # измените, если у вас другое имя
BACKUP_DIR = "backups"


def print_header(text: str):
    """Красивый вывод заголовка"""
    print("\n" + "=" * 60)
    print(f" {text}")
    print("=" * 60)


def print_step(text: str):
    """Вывод шага"""
    print(f"➡️  {text}")


def print_success(text: str):
    """Вывод успеха"""
    print(f"✅ {text}")


def print_warning(text: str):
    """Вывод предупреждения"""
    print(f"⚠️  {text}")


def print_error(text: str):
    """Вывод ошибки"""
    print(f"❌ {text}")


def create_backup() -> Tuple[bool, str]:
    """
    Создаёт резервную копию базы данных.
    Возвращает (успех, путь_к_копии_или_сообщение)
    """
    print_step("Создание резервной копии...")
    
    if not os.path.exists(DB_NAME):
        return False, f"Файл базы данных {DB_NAME} не найден"
    
    # Создаём папку для бэкапов, если её нет
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)
        print(f"   Создана папка для бэкапов: {BACKUP_DIR}")
    
    # Формируем имя файла с датой и временем
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = os.path.join(BACKUP_DIR, f"bot_users_backup_{timestamp}.db")
    
    try:
        shutil.copy2(DB_NAME, backup_file)
        print_success(f"Резервная копия создана: {backup_file}")
        
        # Проверяем размер файла
        size = os.path.getsize(backup_file)
        print(f"   Размер: {size} байт")
        
        return True, backup_file
    except Exception as e:
        return False, str(e)


def get_table_info(cursor) -> dict:
    """
    Получает информацию о всех таблицах и их колонках.
    Возвращает словарь {таблица: [колонки]}
    """
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    
    table_info = {}
    for table in tables:
        table_name = table[0]
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = cursor.fetchall()
        table_info[table_name] = [col[1] for col in columns]  # имена колонок
    
    return table_info


def check_table_exists(cursor, table_name: str) -> bool:
    """Проверяет, существует ли таблица"""
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,)
    )
    return cursor.fetchone() is not None


def check_column_exists(cursor, table_name: str, column_name: str) -> bool:
    """Проверяет, существует ли колонка в таблице"""
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = cursor.fetchall()
    return any(col[1] == column_name for col in columns)


def add_column(cursor, table_name: str, column_name: str, column_def: str):
    """Добавляет колонку в таблицу"""
    try:
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_def}")
        print_success(f"Добавлена колонка {column_name} в таблицу {table_name}")
        return True
    except Exception as e:
        print_error(f"Не удалось добавить колонку {column_name}: {e}")
        return False


def create_table(cursor, table_name: str, create_sql: str):
    """Создаёт таблицу, если её нет"""
    try:
        cursor.execute(create_sql)
        print_success(f"Создана таблица {table_name}")
        return True
    except Exception as e:
        print_error(f"Не удалось создать таблицу {table_name}: {e}")
        return False


def check_database() -> Tuple[bool, List[str]]:
    """
    Проверяет структуру базы данных.
    Возвращает (нужны_ли_изменения, список_изменений)
    """
    print_step("Проверка структуры базы данных...")
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    changes_needed = False
    changes_list = []
    
    # === ПРОВЕРКА ТАБЛИЦ И КОЛОНОК ===
    
    # 1. Проверяем таблицу events (колонка status)
    if check_table_exists(cursor, "events"):
        if not check_column_exists(cursor, "events", "status"):
            changes_needed = True
            changes_list.append("➕ Добавить колонку status в таблицу events")
    else:
        print_warning("Таблица events не найдена. Она будет создана при первом запуске бота.")
    
    # 2. Проверяем таблицу event_matches
    if not check_table_exists(cursor, "event_matches"):
        changes_needed = True
        changes_list.append("➕ Создать таблицу event_matches")
    
    # 3. Проверяем таблицу match_participants
    if not check_table_exists(cursor, "match_participants"):
        changes_needed = True
        changes_list.append("➕ Создать таблицу match_participants")
    
    # 4. Проверяем таблицу role_ratings
    if not check_table_exists(cursor, "role_ratings"):
        changes_needed = True
        changes_list.append("➕ Создать таблицу role_ratings")
    
    # 5. Проверяем индексы (опционально)
    cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
    existing_indexes = [idx[0] for idx in cursor.fetchall()]
    
    needed_indexes = [
        "idx_match_participants_match_id",
        "idx_match_participants_user_id",
        "idx_role_ratings_user_id",
        "idx_role_ratings_match_participant_id"
    ]
    
    for idx in needed_indexes:
        if idx not in existing_indexes:
            changes_needed = True
            changes_list.append(f"➕ Создать индекс {idx}")
    
    conn.close()
    
    return changes_needed, changes_list


def apply_updates():
    """Применяет все необходимые обновления"""
    print_step("Применение обновлений...")
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    try:
        # 1. Добавляем колонку status в events
        if check_table_exists(cursor, "events"):
            if not check_column_exists(cursor, "events", "status"):
                add_column(cursor, "events", "status", "TEXT DEFAULT 'active'")
                # Обновляем существующие записи
                cursor.execute("UPDATE events SET status = 'active' WHERE status IS NULL")
                print("   Установлен статус 'active' для существующих событий")
        
        # 2. Создаём таблицу event_matches
        if not check_table_exists(cursor, "event_matches"):
            create_table(cursor, "event_matches", """
                CREATE TABLE event_matches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (event_id) REFERENCES events (id) ON DELETE CASCADE
                )
            """)
        
        # 3. Создаём таблицу match_participants
        if not check_table_exists(cursor, "match_participants"):
            create_table(cursor, "match_participants", """
                CREATE TABLE match_participants (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    match_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    team TEXT CHECK(team IN ('red', 'blue', 'spectator')),
                    role_played TEXT,
                    played BOOLEAN DEFAULT 1,
                    FOREIGN KEY (match_id) REFERENCES event_matches (id) ON DELETE CASCADE,
                    FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
                )
            """)
        
        # 4. Создаём таблицу role_ratings
        if not check_table_exists(cursor, "role_ratings"):
            create_table(cursor, "role_ratings", """
                CREATE TABLE role_ratings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    match_participant_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    rating INTEGER CHECK(rating >= 1 AND rating <= 5),
                    comment TEXT,
                    rated_by INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (match_participant_id) REFERENCES match_participants (id) ON DELETE CASCADE,
                    FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE,
                    FOREIGN KEY (rated_by) REFERENCES users (user_id) ON DELETE SET NULL
                )
            """)
        
        # 5. Создаём индексы
        indexes = [
            ("idx_match_participants_match_id", 
             "CREATE INDEX IF NOT EXISTS idx_match_participants_match_id ON match_participants(match_id)"),
            ("idx_match_participants_user_id",
             "CREATE INDEX IF NOT EXISTS idx_match_participants_user_id ON match_participants(user_id)"),
            ("idx_role_ratings_user_id",
             "CREATE INDEX IF NOT EXISTS idx_role_ratings_user_id ON role_ratings(user_id)"),
            ("idx_role_ratings_match_participant_id",
             "CREATE INDEX IF NOT EXISTS idx_role_ratings_match_participant_id ON role_ratings(match_participant_id)")
        ]
        
        for idx_name, idx_sql in indexes:
            cursor.execute(idx_sql)
            print_success(f"Индекс {idx_name} создан/проверен")
        
        # Сохраняем изменения
        conn.commit()
        print_success("Все обновления успешно применены!")
        
    except Exception as e:
        conn.rollback()
        print_error(f"Ошибка при применении обновлений: {e}")
        raise
    finally:
        conn.close()


def main():
    """Главная функция"""
    print_header("🔄 ОБНОВЛЕНИЕ БАЗЫ ДАННЫХ ML MANAGER BOT")
    
    # Проверяем наличие файла БД
    if not os.path.exists(DB_NAME):
        print_warning(f"Файл базы данных {DB_NAME} не найден.")
        response = input("Создать новую базу данных? (y/n): ").lower()
        if response == 'y':
            # Создаём пустую БД через db.py
            print_step("Создание новой базы данных...")
            try:
                from db import Session
                session = Session()
                session.close()
                print_success("Новая база данных создана")
            except Exception as e:
                print_error(f"Не удалось создать базу данных: {e}")
                return
        else:
            print("Выход.")
            return
    
    # Создаём резервную копию
    backup_success, backup_result = create_backup()
    if not backup_success:
        print_error(f"Не удалось создать резервную копию: {backup_result}")
        response = input("Продолжить без резервной копии? (y/n): ").lower()
        if response != 'y':
            print("Выход.")
            return
    
    # Проверяем структуру БД
    changes_needed, changes_list = check_database()
    
    if not changes_needed:
        print_success("База данных уже имеет актуальную структуру!")
        print("\nВсе необходимые таблицы и колонки присутствуют.")
        return
    
    # Показываем, что будет изменено
    print("\n🔧 Требуются следующие изменения:")
    for change in changes_list:
        print(f"   {change}")
    
    # Запрашиваем подтверждение
    print()
    response = input("Применить эти изменения? (y/n): ").lower()
    if response != 'y':
        print("❌ Операция отменена пользователем.")
        return
    
    # Применяем обновления
    try:
        apply_updates()
        print_success("Обновление базы данных завершено успешно!")
        print("\n📊 Теперь можно запускать бота с новым функционалом.")
    except Exception as e:
        print_error(f"Ошибка при обновлении: {e}")
        print("\n⚠️  Восстановите базу данных из резервной копии:")
        if backup_success:
            print(f"   {backup_result}")


if __name__ == "__main__":
    main()