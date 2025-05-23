import os
import json
import logging
import nest_asyncio
from aiogram.fsm.context import FSMContext  

nest_asyncio.apply()
import asyncio
from pathlib import Path
from typing import List, Tuple, Optional, Dict
from collections import defaultdict
import re
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.client.default import DefaultBotProperties
from dotenv import load_dotenv
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import AiogramError
import aiofiles
import html
from aiogram.enums import ParseMode
import sqlite3
from contextlib import closing
from datetime import datetime
from aiogram.types import BotCommand
from aiogram.filters import Command




# --- Настройка логов ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- Явная загрузка .env ---
env_path = Path(__file__).parent / '.env'
load_dotenv(env_path)
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("Не задан TELEGRAM_BOT_TOKEN в .env файле")

# --- Константы callback_data ---
CALLBACK_TALES = "tales"
CALLBACK_VOCABULARY = "vocabulary"
CALLBACK_GRAMMAR = "grammar"
CALLBACK_LEXICON = "lexicon"
CALLBACK_BACK_TO_MAIN = "back_to_main"
CALLBACK_BACK_TO_TALES = "back_to_tales"
CALLBACK_BACK_TO_VOCABULARY = "back_to_vocabulary"
CALLBACK_SHOW_STORY = "show_story_"
CALLBACK_SHOW_GRAMMAR = "show_grammar_"
CALLBACK_SHOW_LEXICON = "show_lexicon_"
CALLBACK_LANGUAGE_RU = "lang_ru_"
CALLBACK_LANGUAGE_KH = "lang_kh_"
CALLBACK_BACK_TO_LANGUAGE = "back_to_lang_"
CALLBACK_PLAY_AUDIO = "play_audio_"
CALLBACK_ALPHABET = "alphabet"
CALLBACK_ALPHABET_LETTERS = "alphabet_letters"
CALLBACK_ALPHABET_VOWELS = "alphabet_vowels"
CALLBACK_ALPHABET_CONSONANTS = "alphabet_consonants"
CALLBACK_TALES_PAGE_PREFIX = "tales_page_"
CALLBACK_TALES_PREV = "tales_prev"
CALLBACK_TALES_NEXT = "tales_next"

# --- Класс для работы с базой данных ---
class Database:
    def __init__(self, db_name: str = "user_progress.db"):
        self.db_name = db_name
        self._init_db()

    def _init_db(self):
        """Инициализация базы данных и создание таблиц"""
        with closing(sqlite3.connect(self.db_name)) as conn:
            cursor = conn.cursor()
            # Таблица пользователей
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    registration_date TEXT
                )
            """)
            # Таблица прогресса по сказкам
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tale_progress (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    tale_id INTEGER,
                    last_read_date TEXT,
                    read_count INTEGER DEFAULT 0,
                    completed BOOLEAN DEFAULT FALSE,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            """)
            # Таблица результатов тестов
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS test_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    tale_id INTEGER,
                    question_id INTEGER,
                    is_correct BOOLEAN,
                    answer_date TEXT,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            """)
            conn.commit()

    def add_user(self, user: types.User):
        """Добавление нового пользователя в базу данных"""
        with closing(sqlite3.connect(self.db_name)) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR IGNORE INTO users 
                (user_id, username, first_name, last_name, registration_date)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    user.id,
                    user.username,
                    user.first_name,
                    user.last_name,
                    datetime.now().isoformat()
                )
            )
            conn.commit()

    def update_tale_progress(self, user_id: int, tale_id: int) -> bool:
        """Обновление прогресса по сказке. Возвращает True, если запись была обновлена, False если создана новая"""
        with closing(sqlite3.connect(self.db_name)) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, read_count FROM tale_progress WHERE user_id = ? AND tale_id = ?",
                (user_id, tale_id)
            )
            record = cursor.fetchone()
            
            if record:
                read_count = record[1] + 1
                cursor.execute(
                    """
                    UPDATE tale_progress 
                    SET read_count = ?, last_read_date = ?
                    WHERE id = ?
                    """,
                    (read_count, datetime.now().isoformat(), record[0])
                )
                conn.commit()
                return True
            else:
                cursor.execute(
                    """
                    INSERT INTO tale_progress 
                    (user_id, tale_id, last_read_date, read_count)
                    VALUES (?, ?, ?, 1)
                    """,
                    (user_id, tale_id, datetime.now().isoformat())
                )
                conn.commit()
                return False

    def mark_tale_completed(self, user_id: int, tale_id: int):
        """Помечаем сказку как завершенную (пройден тест)"""
        with closing(sqlite3.connect(self.db_name)) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id FROM tale_progress WHERE user_id = ? AND tale_id = ?",
                (user_id, tale_id)
            )
            record = cursor.fetchone()
            if record:
                cursor.execute(
                    """
                    UPDATE tale_progress 
                    SET completed = TRUE, last_read_date = ?
                    WHERE id = ?
                    """,
                    (datetime.now().isoformat(), record[0])
                )
            else:
                cursor.execute(
                    """
                    INSERT INTO tale_progress 
                    (user_id, tale_id, last_read_date, completed)
                    VALUES (?, ?, ?, TRUE)
                    """,
                    (user_id, tale_id, datetime.now().isoformat())
                )
            conn.commit()

    def save_test_result(self, user_id: int, tale_id: int, question_id: int, is_correct: bool):
        """Сохранение результата ответа на вопрос теста"""
        with closing(sqlite3.connect(self.db_name)) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO test_results 
                (user_id, tale_id, question_id, is_correct, answer_date)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    tale_id,
                    question_id,
                    is_correct,
                    datetime.now().isoformat()
                )
            )
            conn.commit()

    def get_user_progress(self, user_id: int) -> dict:
        """Получение прогресса пользователя"""
        with closing(sqlite3.connect(self.db_name)) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    COUNT(DISTINCT tale_id) as tales_read,
                    SUM(read_count) as total_reads,
                    COUNT(DISTINCT CASE WHEN completed THEN tale_id END) as tales_completed
                FROM tale_progress
                WHERE user_id = ?
            """, (user_id,))
            stats = cursor.fetchone()
            tales_read = stats[0] if stats and stats[0] is not None else 0
            total_reads = stats[1] if stats and stats[1] is not None else 0
            tales_completed = stats[2] if stats and stats[2] is not None else 0

            cursor.execute("""
                SELECT tale_id, last_read_date, read_count, completed
                FROM tale_progress
                WHERE user_id = ?
                ORDER BY last_read_date DESC
                LIMIT 5
            """, (user_id,))
            recent_tales = cursor.fetchall()

            return {
                "tales_read": tales_read,
                "total_reads": total_reads,
                "tales_completed": tales_completed,
                "recent_tales": recent_tales
            }

