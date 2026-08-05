#!/bin/bash

# Создаем папку для бэкапов
BACKUP_DIR="/backups"
mkdir -p $BACKUP_DIR

# Дата
DATE=$(date +%Y%m%d_%H%M%S)

echo "🔄 Создание бэкапа $DATE..."

# Бэкап БД
if [ -f "data/app.db" ]; then
    cp data/app.db $BACKUP_DIR/app_$DATE.db
    gzip -f $BACKUP_DIR/app_$DATE.db
    echo "✅ БД сжата: app_$DATE.db.gz"
else
    echo "⚠️ Файл БД не найден"
fi

# Бэкап медиа (только если есть файлы)
if [ -d "data/media" ] && [ "$(ls -A data/media)" ]; then
    tar -czf $BACKUP_DIR/media_$DATE.tar.gz data/media/ 2>/dev/null
    echo "✅ Медиа сжаты: media_$DATE.tar.gz"
else
    echo "ℹ️ Медиа-файлы не найдены"
fi

# Удаляем бэкапы старше 7 дней
find $BACKUP_DIR -name "*.gz" -mtime +7 -delete 2>/dev/null
find $BACKUP_DIR -name "*.tar.gz" -mtime +7 -delete 2>/dev/null

echo "✅ Бэкап завершен!"

# Выводим список файлов
ls -lh $BACKUP_DIR/ | tail -5