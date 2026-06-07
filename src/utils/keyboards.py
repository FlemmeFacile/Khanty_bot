# src/utils/keyboards.py

from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup
from typing import List, Tuple, Optional, Union, Dict
from src.core.config import all_themes_list
# Импорт констант и данных из config
from src.core.config import (
    CALLBACK_TALES, CALLBACK_VOCABULARY, CALLBACK_GRAMMAR, CALLBACK_LEXICON, 
    CALLBACK_BACK_TO_MAIN, CALLBACK_BACK_TO_TALES, CALLBACK_PROGRESS,
    CALLBACK_SHOW_STORY, CALLBACK_LANGUAGE_RU, CALLBACK_LANGUAGE_KH,
    CALLBACK_ALPHABET, CALLBACK_ALPHABET_LETTERS, CALLBACK_ALPHABET_VOWELS,
    CALLBACK_ALPHABET_CONSONANTS, CALLBACK_BACK_TO_VOCABULARY,
    CALLBACK_TALES_PAGE_PREFIX, tales_data, tests_data, culture_data, logger,
    CALLBACK_SHOW_ILLUSTRATIONS, CALLBACK_PLAY_AUDIO, CALLBACK_SHOW_GRAMMAR,
    CALLBACK_SHOW_LEXICON, CALLBACK_SHOW_CULTURE, CALLBACK_ALPHABET_LETTER_DETAIL
)
from pathlib import Path
import os
import json # Для загрузки alphabet.json



# Колбэки для лексики по частям речи
CALLBACK_LEXICON_POS_MENU = "lexicon_pos_menu"          # показ меню частей речи
CALLBACK_LEXICON_POS_PREFIX = "LXP_SHOW_"               # префикс для показа слов конкретной части речи
LEXICON_POS_PAGE_PREFIX = "lexicon_pos_page_"           # префикс для пагинации
ALL_POS_CATEGORIES = [
    "Существительное",
    "Глагол",
    "Прилагательное",
    "Наречие",
    "Числительное",
    "Местоимение",
    "Служебное"
]