# --- Загрузка сказок из JSON ---
def load_tales_from_json(json_path: str) -> dict:
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            logger.info(f"Успешно загружено {len(data['stories'])} сказок из JSON")
            return data
    except Exception as e:
        logger.error(f"Ошибка загрузки JSON: {e}")
        raise

def load_tests_from_json(json_path: str) -> dict:
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            logger.info(f"Успешно загружено {len(data['tests'])} тестов из JSON")
            return data
    except Exception as e:
        logger.error(f"Ошибка загрузки тестов JSON: {e}")
        raise

def load_phonetics():
    try:
        with open("phonetics.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Ошибка загрузки phonetics.json: {e}")
        return None

# Загружаем данные
try:
    tales_data = load_tales_from_json("fairytales.json")
except Exception as e:
    logger.critical(f"Не удалось загрузить данные: {e}")
    exit(1)

try:
    tests_data = load_tests_from_json("tests.json")
except Exception as e:
    logger.error(f"Не удалось загрузить тесты: {e}")
    tests_data = {"tests": []}

phonetics_data = load_phonetics()

















# --- Инициализация бота и диспетчера ---
bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# Инициализация базы данных
db = Database()








async def set_bot_commands(bot: Bot):
    commands = [
        BotCommand(command="/start", description="Начать работу с ботом"),
        BotCommand(command="/progress", description="Показать ваш прогресс")
    ]
    await bot.set_my_commands(commands)






# --- Вспомогательные функции ---
async def split_long_message(text: str, max_length: int = 4096) -> List[str]:
    if len(text) <= max_length:
        return [text]
    parts = []
    while text:
        part = text[:max_length]
        split_pos = part.rfind('\n') if '\n' in part else max_length
        parts.append(text[:split_pos])
        text = text[split_pos:].lstrip()
    return parts

def build_menu(buttons: List[Tuple[str, str]], 
              back_button: Optional[Tuple[str, str]] = None,
              additional_buttons: List[Tuple[str, str]] = None,
              columns: int = 1) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for text, data in buttons:
        builder.button(text=text, callback_data=data)
    if additional_buttons:
        for text, data in additional_buttons:
            builder.button(text=text, callback_data=data)
    if back_button:
        builder.button(text=back_button[0], callback_data=back_button[1])
    builder.adjust(columns, *[1]*len(additional_buttons or []), 1)
    return builder.as_markup()

# Функция для автоматического определения темы слова
def detect_theme(word: str) -> str:
    theme_mapping = {
     'животные': ['медведь', 'белка', 'лось', 'заяц', 'волк', 'кот', 'олень'],
    'природа': ['солнце', 'река', 'лес', 'дерево', 'вода', 'землянка', 'бор', 'море', 'дыра'],
    'действия': ['идти', 'бежать', 'говорить', 'видеть', 'слышать', 'жить', 'сказать', 'выйди', 'копать', 'смотреть', 'убить', 'танцевать', 'жили', 'размышлять', 'драться' , 'хвастать', 'жили вдвоём'],
    'семья': ['мать', 'отец', 'сын', 'дочь', 'брат', 'сестра', 'мужчина', 'женщина'],
    'еда': ['хлеб', 'мясо', 'рыба', 'ягода', 'вода'],
    'жильё': ['дом', 'землянка'],
    'характеристики': ['тяжело', 'большой', 'сильный', 'маленький', 'холодный', 'милый', 'друг'],
    'местоимения': ['я', 'мой', 'ты', 'твой', 'мы', 'наш', 'себе', 'ему', 'этот'],
    'речь': ['что', 'как', 'зачем', 'нет', 'не', 'пусть', 'дальше'],
    'тело': ['нос', 'ухо', 'рот'],
    'числа': ['семь', 'шесть']
    }
    word_lower = word.lower().strip()
    for theme, keywords in theme_mapping.items():
        if any(keyword in word_lower for keyword in keywords):
            return theme.capitalize()
    return "Общее"

async def send_audio_if_exists(chat_id: int, story: dict):
    """Отправляет аудиофайл, если он существует"""
    if story.get('audio') and story['audio'] != "pass":
        audio_path = Path(__file__).parent / "audio" / story['audio']
        try:
            if audio_path.exists():
                # Правильное создание InputFile
                audio_file = types.FSInputFile(audio_path)
                await bot.send_audio(
                    chat_id=chat_id,
                    audio=audio_file,
                    title=f"{story['rus_title']} | {story['han_title']}",
                    performer="Хантыйская сказка",
                    caption=f"🎧 {story['rus_title']}"
                )
                return True
        except Exception as e:
            logger.error(f"Ошибка при отправке аудио: {e}")
    return False


