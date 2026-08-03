from aiogram import Router
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from src.db.repositories.user_repository import UserRepository

router = Router()


@router.message(Command("start"))
async def start_command(message: Message):
    """Обработчик команды /start"""
    user = await UserRepository.get_by_id(message.from_user.id)
    
    welcome_text = f"""
🌟 <b>Добро пожаловать в Mnemora!</b>

Я ваш персональный ассистент для Telegram. Вот что я умею:

📝 <b>SAVE MODE</b>
Сохраняю удаленные и отредактированные сообщения, а также медиафайлы.

🤖 <b>AI Помощник</b>
Делаю выжимки чатов (/summary), нахожу задачи (/todos), создаю напоминания (/remind).

⚡ <b>Dot команды</b>
.mute - заглушить чат
.info - информация о пользователе
.repeat - повторить сообщение

📌 <b>Быстрые команды:</b>
/savemode on/off - включить/выключить сохранение
/search текст - поиск по сохраненным сообщениям
/help - все команды

<b>Ваш статус:</b>
✅ Аккаунт активен
✅ SAVE MODE: {'включен' if user.savemode_enabled else 'выключен'}
"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📖 Все команды", callback_data="show_help")],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings")]
    ])
    
    await message.answer(welcome_text, reply_markup=keyboard, parse_mode="HTML")


@router.message(Command("help"))
async def help_command(message: Message):
    """Показать все команды"""
    help_text = """
📚 <b>Все команды Mnemora</b>

<b>📝 SAVE MODE:</b>
/savemode on/off - включить/выключить сохранение
/savemode_settings - настройки сохранения
/deleted - последние удаленные сообщения
/edits - последние правки
/media - последние сохраненные медиа
/search текст - поиск по базе

<b>🤖 AI Функции:</b>
/summary чат - выжимка последних сообщений
/catchup чат - где вы остановились
/todos - список задач
/remind текст - создать напоминание
/digest now - дайджест чатов
/autoreply on/off - автоответчик

<b>⚡ Dot команды (в чате):</b>
.mute - заглушить чат
.unmute - включить чат
.info - информация о пользователе
.type текст - отправить с typing
.repeat n текст - повторить n раз
.love - отправить анимацию

<b>👤 Профиль:</b>
/profile - ваш профиль
/settings - настройки
"""
    await message.answer(help_text, parse_mode="HTML")