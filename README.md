# Telegram Message Archiver

Бот для Telegram, который сохраняет **удалённые** и **отредактированные** сообщения из **личных чатов**, используя Telegram Business API.

## Возможности

- Отслеживание удалённых и изменённых сообщений  
- Хранение текста и медиафайлов в базе данных SQLite  
- Автоматическая отправка уведомлений администратору  
- Работа через Business Connections  
- Поддержка самоуничтожающихся сообщений  
- Не требует сессии пользователя — только Telegram Premium и подключение бота

## Установка

1. Клонируй репозиторий:
   ```bash
   git clone https://github.com/FoxCoderGit/telegram-message-archiver.git
   cd telegram-message-archiver 
   ```
   
2. Установи зависимости:
```bash
pip install -r requirements.txt
```

3. Отредактируй переменные в начале monitor_message.py:
```Python
BUSINESS_BOT_TOKEN = "your_bot_token"
MASTER_CHAT_ID = your_telegram_id
BUSINESS_OWNER_ID = your_telegram_id
```

4. Запусти бота:
```bash
python3 monitor_message.py
```


## Структура проекта

- `monitor_message.py` — основной скрипт бота  
- `messages.db` — база данных SQLite (создаётся автоматически)  
- `downloads/` — временная папка для медиа (очищается после отправки)  
- `bot.log` — лог ошибок и событий

## Требования

- Python 3.7+  
- Telegram Premium-аккаунт  
- Бизнес-подключение Telegram Bot API


## Лицензия

Этот проект распространяется под лицензией [MIT](LICENSE).