async def send_question(message: types.Message, question: dict, current: int, total: int):
    """Отправляет вопрос теста"""
    builder = InlineKeyboardBuilder()
    for i, variant in enumerate(question["variants"]):
        builder.button(text=variant, callback_data=f"test_answer_{question['q_id']}_{i}")
    builder.adjust(1)
    await message.answer(
        f"📝 Вопрос {current + 1}/{total}\n"
        f"{question['question']}",
        reply_markup=builder.as_markup()
    )


async def alphabet_menu_kb() -> InlineKeyboardMarkup:
    """Меню раздела алфавита"""
    buttons = [
        ("🔠 Названия букв", CALLBACK_ALPHABET_LETTERS),
        ("🔡 Гласные звуки", CALLBACK_ALPHABET_VOWELS),
        ("🔣 Согласные звуки", CALLBACK_ALPHABET_CONSONANTS)
    ]
    return build_menu(buttons, ("🔙 Назад", CALLBACK_BACK_TO_VOCABULARY), columns=1)


# --- Клавиатуры ---
async def main_menu_kb() -> InlineKeyboardMarkup:
    """Главное меню"""
    buttons = [
        ("📖 Сказки", CALLBACK_TALES),
        ("📚 Словарик", CALLBACK_VOCABULARY)#,
        #("📊 Мой прогресс", "show_progress")
    ]
    return build_menu(buttons, columns=2)


async def vocabulary_menu_kb() -> InlineKeyboardMarkup:
    """Меню словаря"""
    buttons = [
        ("📝 Общая грамматика", CALLBACK_GRAMMAR),
        ("🔤 Общая лексика", CALLBACK_LEXICON),
        ("🔡 Алфавит", CALLBACK_ALPHABET)
    ]
    return build_menu(buttons, ("🗂️ Главное меню", CALLBACK_BACK_TO_MAIN), columns=2)


async def tales_menu_kb(page: int = 0, page_size: int = 5) -> InlineKeyboardMarkup:
    """Меню сказок с пагинацией"""
    stories = tales_data['stories']
    total_pages = (len(stories) + page_size - 1) // page_size
    start_idx = page * page_size
    end_idx = start_idx + page_size
    paginated_stories = stories[start_idx:end_idx]
    buttons = [
        (story['rus_title'], f"{CALLBACK_SHOW_STORY}{story['id']}") 
        for story in paginated_stories
    ]
    navigation_buttons = []
    if page > 0:
        navigation_buttons.append(("◀️ Назад", f"{CALLBACK_TALES_PAGE_PREFIX}{page-1}"))
    if end_idx < len(stories):
        navigation_buttons.append(("Вперед ▶️", f"{CALLBACK_TALES_PAGE_PREFIX}{page+1}"))
    return build_menu(
        buttons, 
        back_button=("🗂️ Главное меню", CALLBACK_BACK_TO_MAIN),
        additional_buttons=navigation_buttons,
        columns=1
    )


async def language_menu_kb(story_id: int) -> InlineKeyboardMarkup:
    """Меню выбора языка для сказки"""
    buttons = [
        ("🇷🇺 Русский", f"{CALLBACK_LANGUAGE_RU}{story_id}"),
        ("🦦 Хантыйский", f"{CALLBACK_LANGUAGE_KH}{story_id}")
    ]
    return build_menu(buttons, ("🔙 Назад", CALLBACK_BACK_TO_TALES), columns=2)


async def story_menu_kb(story_id: int) -> InlineKeyboardMarkup:
    """Меню для конкретной сказки - кнопки только если есть данные"""
    story = next(s for s in tales_data['stories'] if s['id'] == story_id)
    buttons = []
    # Кнопка аудио (если есть файл)
    if story.get('audio') and story['audio'] != "":
        audio_path = Path(__file__).parent / "audio" / story['audio']
        if audio_path.exists():
            buttons.append(("🎧 Аудио", f"{CALLBACK_PLAY_AUDIO}{story_id}"))
    # Кнопка грамматики (если есть данные)
    if story.get('grammar') and story['grammar'].strip():
        buttons.append(("📝 Грамматика", f"{CALLBACK_SHOW_GRAMMAR}{story_id}"))
    # Кнопка лексики (если есть данные)
    if (story.get('han_words') and story.get('rus_words') and 
        len(story['han_words']) > 0 and len(story['rus_words']) > 0):
        buttons.append(("🔤 Лексика", f"{CALLBACK_SHOW_LEXICON}{story_id}"))
    # Кнопка теста (если есть тест для этой сказки)
    if any(t["fairytale_id"] == story_id for t in tests_data["tests"]):
        buttons.append(("📝 Пройти тест", f"start_test_{story_id}"))
    # Всегда добавляем кнопку смены языка
    buttons.append(("🌐 Сменить язык", f"{CALLBACK_BACK_TO_LANGUAGE}{story_id}"))
    return build_menu(buttons, ("🔙 Назад", CALLBACK_BACK_TO_TALES), columns=2)


