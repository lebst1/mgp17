#!/bin/bash

# Проверяем, запущен ли контейнер
CONTAINER_NAME="safesaverx_bot"

if docker ps --format '{{.Names}}' | grep -q "^$CONTAINER_NAME$"; then
    echo "✅ Бот работает"
    
    # Проверяем, нет ли ошибок в логах за последние 5 минут
    ERROR_COUNT=$(docker logs --tail 100 $CONTAINER_NAME 2>&1 | grep -i "error" | wc -l)
    if [ $ERROR_COUNT -gt 0 ]; then
        echo "⚠️ Найдено $ERROR_COUNT ошибок в логах"
        # Можно отправить уведомление в Telegram
    fi
else
    echo "❌ Бот НЕ РАБОТАЕТ!"
    # Попытка перезапуска
    docker compose up -d
    echo "🔄 Попытка перезапуска..."
fi

# Проверяем свободное место на диске
FREE_SPACE=$(df -h / | awk 'NR==2 {print $5}')
echo "💾 Свободно: $FREE_SPACE"