import sqlite3
import os

DB_PATH = "data/app.db"

if not os.path.exists(DB_PATH):
    print(f"❌ База данных не найдена: {DB_PATH}")
    exit(1)

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

try:
    # Проверяем, есть ли колонка user_id в таблице todos
    cursor.execute("PRAGMA table_info(todos)")
    columns = [col[1] for col in cursor.fetchall()]
    
    if "user_id" not in columns:
        print("➕ Добавляем колонку user_id в таблицу todos...")
        cursor.execute("ALTER TABLE todos ADD COLUMN user_id BIGINT")
        print("✅ Колонка user_id добавлена!")
        
        # Создаем индекс
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_todos_user_id ON todos(user_id)")
        print("✅ Индекс создан!")
    else:
        print("✅ Колонка user_id уже существует в таблице todos")
    
    conn.commit()
    print("✅ Готово!")
    
except sqlite3.OperationalError as e:
    if "no such table" in str(e):
        print("⚠️ Таблица todos не существует. Создаем...")
        cursor.execute("""
            CREATE TABLE todos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id BIGINT NOT NULL,
                text TEXT NOT NULL,
                is_done BOOLEAN DEFAULT 0,
                deadline DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_todos_user_id ON todos(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_todos_is_done ON todos(is_done)")
        conn.commit()
        print("✅ Таблица todos создана!")
    else:
        print(f"❌ Ошибка: {e}")

conn.close()