# --- Обработчики сообщений ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """Обработчик команды /start с улучшенным персональным приветствием"""
    try:
        user = message.from_user
        name = ""
        # Формируем обращение в зависимости от доступных данных
        if user.first_name and user.last_name:
            name = f"{user.first_name} {user.last_name}"
        elif user.first_name:
            name = user.first_name
        elif user.last_name:
            name = user.last_name
        elif user.username:
            name = f"@{user.username}"
        else:
            name = "друг"
        # Регистрируем пользователя в базе данных
        db.add_user(user)
        # Форматируем текст с учетом возможного HTML-форматирования
        welcome_text = (
            f"🌟 Вўща, <b>{html.escape(name)}</b> 🐾\n \n"
            "Добро пожаловать в чат-бот для изучения казымского диалекта хантыйского языка!\n\n"
            "<b>Здесь ты сможешь:</b>\n"
            "   • 📖 Прочитать сказки на хантыйском и русском\n"
            "   • 📚 Изучить слова и грамматику\n"
            "   • 🔤 Познакомиться с алфавитом и фонетикой\n\n"
            "<b>Выбери интересующий раздел:</b>"
        )
        await message.answer(
            welcome_text,
            reply_markup=await main_menu_kb(),
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.error(f"Ошибка в cmd_start: {e}", exc_info=True)
        try:
            await message.answer(
                "🌟 Добро пожаловать в бота для изучения хантыйского языка!\n"
                "Пожалуйста, выбери раздел:",
                reply_markup=await main_menu_kb()
            )
        except Exception as fallback_error:
            logger.critical(f"Критическая ошибка в cmd_start: {fallback_error}")


@dp.message(Command("progress"))
async def cmd_progress(message: types.Message):
    """Показывает прогресс пользователя"""
    try:
        progress = db.get_user_progress(message.from_user.id)
        # Формируем текст с прогрессом
        progress_text = (
            f"📊 <b>Ваш прогресс:</b>\n"
            f"📖 Прочитано сказок: {progress['tales_read']}\n"
            f"🔁 Всего прочтений: {progress['total_reads']}\n"
            f"✅ Завершено тестов: {progress['tales_completed']}\n"
            f"<b>Недавно прочитанные:</b>\n"
        )
        # Добавляем информацию о последних прочитанных сказках
        if progress["recent_tales"]:
            for tale in progress["recent_tales"]:
                tale_id, last_read, read_count, completed = tale
                story = next(s for s in tales_data['stories'] if s['id'] == tale_id)
                status = "✅" if completed else "📖"
                progress_text += (
                    f"{status} <b>{story['rus_title']}</b> - "
                    f"прочитано {read_count} раз(а)\n"
                )
        else:
            progress_text += "Вы еще не читали сказки\n"

        await message.answer(
            progress_text,
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.error(f"Ошибка в cmd_progress: {e}", exc_info=True)
        await message.answer("⚠️ Произошла ошибка при загрузке вашего прогресса")


# --- Обработчики сказок ---
@dp.callback_query(F.data == CALLBACK_TALES)
async def handle_tales_first(callback: types.CallbackQuery):
    """Первый вход в меню сказок — создает новое сообщение"""
    try:
        page = 0
        await callback.message.answer(
            "📖 Выбери сказку на этой страничке или нажми <b>Вперёд ▶️</b>, чтобы увидеть другие:",
            reply_markup=await tales_menu_kb(page=page)
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в handle_tales_first: {e}")
        await callback.answer("⚠️ Ошибка при загрузке меню", show_alert=True)


@dp.callback_query(F.data.startswith(CALLBACK_TALES_PAGE_PREFIX))
async def handle_tales_pagination(callback: types.CallbackQuery):
    """Обработчик пагинации в меню сказок — редактирует текущее сообщение"""
    try:
        page = int(callback.data.replace(CALLBACK_TALES_PAGE_PREFIX, ""))
        await callback.message.edit_text(
            "📖 Выбери сказку или воспользуйся кнопками <b>Вперёд ▶️</b> и <b>◀️ Назад</b> для перехода по меню:",
            reply_markup=await tales_menu_kb(page=page)
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в handle_tales_pagination: {e}")
        await callback.answer("⚠️ Ошибка при загрузке меню", show_alert=True)


@dp.callback_query(F.data.startswith(CALLBACK_SHOW_STORY))
async def handle_show_story(callback: types.CallbackQuery):
    """Выбор языка для сказки"""
    try:
        story_id = int(callback.data.replace(CALLBACK_SHOW_STORY, ""))
        story = next(s for s in tales_data['stories'] if s['id'] == story_id)
        await callback.message.answer(
            f"📖 <b>{story['rus_title']}</b>\nВыбери язык:",
            reply_markup=await language_menu_kb(story_id)
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в handle_show_story: {e}")
        await callback.answer("⚠️ Ошибка при загрузке сказки", show_alert=True)


@dp.callback_query(F.data.startswith(CALLBACK_LANGUAGE_RU))
async def handle_language_ru(callback: types.CallbackQuery):
    """Показ сказки на русском (только русское название)"""
    try:
        story_id = int(callback.data.replace(CALLBACK_LANGUAGE_RU, ""))
        story = next(s for s in tales_data['stories'] if s['id'] == story_id)
        
        # Обновляем прогресс пользователя и получаем статус обновления
        was_updated = db.update_tale_progress(callback.from_user.id, story_id)
        
        # Только русское название
        message = f"📖 <b>{story['rus_title']}</b>\n{story['rus_text']}"
        parts = await split_long_message(message)
        
        # Добавляем сообщение о прогрессе, если это не первое прочтение
        if was_updated:
            progress = db.get_user_progress(callback.from_user.id)
            for tale in progress["recent_tales"]:
                if tale[0] == story_id:
                    read_count = tale[2]
                    message = f"📖 <b>{story['rus_title']}</b> (прочитано {read_count} раз)\n{story['rus_text']}"
                    parts = await split_long_message(message)
                    break
        
        # Отправляем первую часть без кнопок
        for part in parts[:-1]:
            await callback.message.answer(part)
        
        # Отправляем остальные части
        await callback.message.answer(
            parts[-1],
            reply_markup=await story_menu_kb(story_id))

                
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в handle_language_ru: {e}")
        await callback.answer("⚠️ Ошибка при загрузке сказки", show_alert=True)

@dp.callback_query(F.data.startswith(CALLBACK_LANGUAGE_KH))
async def handle_language_kh(callback: types.CallbackQuery):
    """Показ сказки на хантыйском (с хантыйским и русским названием)"""
    try:
        story_id = int(callback.data.replace(CALLBACK_LANGUAGE_KH, ""))
        story = next(s for s in tales_data['stories'] if s['id'] == story_id)
        
        # Обновляем прогресс пользователя и получаем статус обновления
        was_updated = db.update_tale_progress(callback.from_user.id, story_id)
        
        # Хантыйское + русское название
        message = (
            f"📖 <b>{story['han_title']}</b>\n"
            f"<i>({story['rus_title']})</i>\n"
            f"{story['han_text']}"
        )
        parts = await split_long_message(message)
        
        # Добавляем сообщение о прогрессе, если это не первое прочтение
        if was_updated:
            progress = db.get_user_progress(callback.from_user.id)
            for tale in progress["recent_tales"]:
                if tale[0] == story_id:
                    read_count = tale[2]
                    message = (
                        f"📖 <b>{story['han_title']}</b> (прочитано {read_count} раз)\n"
                        f"<i>({story['rus_title']})</i>\n"
                        f"{story['han_text']}"
                    )
                    parts = await split_long_message(message)
                    break
        
        # Отправляем первую часть без кнопок
        for part in parts[:-1]:
            await callback.message.answer(part)
        
        # Отправляем остальные части
        await callback.message.answer(
            parts[-1],
            reply_markup=await story_menu_kb(story_id))
                
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в handle_language_kh: {e}")
        await callback.answer("⚠️ Ошибка при загрузке сказки", show_alert=True)

@dp.callback_query(F.data.startswith(CALLBACK_PLAY_AUDIO))
async def handle_play_audio(callback: types.CallbackQuery):
    """Обработчик кнопки аудио - отправляет ТОЛЬКО аудио"""
    try:
        story_id = int(callback.data.replace(CALLBACK_PLAY_AUDIO, ""))
        story = next(s for s in tales_data['stories'] if s['id'] == story_id)
        if story.get('audio') and story['audio'] != "pass":
            audio_path = Path(__file__).parent / "audio" / story['audio']
            if audio_path.exists():
                await bot.send_audio(
                    chat_id=callback.message.chat.id,
                    audio=types.FSInputFile(audio_path),
                    title=f"{story['rus_title']} | {story['han_title']}",
                    performer="Хантыйская сказка",
                    caption=f"🎧 {story['rus_title']}"
                )
            else:
                await callback.answer("⚠️ Аудиофайл не найден", show_alert=True)
        else:
            await callback.answer("⚠️ Для этой сказки нет аудио", show_alert=True)
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в handle_play_audio: {e}")
        await callback.answer("⚠️ Ошибка при загрузке аудио", show_alert=True)


@dp.callback_query(F.data.startswith(CALLBACK_SHOW_GRAMMAR))
async def handle_show_grammar(callback: types.CallbackQuery):
    """Показ грамматики для конкретной сказки (с проверкой)"""
    try:
        story_id = int(callback.data.replace(CALLBACK_SHOW_GRAMMAR, ""))
        story = next(s for s in tales_data['stories'] if s['id'] == story_id)

        # Проверяем наличие грамматики
        if not story.get('grammar') or not story['grammar'].strip():
            await callback.answer("❌ Для этой сказки нет грамматики", show_alert=True)
            return

        message = f"📝 <b>Грамматика для сказки '{story['rus_title']}':</b>\n{story['grammar']}"
        parts = await split_long_message(message)
        await callback.message.answer(
            parts[0],
            reply_markup=await story_menu_kb(story_id)
        )
        for part in parts[1:]:
            await callback.message.answer(part)
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в handle_show_grammar: {e}")
        await callback.answer("⚠️ Ошибка при загрузке грамматики", show_alert=True)


@dp.callback_query(F.data.startswith(CALLBACK_SHOW_LEXICON))
async def handle_show_lexicon(callback: types.CallbackQuery):
    """Показ лексики для конкретной сказки (с проверкой)"""
    try:
        story_id = int(callback.data.replace(CALLBACK_SHOW_LEXICON, ""))
        story = next(s for s in tales_data['stories'] if s['id'] == story_id)

        # Проверяем наличие лексики
        if (not story.get('han_words') or not story.get('rus_words') or
            len(story['han_words']) == 0 or len(story['rus_words']) == 0):
            await callback.answer("❌ Для этой сказки нет лексики", show_alert=True)
            return

        # Проверяем совпадение количества слов
        if len(story['han_words']) != len(story['rus_words']):
            logger.warning(f"Несоответствие количества слов в сказке {story_id}")

        word_pairs = []
        for han, rus in zip(story['han_words'], story['rus_words']):
            word_pairs.append(f"• <b>{han}</b> - {rus}")

        message = f"🔤 <b>Лексика для сказки '{story['rus_title']}':</b>\n" + "\n".join(word_pairs)
        parts = await split_long_message(message)
        await callback.message.answer(
            parts[0],
            reply_markup=await story_menu_kb(story_id)
        )
        for part in parts[1:]:
            await callback.message.answer(part)
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в handle_show_lexicon: {e}")
        await callback.answer("⚠️ Ошибка при загрузке лексики", show_alert=True)


@dp.callback_query(F.data.startswith(CALLBACK_BACK_TO_LANGUAGE))
async def handle_back_to_language(callback: types.CallbackQuery):
    """Возврат к выбору языка"""
    try:
        story_id = int(callback.data.replace(CALLBACK_BACK_TO_LANGUAGE, ""))
        story = next(s for s in tales_data['stories'] if s['id'] == story_id)
        await callback.message.answer(
            f"📖 <b>{story['rus_title']}</b>\nВыберите язык:",
            reply_markup=await language_menu_kb(story_id)
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в handle_back_to_language: {e}")
        await callback.answer("⚠️ Ошибка при возврате к выбору языка", show_alert=True)







# --- Обработчики тестов ---
@dp.callback_query(F.data.startswith("start_test_"))
async def handle_start_test(callback: types.CallbackQuery, state: FSMContext):
    """Начало теста по сказке"""
    try:
        tale_id = int(callback.data.replace("start_test_", ""))
        test = next((t for t in tests_data["tests"] if t["fairytale_id"] == tale_id), None)
        if not test or not test["questions"]:
            await callback.answer("Для этой сказки пока нет теста", show_alert=True)
            return

        # Сохраняем текущий тест в состоянии пользователя
        await state.set_data({
            "current_test": test,
            "current_question": 0,
            "test_score": 0
        })

        # Отправляем первый вопрос
        await send_question(callback.message, test["questions"][0], 0, len(test["questions"]))
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в handle_start_test: {e}", exc_info=True)
        await callback.answer("⚠️ Ошибка при запуске теста", show_alert=True)









@dp.callback_query(F.data.startswith("test_answer_"))
async def handle_test_answer(callback: types.CallbackQuery, state: FSMContext):
    """Обработка ответа на вопрос теста"""
    try:
        parts = callback.data.split("_")
        q_id = int(parts[2])
        answer_idx = int(parts[3])
        
        # Получаем данные из FSMContext
        user_data = await state.get_data()
        test = user_data.get("current_test")
        current_question = user_data.get("current_question", 0)
        test_score = user_data.get("test_score", 0)
        answered_with_mistake = user_data.get("answered_with_mistake", set())

        if not test:
            await callback.answer("Тест не найден", show_alert=True)
            return

        question = test["questions"][current_question]
        selected_answer = question["variants"][answer_idx]
        right_answer = question["right answer"]

        # Поддержка нескольких правильных ответов (список или строка)
        if isinstance(right_answer, list):
            right_answers = [str(ans).strip().lower() for ans in right_answer]
            is_correct = str(selected_answer).strip().lower() in right_answers
        else:
            is_correct = str(selected_answer).strip().lower() == str(right_answer).strip().lower()

        # Сохраняем результат в базу данных
        db.save_test_result(
            user_id=callback.from_user.id,
            tale_id=test["fairytale_id"],
            question_id=q_id,
            is_correct=is_correct
        )

        explanation = question.get('explanation', 'Объяснение отсутствует.')

        # Если ответ неверный
        if not is_correct:
            # Запоминаем, что была ошибка
            answered_with_mistake.add(current_question)
            await state.update_data(answered_with_mistake=answered_with_mistake)
            
            # Показываем алёрт с ошибкой
            await callback.answer(f"❌ Неверно.\nПопробуйте снова.", show_alert=True)
            return

        # Если ответ верный
        if current_question not in answered_with_mistake:
            # Ответ верный с первого раза - засчитываем полный балл
            test_score += 1
            # Показываем сообщение с пояснением
            await callback.message.answer(f"✅ Верно!\n{explanation}")
        else:
            # Ответ верный, но после ошибки - засчитываем 0.5 балла
            test_score += 0.5
            # Показываем сообщение с пояснением
            await callback.message.answer(f"✅ Теперь верно.\n{explanation}")

        # Обновляем данные пользователя
        await state.update_data({
            "current_test": test,
            "current_question": current_question + 1,
            "test_score": test_score,
            "answered_with_mistake": set()  # Сбрасываем для нового вопроса
        })

        # Переход к следующему вопросу или завершение
        if current_question + 1 < len(test["questions"]):
            await send_question(
                callback.message,
                test["questions"][current_question + 1],
                current_question + 1,
                len(test["questions"])
            )
        else:
            score_percent = int((test_score / len(test["questions"])) * 100)
            tale = next(t for t in tales_data["stories"] if t["id"] == test["fairytale_id"])
            completion_msg = "🎉 Поздравляем! Вы успешно прошли тест." if score_percent >= 70 else "Вы можете пройти тест ещё раз."
            await callback.message.answer(
                f"📊 Тест по сказке '{tale['rus_title']}' завершён!\n"
                f"Ваш результат: {test_score:.1f} из {len(test['questions'])} ({score_percent}%)\n"
                f"{completion_msg}",
                reply_markup=await story_menu_kb(test["fairytale_id"])
            )

        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка в handle_test_answer: {e}", exc_info=True)
        await callback.answer("⚠️ Ошибка при обработке ответа", show_alert=True)



        






# --- Обработчики словаря ---
@dp.callback_query(F.data == CALLBACK_VOCABULARY)
async def handle_vocabulary(callback: types.CallbackQuery):
    """Обработчик раздела словаря"""
    try:
        await callback.message.answer(
            "📚 Выбери раздел словаря:\n\n"
            "В <b>📝 Общей грамматике</b> можешь прочитать о грамматических правилах: \n" 
            " • Сколько чисел в хантыйском и как они образуются,\n "
            " • Какие есть падежные суффиксы,\n"
            " • Как ласково сказать белочка или рыбка.\n\n"

            "В <b>🔤 Общей лексике</b> сможешь узнать слова из разных категорий:\n" 
            " • Еда,\n" 
            " • Животные,\n"
            " • Природа и другие.\n\n"

            "В <b>🔡 Алфавите</b> можешь увидеть:\n" 
            " • Названия букв\n" 
            " • Гласные звуки\n" 
            " • Согласные звуки.\n",
            reply_markup=await vocabulary_menu_kb()
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в handle_vocabulary: {e}")
        await callback.answer("⚠️ Ошибка при загрузке меню", show_alert=True)


@dp.callback_query(F.data == CALLBACK_GRAMMAR)
async def handle_grammar(callback: types.CallbackQuery):
    """Показ общей грамматики"""
    try:
        grammar_parts = []
        for story in tales_data['stories']:
            if story.get('grammar'):
                grammar_parts.append(f"📝 <b>{story['rus_title']}</b>\n{story['grammar']}\n")

        if not grammar_parts:
            await callback.message.answer("❌ Информация по грамматике не найдена")
            return

        full_message = "\n".join(grammar_parts)
        parts = await split_long_message(full_message)

        # Редактируем текущее сообщение (вместо удаления)
        if len(parts) > 0:
            await callback.message.answer(
                parts[0],
                reply_markup=build_menu([], ("🔙 Назад", CALLBACK_BACK_TO_VOCABULARY))
            )

        # Отправляем остальные части как новые сообщения
        for part in parts[1:]:
            await callback.message.answer(part)

        await callback.answer()
    except AiogramError as e:
        logger.error(f"Aiogram ошибка в handle_grammar: {e}")
        await callback.answer("⚠️ Ошибка при отображении грамматики", show_alert=True)
    except Exception as e:
        logger.error(f"Неизвестная ошибка в handle_grammar: {e}", exc_info=True)
        await callback.answer("⚠️ Произошла внутренняя ошибка", show_alert=True)

# Добавляем глобальный словарь для хранения тематической лексики
themes_dict = defaultdict(list)


@dp.callback_query(F.data == CALLBACK_LEXICON)
async def handle_lexicon(callback: types.CallbackQuery):
    """Показ лексики, сгруппированной по темам (с проверкой)"""
    global themes_dict
    try:
        themes_dict.clear()
        has_lexicon = False

        for story in tales_data['stories']:
            if (story.get('han_words') and story.get('rus_words') and
                len(story['han_words']) > 0 and len(story['rus_words']) > 0):
                has_lexicon = True
                min_length = min(len(story['han_words']), len(story['rus_words']))
                for i in range(min_length):
                    han_word = story['han_words'][i].strip()
                    rus_word = story['rus_words'][i].strip()
                    theme = detect_theme(rus_word)
                    themes_dict[theme].append((han_word, rus_word))

        if not has_lexicon:
            await callback.answer("❌ В словаре нет доступной лексики", show_alert=True)
            return

        builder = InlineKeyboardBuilder()
        for theme in sorted(themes_dict.keys()):
            builder.button(text=theme, callback_data=f"lexicon_theme_{theme}")
        builder.button(text="🔙 Назад", callback_data=CALLBACK_BACK_TO_VOCABULARY)
        builder.adjust(2)

        await callback.message.answer(
            "📚 Выбери тематику словаря:",
            reply_markup=builder.as_markup()
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в handle_lexicon: {e}", exc_info=True)
        await callback.answer("⚠️ Ошибка при загрузке словаря", show_alert=True)


@dp.callback_query(F.data.startswith("lexicon_theme_"))
async def handle_lexicon_theme(callback: types.CallbackQuery):
    """Показывает слова по выбранной теме"""
    global themes_dict

    try:
        theme = callback.data.split('_', 2)[2]
        if theme not in themes_dict:
            await callback.answer("Тема не найдена", show_alert=True)
            return

        words = themes_dict[theme]
        word_list = '\n'.join([f"• <b>{han}</b> — {rus}" for han, rus in words])
        message = f"📚 <b>{theme}</b>\n{word_list}"

        builder = InlineKeyboardBuilder()
        builder.button(text="🔙 Назад", callback_data=CALLBACK_LEXICON)

        await callback.message.answer(
            message,
            reply_markup=builder.as_markup()
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в handle_lexicon_theme: {e}", exc_info=True)
        await callback.answer("⚠️ Ошибка при загрузке темы", show_alert=True)


# --- Обработчики алфавита ---
@dp.callback_query(F.data == CALLBACK_ALPHABET)
async def handle_alphabet(callback: types.CallbackQuery):
    """Обработчик раздела алфавита"""
    try:
        if not phonetics_data:
            await callback.answer("❌ Данные об алфавите не загружены", show_alert=True)
            return

        await callback.message.answer(
            "🔤 Выбери раздел алфавита:",
            reply_markup=await alphabet_menu_kb()
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в handle_alphabet: {e}")
        await callback.answer("⚠️ Ошибка при загрузке меню", show_alert=True)


@dp.callback_query(F.data == CALLBACK_ALPHABET_LETTERS)
async def handle_alphabet_letters(callback: types.CallbackQuery):
    """Обработчик названий букв"""
    try:
        if not phonetics_data:
            await callback.answer("❌ Данные об алфавите не загружены", show_alert=True)
            return

        text = phonetics_data["алфавит"]["название букв"]
        await callback.message.answer(
            text,
            reply_markup=build_menu([], ("🔙 Назад", CALLBACK_ALPHABET))
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в handle_alphabet_letters: {e}")
        await callback.answer("⚠️ Ошибка при загрузке данных", show_alert=True)


@dp.callback_query(F.data == CALLBACK_ALPHABET_VOWELS)
async def handle_alphabet_vowels(callback: types.CallbackQuery):
    """Обработчик гласных звуков"""
    try:
        if not phonetics_data:
            await callback.answer("❌ Данные об алфавите не загружены", show_alert=True)
            return

        text = phonetics_data["гласные"]
        await callback.message.answer(
            text,
            reply_markup=build_menu([], ("🔙 Назад", CALLBACK_ALPHABET))
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в handle_alphabet_vowels: {e}")
        await callback.answer("⚠️ Ошибка при загрузке данных", show_alert=True)


@dp.callback_query(F.data == CALLBACK_ALPHABET_CONSONANTS)
async def handle_alphabet_consonants(callback: types.CallbackQuery):
    """Обработчик согласных звуков"""
    try:
        if not phonetics_data:
            await callback.answer("❌ Данные об алфавите не загружены", show_alert=True)
            return

        text = phonetics_data["согласные"]
        await callback.message.answer(
            text,
            reply_markup=build_menu([], ("🔙 Назад", CALLBACK_ALPHABET))
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в handle_alphabet_consonants: {e}")
        await callback.answer("⚠️ Ошибка при загрузке данных", show_alert=True)


# --- Обработчики навигации ---
@dp.callback_query(F.data == CALLBACK_BACK_TO_MAIN)
async def handle_back_to_main(callback: types.CallbackQuery):
    """Возврат в главное меню"""
    try:
        await callback.message.answer(
            f"🌟 <b>{html.escape(callback.from_user.first_name)}</b>, ты в главном меню! \n \n"
            "Выбери <b>📖 Cказки</b>, если хочешь: \n"
            " • почитать или послушать сказки на хантыйском,\n"
            " • увидеть русский перевод сказки,\n"
            " • пройти тест на знание материала,\n\n"
             
            "Выбери <b>📚 Словарик</b>, если хочешь:\n"
            " • почитать про хантыйский алфавит,\n"
            " • увидеть список слов с переводом,\n"
            " • узнать грамматические правила. \n\n",
            
            reply_markup=await main_menu_kb(),
            parse_mode=ParseMode.HTML
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в handle_back_to_main: {e}")
        await callback.answer("⚠️ Ошибка при возврате в меню", show_alert=True)


@dp.callback_query(F.data == CALLBACK_BACK_TO_TALES)
async def handle_back_to_tales(callback: types.CallbackQuery):
    """Возврат в меню сказок"""
    try:
        await callback.message.answer(
            "📖 Выбери сказку или воспользуйся кнопками <b>Вперёд ▶️</b> и <b>◀️ Назад</b> для перехода по меню:",
            reply_markup=await tales_menu_kb()
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в handle_back_to_tales: {e}")
        await callback.answer("⚠️ Ошибка при возврате в меню", show_alert=True)


@dp.callback_query(F.data == CALLBACK_BACK_TO_VOCABULARY)
async def handle_back_to_vocabulary(callback: types.CallbackQuery):
    """Возврат в меню словаря"""
    try:
        await callback.message.answer(
           "📚 Выбери раздел словаря:\n\n"
            "В <b>📝 Общей грамматике</b> можешь прочитать о грамматических правилах: \n" 
            " • Сколько чисел в хантыйском и как они образуются,\n "
            " • Какие есть падежные суффиксы,\n"
            " • Как ласково сказать белочка или рыбка.\n\n"

            "В <b>🔤 Общей лексике</b> сможешь узнать слова из разных категорий:\n" 
            " • Еда,\n" 
            " • Животные,\n"
            " • Природа и другие.\n\n"

            "В <b>🔡 Алфавите</b> можешь увидеть:\n" 
            " • Названия букв\n" 
            " • Гласные звуки\n" 
            " • Согласные звуки.\n"
            ,
            reply_markup=await vocabulary_menu_kb()
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в handle_back_to_vocabulary: {e}")
        await callback.answer("⚠️ Ошибка при возврате в меню", show_alert=True)


@dp.callback_query(F.data == "show_progress")
async def handle_show_progress(callback: types.CallbackQuery):
    """Обработчик кнопки прогресса"""
    await cmd_progress(callback.message)
    await callback.answer()


# --- Обработчики текстовых сообщений ---
@dp.message(F.text)
async def handle_text(message: types.Message):
    """Обработчик текстовых сообщений"""
    await message.answer("Пожалуйста, используйте кнопки меню или команду /start")


@dp.message()
async def handle_other(message: types.Message):
    """Обработчик всех необработанных сообщений"""
    await message.answer("Извините, я не понимаю этот тип сообщений. Используйте кнопки меню.")


# --- Глобальный обработчик ошибок ---
@dp.error()
async def errors_handler(event: types.ErrorEvent):
    """Глобальный обработчик ошибок для aiogram 3.x"""
    logger.error(
        "Ошибка при обработке события %s: %s",
        event.update,
        event.exception,
        exc_info=True
    )
    return True


# --- Запуск бота ---
async def main():
    try:
        logger.info("Запуск бота...")
        await set_bot_commands(bot)  # Добавьте эту строку
        await dp.start_polling(bot)
    except Exception as e:
        logger.critical(f"Ошибка при запуске бота: {e}")
    finally:
        await bot.session.close()
        logger.info("Бот остановлен")


if __name__ == "__main__":
    asyncio.run(main())