# --- Вспомогательная функция для построения меню ---
def build_menu(buttons: List[Tuple[str, str]], 
              back_button: Optional[Tuple[str, str]] = None,
              additional_buttons: List[Tuple[str, str]] = None,
              columns: int = 2) -> InlineKeyboardMarkup:
    """
    Создает inline клавиатуру с кнопками в несколько столбцов.
    """
    builder = InlineKeyboardBuilder()
    
    # Добавляем основные кнопки
    for text, data in buttons:
        builder.button(text=text, callback_data=data)
    
    # Добавляем дополнительные кнопки (например, навигация, описания)
    if additional_buttons:
        for text, data in additional_buttons:
            builder.button(text=text, callback_data=data)
    
    # Добавляем кнопку "Назад" если есть
    if back_button:
        builder.button(text=back_button[0], callback_data=back_button[1])
    
    rows = (len(buttons) + columns - 1) // columns
    
    adjust_params = [columns] * rows
    
    # Добавляем логику для размещения навигационных кнопок (обычно по 2 в ряд)
    if additional_buttons:
        # Пытаемся разместить по две, если их четное количество и они идут парой
        if len(additional_buttons) % 2 == 0:
             adjust_params.extend([2] * (len(additional_buttons) // 2))
        else:
             adjust_params.extend([1] * len(additional_buttons))
    
    if back_button:
        adjust_params.append(1)
    
    builder.adjust(*adjust_params)
    
    return builder.as_markup()

# --- Клавиатуры ---
async def main_menu_kb() -> InlineKeyboardMarkup:
    """Главное меню"""
    buttons = [
        ("📖 Сказки", CALLBACK_TALES),
        ("📚 Словарик", CALLBACK_VOCABULARY),
        ("📊 Мой прогресс", CALLBACK_PROGRESS)
    ]
    return build_menu(buttons, columns=2)

async def vocabulary_menu_kb() -> InlineKeyboardMarkup:
    """Меню словаря с отдельными ветками тем и частей речи"""
    buttons = [
        ("📝 Общая грамматика", CALLBACK_GRAMMAR),
        ("📂 Лексика по темам", CALLBACK_LEXICON),          
        ("🔤 Лексика по частям речи", CALLBACK_LEXICON_POS_MENU), 
        ("🔡 Алфавит", CALLBACK_ALPHABET)
    ]
    return build_menu(buttons, ("🗂️ Главное меню", CALLBACK_BACK_TO_MAIN), columns=2)

async def tales_menu_kb(page: int = 0, page_size: int = 5) -> InlineKeyboardMarkup:
    """Меню сказок с пагинацией"""
    stories = tales_data.get('stories', [])
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
        
    navigation_buttons.append((f"Страница {page+1}/{total_pages}", "page_indicator"))

    if end_idx < len(stories):
        navigation_buttons.append(("Вперёд ▶️", f"{CALLBACK_TALES_PAGE_PREFIX}{page+1}"))
    
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
    try:
        story = next(s for s in tales_data['stories'] if s['id'] == story_id)
        buttons = []
        
        # Пути теперь должны быть относительно корня проекта
        BASE_DIR = Path(__file__).resolve().parent.parent.parent
        ILLUSTRATIONS_DIR = BASE_DIR / "illustraciones" / story['rus_title']
        AUDIO_PATH = BASE_DIR / "audio" / story.get('audio', '')
        
        # Проверки наличия контента
        has_illustrations = ILLUSTRATIONS_DIR.exists() and any(ILLUSTRATIONS_DIR.iterdir())
        has_audio = story.get('audio') and AUDIO_PATH.exists() and story['audio'] != "pass"
        has_grammar = bool(story.get('grammar', '').strip())
        has_lexicon = bool(story.get('han_words')) and bool(story.get('rus_words'))
        has_test = any(t["fairytale_id"] == story_id for t in tests_data.get("tests", []))
        
        # Проверка культурного факта
        has_culture = any(cf for cf in culture_data if cf.get("id") == story_id and cf.get("fact", '').strip())
        
        # Формирование кнопок (для верхних рядов)
        if has_illustrations:
            buttons.append(("🖼️ Иллюстрации", f"{CALLBACK_SHOW_ILLUSTRATIONS}{story_id}"))
        if has_audio:
            buttons.append(("🎧 Аудио", f"{CALLBACK_PLAY_AUDIO}{story_id}"))
        if has_grammar:
            buttons.append(("📖 Грамматика", f"{CALLBACK_SHOW_GRAMMAR}{story_id}"))
        if has_lexicon:
            buttons.append(("🔤 Лексика", f"{CALLBACK_SHOW_LEXICON}{story_id}"))
        if has_test:
            buttons.append(("📝 Пройти тест", f"start_test_{story_id}"))
        if has_culture:
            buttons.append(("🌿 Культура", f"show_culture_{story_id}"))
        
        # ⚠️ ИСПРАВЛЕНИЕ: ТОЧНЫЙ КОНТРОЛЬ ПОРЯДКА КНОПОК
        
        # 1. Формируем колбэк для возврата к выбору языка
        back_to_lang_data = f"{CALLBACK_SHOW_STORY}{story_id}"
        
        # 2. Создаем список нижних кнопок в нужном порядке: 
        # Сначала "Назад к языку", потом "Главное меню"
        bottom_buttons = [
            ("🔙 Назад к языку", back_to_lang_data),
            ("🗂️ Главное меню", CALLBACK_BACK_TO_MAIN)
        ]

        # 3. Отключаем back_button и передаем обе кнопки в additional_buttons
        return build_menu(
            buttons, 
            back_button=None, # Отключаем стандартную кнопку возврата
            additional_buttons=bottom_buttons,
            columns=2 # 2 колонки для основных кнопок
        )
    
    except Exception as e:
        logger.error(f"Ошибка в story_menu_kb: {e}")
        # В случае ошибки возвращаем только Главное меню
        return build_menu([], back_button=("🗂️ Главное меню", CALLBACK_BACK_TO_MAIN))


async def alphabet_menu_kb() -> InlineKeyboardMarkup:
    """Меню раздела алфавита"""
    buttons = [
        ("🔠 Названия букв", CALLBACK_ALPHABET_LETTERS),
        ("🔡 Гласные звуки", CALLBACK_ALPHABET_VOWELS),
        ("🔣 Согласные звуки", CALLBACK_ALPHABET_CONSONANTS)
    ]
    return build_menu(buttons, ("🔙 Назад", CALLBACK_BACK_TO_VOCABULARY), columns=1)





async def lexicon_menu_kb(all_themes: List[str], page: int = 0, page_size: int = 6,
                          themes_dict: Optional[Dict[str, list]] = None) -> InlineKeyboardMarkup:
    """Меню лексики с пагинацией по темам (индексы в callback)"""
    # Отбираем только темы, для которых есть слова (если передан словарь)
    if themes_dict:
        filtered_themes = [t for t in all_themes if themes_dict.get(t)]
    else:
        filtered_themes = all_themes

    total_pages = (len(filtered_themes) + page_size - 1) // page_size
    if page < 0:
        page = 0
    elif page >= total_pages:
        page = total_pages - 1

    start_idx = page * page_size
    end_idx = min(start_idx + page_size, len(filtered_themes))
    themes_on_page = filtered_themes[start_idx:end_idx]

    buttons = []
    for theme in themes_on_page:
        # Находим глобальный индекс в all_themes (для callback)
        global_idx = all_themes.index(theme)
        buttons.append((theme, f"LXT_SHOW_{global_idx}"))

    navigation_buttons = []
    if page > 0:
        navigation_buttons.append(("◀️ Назад", f"lexicon_page_{page-1}"))
    navigation_buttons.append((f"Страница {page+1}/{total_pages}", "page_indicator"))
    if end_idx < len(filtered_themes):
        navigation_buttons.append(("Вперёд ▶️", f"lexicon_page_{page+1}"))

    return build_menu(
        buttons,
        back_button=("🔙 Назад в словарь", CALLBACK_BACK_TO_VOCABULARY),
        additional_buttons=navigation_buttons,
        columns=2
    )


async def get_alphabet_buttons(vowels_only: bool = False, consonants_only: bool = False) -> List[Tuple[str, str]]:
    """Вспомогательная функция для получения кнопок алфавита"""
    try:
        BASE_DIR = Path(__file__).resolve().parent.parent.parent
        with open(BASE_DIR / 'alphabet.json', 'r', encoding='utf-8') as f:
            alphabet_data = json.load(f)
        
        buttons = []
        VOWELS = {'А', 'Ӑ', 'И', 'Й', 'О', 'Ө', 'У', 'Ў', 'Ы', 'Э', 'Є', 'Ә'}
        
        for letter in alphabet_data:
            letter_char = Path(letter['photo']).stem.upper()
            
            is_vowel = letter_char in VOWELS
            is_consonant = not is_vowel
            
            if (vowels_only and is_vowel) or \
               (consonants_only and is_consonant) or \
               (not vowels_only and not consonants_only):
                
                callback_data = f"{CALLBACK_ALPHABET_LETTER_DETAIL}{letter['name']}"
                buttons.append((letter_char, callback_data))

        # Сортировка (если нужно)
        if vowels_only or consonants_only:
            # Сортируем по порядку гласных/согласных
            def get_sort_key(button):
                char = button[0].upper()
                if char in VOWELS:
                    return sorted(list(VOWELS)).index(char)
                return 999 
            buttons.sort(key=get_sort_key)
            
        return buttons
        
    except Exception as e:
        logger.error(f"Ошибка загрузки alphabet.json: {e}")
        return []
    

