#!/bin/bash

echo "🧹 Запуск очистки старых данных..."

# Удаляем медиа-файлы старше 30 дней
if [ -d "data/media" ]; then
    find data/media/ -type f -mtime +30 -delete 2>/dev/null
    echo "✅ Старые медиа удалены"
fi

# Запускаем SQLite очистку
if [ -f "data/app.db" ]; then
    # Удаляем записи старше 30 дней
    sqlite3 data/app.db "DELETE FROM saved_messages WHERE saved_at < datetime('now', '-30 days') AND is_deleted = 0;"
    sqlite3 data/app.db "VACUUM;"
    echo "✅ База данных очищена и сжата"
fi

echo "✅ Очистка завершена!"