import os
import time
import requests
import logging
import sqlite3
from concurrent.futures import ThreadPoolExecutor

# Загружаем переменные окружения
BUSINESS_BOT_TOKEN = "8221355803:AAFm_q6ZDARKvgWWXI6jZdNB92X6s413APU"
MASTER_CHAT_ID = 7307366104
BUSINESS_OWNER_ID = 7307366104

BASE_URL = f"https://api.telegram.org/bot{BUSINESS_BOT_TOKEN}"
SAVE_DIR = "downloads"
os.makedirs(SAVE_DIR, exist_ok=True)

# Логирование
logging.basicConfig(
    filename="bot.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# Подключение к БД
conn = sqlite3.connect("messages.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS messages (
    bc_id INTEGER,
    msg_id INTEGER,
    user_id INTEGER,
    username TEXT,
    fullname TEXT,
    text TEXT,
    files TEXT,
    is_temporary BOOLEAN DEFAULT 0,
    PRIMARY KEY (bc_id, msg_id)
)
""")
conn.commit()

def download_file(file_id, file_name):
    """Скачать файл с правильным расширением"""
    try:
        file_info = requests.get(f"{BASE_URL}/getFile?file_id={file_id}", timeout=15).json()
        if file_info["ok"]:
            file_path = file_info["result"]["file_path"]
            file_ext = os.path.splitext(file_path)[-1] or ".bin"
            save_path = os.path.join(SAVE_DIR, file_name + file_ext)

            file_resp = requests.get(f"https://api.telegram.org/file/bot{BUSINESS_BOT_TOKEN}/{file_path}", timeout=15)
            if file_resp.status_code == 200:
                with open(save_path, "wb") as f:
                    f.write(file_resp.content)
                return save_path
    except requests.exceptions.RequestException as e:
        logging.error(f"Ошибка загрузки файла: {e}")
    return None

def extract_files(message):
    """
    Сохранить все файлы в сообщении, включая самоуничтожающиеся фото/видео,
    а также обрабатывать неизвестные типы медиа.
    """
    file_paths = []
    media_types = ["photo", "video", "voice", "audio", "document", "sticker", "animation", "video_note"]
    # Ключи, которые уже обработаны
    processed_keys = set(media_types)
    processed_keys.update(["message_id", "business_connection_id", "from", "text", "has_media_spoiler"])

    with ThreadPoolExecutor() as executor:
        futures = []
        for media in media_types:
            if media in message:
                # Для фото выбираем только последний элемент списка (наивысшее качество)
                if media == "photo" and isinstance(message[media], list):
                    items = message[media]
                    chosen_item = items[-1]
                    file_id = chosen_item["file_id"]
                    file_name = f"{media}_{message['message_id']}"
                    futures.append(executor.submit(download_file, file_id, file_name))
                else:
                    items = message[media] if isinstance(message[media], list) else [message[media]]
                    for item in items:
                        file_id = item["file_id"]
                        file_name = f"{media}_{message['message_id']}"
                        futures.append(executor.submit(download_file, file_id, file_name))
        # Обработка потенциально новых типов медиа
        for key, value in message.items():
            if key not in processed_keys and isinstance(value, dict) and "file_id" in value:
                file_id = value["file_id"]
                file_name = f"{key}_{message['message_id']}"
                futures.append(executor.submit(download_file, file_id, file_name))

        for future in futures:
            result = future.result()
            if result:
                file_paths.append(result)
    return file_paths

def send_message(chat_id, text, files=[], include_files=True):
    """
    Отправить сообщение с текстом и (опционально) файлами.
    После отправки файлы удаляются с сервера.
    """
    try:
        if include_files and files:
            if len(files) == 1:
                with open(files[0], "rb") as file:
                    requests.post(
                        f"{BASE_URL}/sendDocument",
                        files={"document": file},
                        data={"chat_id": chat_id, "caption": text},
                        timeout=15
                    )
                os.remove(files[0])  # Удалить файл
            else:
                requests.post(
                    f"{BASE_URL}/sendMessage",
                    json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
                    timeout=15
                )
                for file_path in files:
                    with open(file_path, "rb") as file:
                        requests.post(
                            f"{BASE_URL}/sendDocument",
                            files={"document": file},
                            data={"chat_id": chat_id},
                            timeout=15
                        )
                    os.remove(file_path)  # Удалить файл после отправки
        else:
            requests.post(
                f"{BASE_URL}/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
                timeout=15
            )
    except requests.exceptions.RequestException as e:
        logging.error(f"Ошибка отправки сообщения: {e}")
    except OSError as e:
        logging.error(f"Ошибка удаления файла: {e}")

def format_user_info(user):
    """Форматирование имени пользователя"""
    username = user.get("username")
    user_id = user.get("id")
    full_name = (user.get("first_name", "") + " " + user.get("last_name", "")).strip()
    return f"{full_name} (@{username})" if username else f"{full_name} (ID: {user_id})"

def main():
    offset = 0
    while True:
        try:
            data = requests.get(
                f"{BASE_URL}/getUpdates",
                params={"offset": offset + 1, "timeout": 30},
                timeout=35
            ).json()
            if not data or not data.get("ok"):
                time.sleep(5)
                continue

            for update in data["result"]:
                offset = update["update_id"]

                # 1️⃣ Новое сообщение
                if "business_message" in update:
                    bm = update["business_message"]
                    bc_id = bm["business_connection_id"]
                    msg_id = bm["message_id"]
                    user = bm["from"]
                    text = bm.get("text", "")
                    author_info = format_user_info(user)
                    file_paths = extract_files(bm)
                    is_temporary = bm.get("has_media_spoiler", False)

                    cursor.execute("""
                        INSERT OR REPLACE INTO messages (bc_id, msg_id, user_id, username, fullname, text, files, is_temporary)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        bc_id,
                        msg_id,
                        user["id"],
                        user.get("username"),
                        author_info,
                        text,
                        ','.join(file_paths) if file_paths else None,
                        is_temporary
                    ))
                    conn.commit()

                    if is_temporary and file_paths:
                        send_message(
                            MASTER_CHAT_ID,
                            f"⚠️ *Самоуничтожающееся сообщение!*\n👤 {author_info}\n📄 {text or '(без текста)'}",
                            file_paths
                        )

                # 2️⃣ Изменённое сообщение
                if "edited_business_message" in update:
                    ebm = update["edited_business_message"]
                    bc_id = ebm["business_connection_id"]
                    msg_id = ebm["message_id"]
                    new_text = ebm.get("text", "")
                    user = ebm.get("from")
                    new_author_info = format_user_info(user) if user else None

                    cursor.execute("SELECT user_id, username, fullname, text, files FROM messages WHERE bc_id=? AND msg_id=?", (bc_id, msg_id))
                    data_db = cursor.fetchone()
                    if data_db:
                        old_text, stored_files = data_db[3], data_db[4]
                        if new_text.strip() == old_text.strip():
                            continue
                        file_paths = stored_files.split(',') if stored_files else []
                        notify_files = False if file_paths else True

                        if new_author_info and new_author_info != data_db[2]:
                            cursor.execute("UPDATE messages SET fullname=? WHERE bc_id=? AND msg_id=?", (new_author_info, bc_id, msg_id))
                        
                        send_message(
                            MASTER_CHAT_ID,
                            f"✏️ *Сообщение изменено!*\n👤 {new_author_info or data_db[2]}\n📄 *Было:* {old_text}\n📄 *Стало:* {new_text}",
                            file_paths,
                            include_files=notify_files
                        )
                        cursor.execute("UPDATE messages SET text=? WHERE bc_id=? AND msg_id=?", (new_text, bc_id, msg_id))
                        conn.commit()

                # 3️⃣ Удалённое сообщение
                if "deleted_business_messages" in update:
                    dbm = update["deleted_business_messages"]
                    bc_id = dbm["business_connection_id"]
                    message_ids = dbm["message_ids"]

                    for mid in message_ids:
                        cursor.execute("SELECT user_id, username, fullname, text, files FROM messages WHERE bc_id=? AND msg_id=?", (bc_id, mid))
                        data_db = cursor.fetchone()
                        if data_db:
                            file_paths = data_db[4].split(',') if data_db[4] else []
                            send_message(
                                MASTER_CHAT_ID,
                                f"❌ *Удалено!*\n👤 {data_db[2]}\n📄 {data_db[3]}",
                                file_paths
                            )
                            cursor.execute("DELETE FROM messages WHERE bc_id=? AND msg_id=?", (bc_id, mid))
                            conn.commit()

        except Exception as e:
            logging.error(f"Ошибка в основном цикле: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()