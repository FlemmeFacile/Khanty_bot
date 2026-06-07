 # src/handlers/tale_handlers.py
import asyncio
from aiogram.types import InputMediaPhoto
import aiohttp
from aiogram import Router, types, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.enums import ParseMode
import html
from typing import List, Optional, Dict, Tuple
from pathlib import Path
from collections import defaultdict
from src.services.classifier import hybrid_classifier, manual_dictionary
from src.utils.helpers import split_long_message
import json 
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import AiogramError
from aiogram.types import InputMediaPhoto, InlineKeyboardButton
import tempfile
import os
from aiogram.types import InlineKeyboardMarkup
from src.core.config import all_themes_list
from src.services.classifier import PosTagger
import asyncio
from aiogram import Router, types, F
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from collections import defaultdict
from src.services.classifier import PosTagger
from src.utils.keyboards import ALL_POS_CATEGORIES, CALLBACK_LEXICON_POS_MENU, CALLBACK_LEXICON_POS_PREFIX, LEXICON_POS_PAGE_PREFIX



# Импорт из модулей проекта
from src.core.config import (
    logger, CALLBACK_TALES, CALLBACK_SHOW_STORY, CALLBACK_LANGUAGE_RU,
    CALLBACK_LANGUAGE_KH, CALLBACK_BACK_TO_TALES, CALLBACK_BACK_TO_MAIN,
    CALLBACK_SHOW_GRAMMAR, CALLBACK_SHOW_LEXICON, CALLBACK_PLAY_AUDIO, 
    CALLBACK_VOCABULARY, CALLBACK_ALPHABET, CALLBACK_ALPHABET_LETTERS,
    CALLBACK_ALPHABET_VOWELS, CALLBACK_ALPHABET_CONSONANTS, CALLBACK_SHOW_CULTURE,
    CALLBACK_ALPHABET_DESCRIPTION, CALLBACK_VOWELS_DESCRIPTION, 
    CALLBACK_CONSONANTS_DESCRIPTION, CALLBACK_ALPHABET_LETTERS_LIST,
    CALLBACK_ALPHABET_LETTER_DETAIL, CALLBACK_BACK_TO_VOCABULARY, CALLBACK_LEXICON,
    CALLBACK_TALES_PAGE_PREFIX, CALLBACK_SHOW_ILLUSTRATIONS, CALLBACK_GRAMMAR,
    tales_data, tests_data, culture_data, phonetics_data, sort_khanty_words_in_themes,
    sort_by_russian_translation
)
from src.db.database import Database
from src.utils.keyboards import (
    tales_menu_kb, language_menu_kb, story_menu_kb, vocabulary_menu_kb,
    alphabet_menu_kb, lexicon_menu_kb, build_menu, get_alphabet_buttons
)
from src.utils.helpers import (
    split_long_message, send_audio_if_exists, send_question, show_illustration,
    image_cache
)
from src.services.classifier import hybrid_classifier

# --- Роутер ---
router = Router()


from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
MANUAL_POS_FILE = BASE_DIR / 'manual_pos.json'
manual_pos_corrections = {}
if MANUAL_POS_FILE.exists():
    with open(MANUAL_POS_FILE, 'r', encoding='utf-8') as f:
        manual_pos_corrections = json.load(f)
    logger.info(f"Загружено ручных исправлений частей речи: {len(manual_pos_corrections)}")
else:
    logger.warning(f"Файл {MANUAL_POS_FILE} не найден, ручные исправления отключены")




    
# --- Обработчики навигации ---
@router.callback_query(F.data == CALLBACK_TALES)
async def handle_tales_menu(callback: types.CallbackQuery):
    """Обработчик раздела сказок"""
    try:
        await callback.message.answer(
            "📖 Выбери сказку или воспользуйся кнопками <b>Вперёд ▶️</b> и <b>◀️ Назад</b> для перехода по меню:",
            reply_markup=await tales_menu_kb()
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в handle_tales_menu: {e}")
        await callback.answer("⚠️ Ошибка при загрузке меню", show_alert=True)


@router.callback_query(F.data.startswith(CALLBACK_TALES_PAGE_PREFIX))
async def handle_tales_pagination(callback: types.CallbackQuery):
    """Обработчик пагинации сказок"""
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


@router.callback_query(F.data.startswith(CALLBACK_SHOW_STORY))
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


@router.callback_query(F.data == CALLBACK_BACK_TO_TALES)
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


# --- Обработчики языков ---

@router.callback_query(F.data.startswith(CALLBACK_LANGUAGE_RU))
async def handle_language_ru(callback: types.CallbackQuery, state: FSMContext, db: Database):
    """Показ сказки на русском"""
    story_id = int(callback.data.replace(CALLBACK_LANGUAGE_RU, ""))
    await state.update_data(last_lang='ru') # Сохраняем язык
    try:
        story = next(s for s in tales_data['stories'] if s['id'] == story_id)
        
        # Обновляем прогресс пользователя
        was_updated = db.update_tale_progress(callback.from_user.id, story_id)

        message = f"📖 <b>{story['rus_title']}</b>\n{story['rus_text']}"
        parts = await split_long_message(message)
        
        # Добавляем сообщение о прогрессе, если это не первое прочтение
        if was_updated:
            progress_msg = f"\n\n<i>✨ Это ваше повторное прочтение!</i>"
            parts[-1] += progress_msg
            
        for part in parts:
            await callback.message.answer(part, parse_mode=ParseMode.HTML)
            
        await callback.message.answer(
            "Выбери дополнительную информацию:",
            reply_markup=await story_menu_kb(story_id)
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в handle_language_ru: {e}")
        await callback.answer("⚠️ Ошибка при загрузке сказки", show_alert=True)


@router.callback_query(F.data.startswith(CALLBACK_LANGUAGE_KH))
async def handle_language_kh(callback: types.CallbackQuery, state: FSMContext, db: Database):
    """Показ сказки на хантыйском"""
    story_id = int(callback.data.replace(CALLBACK_LANGUAGE_KH, ""))
    await state.update_data(last_lang='kh') # Сохраняем язык
    try:
        story = next(s for s in tales_data['stories'] if s['id'] == story_id)
        
        # Обновляем прогресс пользователя
        was_updated = db.update_tale_progress(callback.from_user.id, story_id)

        message = (
            f"📖 <b>{story['rus_title']} | {story['han_title']}</b>\n\n"
            f"{story['han_text']}"
        )
        
        parts = await split_long_message(message)
        
        if was_updated:
            progress_msg = f"\n\n<i>✨ Это ваше повторное прочтение!</i>"
            parts[-1] += progress_msg
            
        for part in parts:
            await callback.message.answer(part, parse_mode=ParseMode.HTML)
            
        await callback.message.answer(
            "Выбери дополнительную информацию:",
            reply_markup=await story_menu_kb(story_id)
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в handle_language_kh: {e}")
        await callback.answer("⚠️ Ошибка при загрузке сказки", show_alert=True)


# --- Обработчики дополнительных материалов ---

@router.callback_query(F.data.startswith(CALLBACK_PLAY_AUDIO))
async def handle_play_audio(callback: types.CallbackQuery, bot: Bot):
    """Обработчик кнопки аудио - отправляет ТОЛЬКО аудио"""
    try:
        story_id = int(callback.data.replace(CALLBACK_PLAY_AUDIO, ""))
        story = next(s for s in tales_data['stories'] if s['id'] == story_id)
        
        if not await send_audio_if_exists(bot, callback.message.chat.id, story):
            await callback.answer("⚠️ Аудиофайл не найден или отсутствует", show_alert=True)
            
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в handle_play_audio: {e}")
        await callback.answer("⚠️ Ошибка при загрузке аудио", show_alert=True)


@router.callback_query(F.data.startswith(CALLBACK_SHOW_GRAMMAR))
async def handle_show_grammar(callback: types.CallbackQuery):
    """Показ грамматики для конкретной сказки"""
    try:
        story_id = int(callback.data.replace(CALLBACK_SHOW_GRAMMAR, ""))
        story = next(s for s in tales_data['stories'] if s['id'] == story_id)
        
        if not story.get('grammar') or not story['grammar'].strip():
            await callback.answer("❌ Для этой сказки нет грамматики", show_alert=True)
            return

        message = f"📝 <b>Грамматика для сказки '{story['rus_title']}':</b>\n{story['grammar']}"
        parts = await split_long_message(message)

        for part in parts:
            await callback.message.answer(part, parse_mode=ParseMode.HTML)
            
        await callback.message.answer(
            "Выбери дополнительную информацию:",
            reply_markup=await story_menu_kb(story_id)
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в handle_show_grammar: {e}")
        await callback.answer("⚠️ Ошибка при загрузке грамматики", show_alert=True)


@router.callback_query(F.data.startswith(CALLBACK_SHOW_LEXICON))
async def handle_show_lexicon(callback: types.CallbackQuery):
    """Показ лексики для конкретной сказки"""
    try:
        story_id = int(callback.data.replace(CALLBACK_SHOW_LEXICON, ""))
        story = next(s for s in tales_data['stories'] if s['id'] == story_id)
        
        han_words = story.get('han_words', [])
        rus_words = story.get('rus_words', [])
        
        if not han_words or not rus_words or len(han_words) == 0:
            await callback.answer("❌ Для этой сказки нет лексики", show_alert=True)
            return

        lexicon_list = ""
        min_length = min(len(han_words), len(rus_words))
        for i in range(min_length):
            lexicon_list += f" • <b>{han_words[i].strip()}</b> — {rus_words[i].strip()}\n"

        message = (
            f"🔤 <b>Лексика для сказки '{story['rus_title']}':</b>\n\n"
            f"{lexicon_list}"
        )
        parts = await split_long_message(message)

        for part in parts:
            await callback.message.answer(part, parse_mode=ParseMode.HTML)
            
        await callback.message.answer(
            "Выбери дополнительную информацию:",
            reply_markup=await story_menu_kb(story_id)
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в handle_show_lexicon: {e}")
        await callback.answer("⚠️ Ошибка при загрузке лексики", show_alert=True)


@router.callback_query(F.data.startswith(CALLBACK_SHOW_ILLUSTRATIONS))
async def handle_show_illustrations(callback: types.CallbackQuery, state: FSMContext):
    """Начало показа иллюстраций"""
    try:
        story_id = int(callback.data.replace(CALLBACK_SHOW_ILLUSTRATIONS, ""))
        
        # Получаем и сохраняем информацию о текущей иллюстрации
        await state.update_data(current_illustration_page=0, current_story_id=story_id)
        
        # Запускаем показ первой иллюстрации
        await show_illustration(callback.message, story_id, 0, state)
        
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в handle_show_illustrations: {e}")
        await callback.answer("⚠️ Иллюстрации не найдены или произошла ошибка", show_alert=True)


@router.callback_query(F.data.startswith("illustr_prev_") | F.data.startswith("illustr_next_"))
async def handle_illustr_nav(callback: types.CallbackQuery, state: FSMContext):
    """Переключение иллюстраций"""
    try:
        parts = callback.data.split("_")
        story_id = int(parts[2])
        current_page = int(parts[3])
        
        # Вычисляем новую страницу
        new_page = current_page - 1 if "prev" in callback.data else current_page + 1
        
        # Удаляем предыдущее сообщение с изображением
        await callback.message.delete()
        
        # Показываем новую иллюстрацию
        await show_illustration(callback.message, story_id, new_page, state)
        
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в handle_illustr_nav: {e}")
        await callback.answer("⚠️ Ошибка при переключении иллюстраций", show_alert=True)


def build_pos_index(themes_dict: Dict[str, List[Tuple[str, str]]]) -> Dict[str, List[Tuple[str, str]]]:
    """Строит словарь {часть_речи: [(хант, рус), ...]} без дубликатов"""
    pos_index = defaultdict(list)
    seen_pairs_by_pos = defaultdict(set)

    for word_pairs in themes_dict.values():
        for han, rus in word_pairs:
            han_clean = han.strip().lower()
            rus_clean = rus.strip().lower()
            normalized_pair = (han_clean, rus_clean)

            # Определяем часть речи
            pos = PosTagger.get_pos(rus_clean)
            # --- ПРИМЕНЯЕМ РУЧНЫЕ ИСПРАВЛЕНИЯ ---
            if rus_clean in manual_pos_corrections:
                pos = manual_pos_corrections[rus_clean]

            if normalized_pair not in seen_pairs_by_pos[pos]:
                seen_pairs_by_pos[pos].add(normalized_pair)
                pos_index[pos].append((han.strip(), rus.strip()))

    for pos in pos_index:
        pos_index[pos].sort(key=lambda x: x[0].lower())
    return pos_index


@router.callback_query(F.data.startswith(CALLBACK_SHOW_CULTURE))
async def show_culture_fact(callback: types.CallbackQuery, state: FSMContext):
    """Показывает культурный факт для сказки"""
    try:
        story_id = int(callback.data.split("_")[-1])
        user_data = await state.get_data()
        lang = user_data.get('last_lang', 'ru')
        
        culture_fact = next((cf for cf in culture_data 
                           if cf.get("id") == story_id and cf.get("fact")), None)
        
        if not culture_fact or not culture_fact.get("fact"):
            await callback.answer("⚠️ Культурный факт не найден", show_alert=True)
            return
        
        fact_text = culture_fact['fact']
        source_text = f"\n\n🔗 Источник: {culture_fact['source']}" if culture_fact.get("source") else ""
        full_caption = f"🌿 <b>Культура</b>\n\n{fact_text}{source_text}"
        
        back_callback = f"{CALLBACK_LANGUAGE_RU}{story_id}" if lang == 'ru' else f"{CALLBACK_LANGUAGE_KH}{story_id}"
        kb = InlineKeyboardBuilder()
        kb.button(text="🔙 Назад к сказке", callback_data=back_callback)
        kb.button(text="🗂️ Главное меню", callback_data=CALLBACK_BACK_TO_MAIN)
        kb.adjust(2)
        
        await send_culture_content(callback.message, culture_fact, full_caption, kb.as_markup())
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка показа культурного факта: {e}", exc_info=True)
        await callback.answer("⚠️ Произошла ошибка", show_alert=True)


async def send_culture_content(message: types.Message, culture_fact: dict, full_caption: str, reply_markup):
    """Универсальная отправка культурного факта"""
    photo_path = culture_fact.get("photo")
    
    if not photo_path:
        await safe_send_message(message, full_caption, reply_markup)
        return
    
    try:
        if photo_path.startswith(("http://", "https://")):
            photo_path = await download_photo(photo_path)
        
        if len(full_caption) <= 1024:
            photo = types.FSInputFile(photo_path)
            await message.answer_photo(photo=photo, caption=full_caption, 
                                     reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        else:
            short_caption = "🌿 <b>Культура</b>"
            photo = types.FSInputFile(photo_path)
            await message.answer_photo(photo=photo, caption=short_caption, 
                                     parse_mode=ParseMode.HTML)
            await safe_send_message(message, full_caption, reply_markup)
            
    except Exception as e:
        logger.error(f"Ошибка отправки фото: {e}")
        await safe_send_message(message, full_caption, reply_markup)
    
    finally:
        if photo_path and os.path.exists(photo_path) and not photo_path.startswith(('http', '/')):
            try:
                os.unlink(photo_path)
            except:
                pass


async def download_photo(url: str) -> str:
    """Скачивает фото из URL"""
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(url, timeout=10) as response:
            if response.status != 200:
                raise Exception(f"HTTP {response.status}")
            with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp_file:
                tmp_file.write(await response.read())
                return tmp_file.name


async def safe_send_message(message: types.Message, text: str, reply_markup):
    """Отправляет текстовое сообщение"""
    await message.answer(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML, 
                        disable_web_page_preview=False)





# --- Обработчики тестов ---

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

@router.callback_query(F.data.startswith("start_test_"))
async def handle_start_test(callback: types.CallbackQuery, state: FSMContext, tales_data: dict): # tales_data для проверки
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
            "test_score": 0,
            "answered_with_mistake": set() 
        })

        # Отправляем первый вопрос
        await send_question(callback.message, test["questions"][0], 0, len(test["questions"]))
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в handle_start_test: {e}", exc_info=True)
        await callback.answer("⚠️ Ошибка при запуске теста", show_alert=True)

@router.callback_query(F.data.startswith("test_answer_"))
async def handle_test_answer(
    callback: types.CallbackQuery, 
    state: FSMContext, 
    db: Database,            
    tales_data: dict      
):
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

        # Сохраняем результат в базу данных (теперь db доступен)
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
            # Преобразование в set, так как set не сохраняется в data напрямую
            if isinstance(answered_with_mistake, list): 
                answered_with_mistake = set(answered_with_mistake)
            
            answered_with_mistake.add(current_question)
            await state.update_data(answered_with_mistake=list(answered_with_mistake)) # Сохраняем обратно как list
            
            # Показываем алёрт с ошибкой
            await callback.answer(f"❌ Неверно.\nПопробуйте снова.", show_alert=True)
            return

        # --- Ответ верный (либо с первого раза, либо со второго) ---
        
        # Получаем обновленный набор ошибок
        updated_mistakes = user_data.get("answered_with_mistake", set())

        if current_question not in updated_mistakes:
            # Ответ верный с первого раза - засчитываем полный балл
            test_score += 1
            # Показываем сообщение с пояснением
            await callback.message.answer(f"✅ {explanation}")
        else:
            # Ответ верный, но после ошибки - засчитываем 0.5 балла
            test_score += 0.5
            # Показываем сообщение с пояснением
            await callback.message.answer(f"✅ Теперь верно.\n{explanation}")

        # Обновляем данные пользователя для следующего вопроса
        await state.update_data({
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
            
            # Добавляем вызов mark_tale_completed если тест пройден успешно
            if score_percent >= 70:  # Порог успешного прохождения теста
                db.mark_tale_completed(callback.from_user.id, test["fairytale_id"])
            
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

@router.callback_query(F.data == CALLBACK_VOCABULARY)
async def handle_vocabulary(callback: types.CallbackQuery):
    """Обработчик раздела словаря"""
    try:
        await callback.message.answer(
            "📚 Выбери раздел словаря:\n\n"
            "В <b>📝 Общей грамматике</b> можешь прочитать о грамматических правилах: \n"
            " • Сколько чисел в хантыйском и как они образуются,\n "
            " • Какие есть падежные суффиксы,\n"
            " • Как ласково сказать белочка или рыбка.\n\n"
            "В <b>📁 Лексике по темам</b> сможешь узнать слова из разных категорий:\n"
            " • Еда,\n"
            " • Животные,\n"
            " • Природа и другие.\n\n"
            "В <b>🔤 Лексике по частям речи</b> слова разделены по категориям для более простого поиска:\n"
            " • Существительное,\n"
            " • Местоимение,\n"
            " • Числительное и другие.\n\n"
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


@router.callback_query(F.data == CALLBACK_GRAMMAR)
async def handle_general_grammar(callback: types.CallbackQuery):
    """Показ общей грамматики (восстановленный из старого кода)"""
    try:
        grammar_parts = []
        for story in tales_data['stories']:
            if story.get('grammar'):
                grammar_parts.append(f"📝 <b>{story['rus_title']}</b>\n{story['grammar']}\n")

        if not grammar_parts:
            await callback.message.answer("❌ Информация по грамматике не найдена")
            await callback.answer()
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
        logger.error(f"Aiogram ошибка в handle_general_grammar: {e}")
        await callback.answer("⚠️ Ошибка при отображении грамматики", show_alert=True)
    except Exception as e:
        logger.error(f"Неизвестная ошибка в handle_general_grammar: {e}", exc_info=True)
        await callback.answer("⚠️ Произошла внутренняя ошибка", show_alert=True)



@router.callback_query(F.data == CALLBACK_LEXICON)
async def handle_lexicon_first(callback: types.CallbackQuery, state: FSMContext):
    """Первый вход в меню лексики — создает новое сообщение"""
    try:
        # Инициализируем themes_dict всеми темами из глобального списка
        themes_dict = {theme: [] for theme in all_themes_list}
        stats = {'manual': 0, 'neural': 0}
        seen_pairs_by_theme = {theme: set() for theme in all_themes_list}

        for story in tales_data['stories']:
            if not (story.get('han_words') and story.get('rus_words') and
                    len(story['han_words']) > 0 and len(story['rus_words']) > 0):
                continue

            han_words = [w.strip() for w in story['han_words']]
            rus_words = [w.strip() for w in story['rus_words']]
            min_len = min(len(han_words), len(rus_words))

            for i in range(min_len):
                han_word = han_words[i]
                rus_word = rus_words[i]
                if not han_word or not rus_word:
                    continue

                rus_lower = rus_word.lower().strip()
                if rus_lower in manual_dictionary:
                    stats['manual'] += 1
                else:
                    stats['neural'] += 1

                themes = hybrid_classifier.predict_themes(rus_word)
                for theme in themes:
                    if theme not in themes_dict:
                        continue  # Игнорируем неизвестные темы
                    pair = (han_word, rus_word)
                    if pair not in seen_pairs_by_theme[theme]:
                        themes_dict[theme].append(pair)
                        seen_pairs_by_theme[theme].add(pair)

        # Удаляем пустые темы? Лучше оставить все, но в меню показывать только непустые
        # Для клавиатуры будем фильтровать на лету
        non_empty_themes = [theme for theme in all_themes_list if themes_dict[theme]]
        if not non_empty_themes:
            await callback.answer("❌ В словаре нет доступной лексики", show_alert=True)
            return

        # Сортируем слова внутри каждой темы
        themes_dict = sort_khanty_words_in_themes(themes_dict)

        logger.info(f"Классификация: {stats['manual']} слов из ручного словаря, {stats['neural']} слов нейросетью")
        logger.info(f"Темы распределены: {len(non_empty_themes)} непустых тем, всего пар: {sum(len(v) for v in themes_dict.values())}")

        # Сохраняем полный словарь тем и список непустых (или используем all_themes_list прямо в клавиатуре)
        await state.update_data({
            'themes_dict': themes_dict,
            'lexicon_page': 0
        })

        message = await callback.message.answer(
            "📚 Выбери тематику словаря. Слова внутри каждой темы расположены в алфавитном порядке.\n\n"
            "Воспользуйся кнопками <b>Вперёд ▶️</b> и <b>◀️ Назад</b> для перехода по меню:",
            reply_markup=await lexicon_menu_kb(all_themes_list, 0, themes_dict=themes_dict)
        )
        await state.update_data({'lexicon_message_id': message.message_id})
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка в handle_lexicon_first: {e}", exc_info=True)
        await callback.answer("⚠️ Ошибка при загрузке словаря", show_alert=True)














async def handle_lexicon_return_to_themes(callback: types.CallbackQuery, state: FSMContext):
    """Возвращает из просмотра слов конкретной темы обратно в меню тем лексики."""
    try:
        data = await state.get_data()
        all_themes = data.get('all_themes')
        
        if not all_themes:
            await callback.answer("⚠️ Ошибка: Тематика не загружена.", show_alert=True)
            return
            
        # 1. Сбрасываем страницу на 0, чтобы пагинация работала с первой страницы
        await state.update_data({'lexicon_page': 0})
        
        # 2. Удаляем текущее сообщение (со словами темы), чтобы не оставлять мусор
        try:
            await callback.bot.delete_message(
                chat_id=callback.message.chat.id,
                message_id=callback.message.message_id
            )
        except AiogramError as e:
            logger.info(f"Не удалось удалить текущее сообщение со словами: {e}")
            pass
            
        text = "📚 Выбери тематику словаря. Воспользуйся кнопками <b>Вперёд ▶️</b> и <b>◀️ Назад</b> для перехода по меню:"
        
        # 3. Отправляем новое сообщение с меню тем
        message = await callback.bot.send_message(
            chat_id=callback.message.chat.id,
            text=text,
            reply_markup=await lexicon_menu_kb(all_themes, 0), # Генерируем для страницы 0
            parse_mode=ParseMode.HTML
        )
        
        # 4. Сохраняем ID НОВОГО сообщения, которое теперь нужно редактировать при пагинации
        await state.update_data({'lexicon_message_id': message.message_id})

        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в handle_lexicon_return_to_themes: {e}")
        await callback.answer("⚠️ Ошибка при возврате в меню", show_alert=True)








@router.callback_query(F.data.startswith("lexicon_page_"))
async def handle_lexicon_pagination(callback: types.CallbackQuery, state: FSMContext):
    """Пагинация по темам (использует глобальный all_themes_list)"""
    try:
        new_page = int(callback.data.replace("lexicon_page_", ""))

        page_size = 6
        total_pages = (len(all_themes_list) + page_size - 1) // page_size
        # Нормализация
        if new_page < 0:
            new_page = 0
        elif new_page >= total_pages:
            new_page = total_pages - 1

        data = await state.get_data()
        message_id = data.get('lexicon_message_id')
        if not message_id:
            await callback.answer("Ошибка: не найден идентификатор сообщения", show_alert=True)
            return

        await state.update_data({'lexicon_page': new_page})
        new_keyboard = await lexicon_menu_kb(all_themes_list, new_page)

        try:
            await callback.bot.edit_message_reply_markup(
                chat_id=callback.message.chat.id,
                message_id=message_id,
                reply_markup=new_keyboard
            )
        except AiogramError as e:
            if 'message is not modified' not in str(e):
                raise e
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в handle_lexicon_pagination: {e}")
        await callback.answer("⚠️ Ошибка при переключении страницы", show_alert=True)








'''
@router.callback_query(F.data.startswith("show_lexicon_theme_"))
async def handle_show_lexicon_theme(callback: types.CallbackQuery, state: FSMContext):
    """Показ слов по выбранной теме"""
    try:
        theme = callback.data.replace("show_lexicon_theme_", "")
        data = await state.get_data()
        themes_dict: Dict[str, List[Tuple[str, str]]] = data.get('themes_dict', {})
        current_page = data.get('lexicon_page', 0)
        
        words = themes_dict.get(theme)
        
        if not words:
            await callback.answer(f"❌ Слов по теме '{theme}' не найдено.", show_alert=True)
            return

        lexicon_list = ""
        for han_word, rus_word in words:
            lexicon_list += f" • <b>{han_word}</b> — {rus_word}\n"
            
        message = (
            f"🔤 <b>Словарь по теме: {theme}</b> (Всего: {len(words)})\n\n"
            f"{lexicon_list}"
        )
        parts = await split_long_message(message)
        
        # Кнопка возврата к списку тем
        back_button = ("🔙 Назад к темам", f"lexicon_return_to_page_{current_page}")

        for part in parts:
            await callback.message.answer(part, parse_mode=ParseMode.HTML)
            
        # Отправляем клавиатуру после всего текста
        await callback.message.answer(
            "Выбери действие:",
            reply_markup=build_menu([], back_button=back_button)
        )
        
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в handle_show_lexicon_theme: {e}")
        await callback.answer("⚠️ Ошибка при загрузке темы", show_alert=True)

'''





@router.callback_query(F.data == CALLBACK_BACK_TO_VOCABULARY)
async def handle_back_to_vocabulary(callback: types.CallbackQuery):
    """Возврат в меню словаря"""
    try:
        await callback.message.answer(
            "📚 Выбери раздел словаря:\n\n"
            "В <b>📝 Общей грамматике</b> можешь прочитать о грамматических правилах: \n"
            " • Сколько чисел в хантыйском и как они образуются,\n "
            " • Какие есть падежные суффиксы,\n"
            " • Как ласково сказать белочка или рыбка.\n\n"
            "В <b>📁 Лексике по темам</b> сможешь узнать слова из разных категорий:\n"
            " • Еда,\n"
            " • Животные,\n"
            " • Природа и другие.\n\n"
            "В <b>🔤 Лексике по частям речи</b> слова разделены по категориям для более простого поиска:\n"
            " • Существительное,\n"
            " • Местоимение,\n"
            " • Числительное и другие.\n\n"
            "В <b>🔡 Алфавите</b> можешь увидеть:\n"
            " • Названия букв\n"
            " • Гласные звуки\n"
            " • Согласные звуки.\n",
            reply_markup=await vocabulary_menu_kb()
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в handle_back_to_vocabulary: {e}")
        await callback.answer("⚠️ Ошибка при возврате в меню", show_alert=True)
















@router.callback_query(F.data.startswith("LXT_SHOW_"))
async def handle_show_lexicon_theme(callback: types.CallbackQuery, state: FSMContext):
    """Показ слов по выбранной теме (индекс из глобального списка)"""
    try:
        theme_idx = int(callback.data.split("_")[-1])
        if theme_idx < 0 or theme_idx >= len(all_themes_list):
            await callback.answer("Тема не найдена", show_alert=True)
            return
        theme = all_themes_list[theme_idx]

        data = await state.get_data()
        themes_dict = data.get('themes_dict', {})
        words = themes_dict.get(theme, [])

        if not words:
            await callback.answer(f"❌ Слов по теме '{theme}' не найдено.", show_alert=True)
            return

        lexicon_list = ""
        for han_word, rus_word in words:
            lexicon_list += f"• <b>{han_word}</b> — {rus_word}\n"

        full_text = f"🔤 <b>Словарь по теме: {theme}</b> (Всего: {len(words)})\n\n{lexicon_list}"
        parts = await split_long_message(full_text, max_length=4000)

        current_page = data.get('lexicon_page', 0)
        back_button = ("🔙 Назад к темам", f"lexicon_return_to_page_{current_page}")

        for i, part in enumerate(parts):
            if i == 0 and len(parts) == 1:
                await callback.message.answer(part, parse_mode=ParseMode.HTML,
                                             reply_markup=build_menu([], back_button=back_button))
            elif i == 0:
                await callback.message.answer(part, parse_mode=ParseMode.HTML)
            else:
                await callback.message.answer(part, parse_mode=ParseMode.HTML)

        if len(parts) > 1:
            await callback.message.answer("Выбери действие:",
                                         reply_markup=build_menu([], back_button=back_button))
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в handle_show_lexicon_theme: {e}", exc_info=True)
        await callback.answer("⚠️ Ошибка при загрузке темы", show_alert=True)











# --- Обработчики алфавита ---

VOWELS = {'А', 'Ă', 'И', 'О', 'Ө', 'У', 'Ў', 'Ы', 'Э', 'Є', 'Ә', 'а', 'ӑ', 'и', 'о', 'ө', 'у', 'ў', 'ы', 'э', 'є', 'ә'}
BASE_DIR = Path(__file__).resolve().parent.parent.parent
PHONETICS_DIR = BASE_DIR / 'phonetics' # Папка для звуков алфавита

@router.callback_query(F.data == CALLBACK_ALPHABET)
async def handle_alphabet(callback: types.CallbackQuery):
    """Меню алфавита"""
    try:
        await callback.message.answer(
            "🔤 Выбери раздел хантыйского алфавита:\n\n"
            "Здесь ты можешь увидеть написание каждой буквы и прослушать ее произношение.",
            reply_markup=await alphabet_menu_kb()
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в handle_alphabet: {e}")
        await callback.answer("⚠️ Ошибка при загрузке меню алфавита", show_alert=True)


@router.callback_query(F.data == CALLBACK_ALPHABET_LETTERS)
async def handle_alphabet_letters_list(callback: types.CallbackQuery):
    """Список всех букв алфавита"""
    try:
        buttons_data = await get_alphabet_buttons() 

        if not buttons_data:
            await callback.answer("⚠️ Буквы алфавита не найдены", show_alert=True)
            return

        # Используем вашу готовую функцию build_menu
        additional_buttons = [("📝 Описание алфавита", CALLBACK_ALPHABET_DESCRIPTION)]
        
        builder = InlineKeyboardBuilder()

        # Основные кнопки — буквы (6 в строке)
        for text, data in buttons_data:
            builder.button(text=text, callback_data=data)
        builder.adjust(6)

        # Отдельная строка: "Описание алфавита"
        builder.row(
            InlineKeyboardButton(text="📝 Описание алфавита", callback_data=CALLBACK_ALPHABET_DESCRIPTION)
        )

        # Отдельная строка: "Назад"
        builder.row(
            InlineKeyboardButton(text="🔙 Назад", callback_data=CALLBACK_ALPHABET)
        )

        await callback.message.answer(
            "🔠 <b>Хантыйский алфавит</b>\n\n"
            "Выбери букву, чтобы увидеть её написание и услышать произношение.\n\n"
            "ℹ️ Для общего описания алфавита нажми «📝 Описание алфавита».\n\n"
            "⬅️ Чтобы вернуться к меню алфавита, используй кнопку «🔙 Назад».",
            reply_markup=builder.as_markup()
        )
    except Exception as e:
        logger.error(f"Ошибка в handle_alphabet_letters_list: {e}")
        await callback.answer("⚠️ Ошибка при загрузке списка букв", show_alert=True)


@router.callback_query(F.data == CALLBACK_ALPHABET_VOWELS)
async def handle_alphabet_vowels(callback: types.CallbackQuery):
    """Список гласных букв алфавита"""
    try:
        BASE_DIR = Path(__file__).resolve().parent.parent.parent
        alphabet_path = BASE_DIR / 'alphabet.json'
        
        with open(alphabet_path, 'r', encoding='utf-8') as f:
            alphabet_data = json.load(f)
        
        buttons = []
        for letter in alphabet_data:
            letter_char = Path(letter['photo']).stem.upper()
            if letter_char in VOWELS:
                callback_data = f"{CALLBACK_ALPHABET_LETTER_DETAIL}{letter['name']}"
                buttons.append((letter_char, callback_data))
        
        # Сортируем по порядку гласных
        VOWELS_ORDER = ['А', 'Ă', 'И', 'О', 'Ө', 'У', 'Ў', 'Ы', 'Э', 'Є', 'Ә', 'а', 'ӑ', 'и', 'о', 'ө', 'у', 'ў', 'ы', 'э', 'є', 'ә']
        buttons.sort(key=lambda x: VOWELS_ORDER.index(x[0]))
     
        builder = InlineKeyboardBuilder()

        # Гласные — 4 в строке
        for text, data in buttons:
            builder.button(text=text, callback_data=data)
        builder.adjust(4)

        # Описание гласных
        builder.row(
            InlineKeyboardButton(text="📝 Описание гласных", callback_data=CALLBACK_VOWELS_DESCRIPTION)
        )

        # Назад
        builder.row(
            InlineKeyboardButton(text="🔙 Назад", callback_data=CALLBACK_ALPHABET)
        )

        await callback.message.answer(
            "🔤 <b>Гласные буквы хантыйского алфавита</b>\n\n"
            "Выбери гласную, чтобы увидеть её написание и услышать произношение.\n\n"
            "ℹ️ Для подробной информации о каждой букве и тонкостях произношения — нажми «📝 Описание гласных».\n\n"
            "⬅️ Чтобы вернуться к меню алфавита, используй кнопку «🔙 Назад».",
            reply_markup=builder.as_markup()
        )
    except Exception as e:
        logger.error(f"Ошибка в handle_alphabet_vowels: {e}")
        await callback.answer("⚠️ Ошибка при загрузке гласных букв", show_alert=True)


@router.callback_query(F.data == CALLBACK_ALPHABET_CONSONANTS)
async def handle_alphabet_consonants(callback: types.CallbackQuery):
    """Список согласных букв алфавита"""
    try:
        BASE_DIR = Path(__file__).resolve().parent.parent.parent
        alphabet_path = BASE_DIR / 'alphabet.json'
        
        with open(alphabet_path, 'r', encoding='utf-8') as f:
            alphabet_data = json.load(f)
        
        consonant_buttons = []
        for letter in alphabet_data:
            letter_char = Path(letter['photo']).stem.upper()
            if letter_char not in VOWELS:
                callback_data = f"{CALLBACK_ALPHABET_LETTER_DETAIL}{letter['name']}"
                consonant_buttons.append((letter_char, callback_data))
        
        # Используем build_menu для согласных
        additional_buttons = [("📝 Описание согласных", CALLBACK_CONSONANTS_DESCRIPTION)]
        
        builder = InlineKeyboardBuilder()

        # Согласные — 5 в строке
        for text, data in consonant_buttons:
            builder.button(text=text, callback_data=data)
        builder.adjust(5)

        # Описание согласных
        builder.row(
            InlineKeyboardButton(text="📝 Описание согласных", callback_data=CALLBACK_CONSONANTS_DESCRIPTION)
        )

        # Назад
        builder.row(
            InlineKeyboardButton(text="🔙 Назад", callback_data=CALLBACK_ALPHABET)
        )

        await callback.message.answer(
            "🔤 <b>Согласные буквы хантыйского алфавита</b>\n\n"
            "Выбери согласную, чтобы увидеть её написание и услышать произношение.\n\n"
            "ℹ️ Для подробной информации о каждой букве и тонкостях произношения — нажми «📝 Описание согласных».\n\n"
            "⬅️ Чтобы вернуться к меню алфавита, используй кнопку «🔙 Назад».",
            reply_markup=builder.as_markup()
        )
    except Exception as e:
        logger.error(f"Ошибка в handle_alphabet_consonants: {e}")
        await callback.answer("⚠️ Ошибка при загрузке согласных букв", show_alert=True)





@router.callback_query(F.data.startswith(CALLBACK_ALPHABET_LETTER_DETAIL))
async def handle_alphabet_letter_detail(callback: types.CallbackQuery, bot: Bot):
    """Показ детализации буквы алфавита (фото и аудио)"""
    try:
        letter_name = callback.data.replace(CALLBACK_ALPHABET_LETTER_DETAIL, "")
        
        BASE_DIR = Path(__file__).resolve().parent.parent.parent
        alphabet_path = BASE_DIR / 'alphabet.json'
        
        # Загружаем данные алфавита
        with open(alphabet_path, 'r', encoding='utf-8') as f:
            alphabet_data = json.load(f)
        
        letter = next((l for l in alphabet_data if l['name'] == letter_name), None)
        
        if not letter:
            await callback.answer(f"⚠️ Буква '{letter_name}' не найдена", show_alert=True)
            return

        # 1. Отправляем фото
        photo_path = BASE_DIR / letter['photo']
        if photo_path.exists():
            await callback.message.answer_photo(
                types.FSInputFile(photo_path), 
                caption=f"Буква: <b>{letter['name']}</b>", 
                parse_mode=ParseMode.HTML
            )
        else:
            await callback.message.answer(f"⚠️ Фото буквы {letter['name']} не найдено")

        # 2. Отправляем аудио с произношением
        audio_path = BASE_DIR / letter['sound']
        if audio_path.exists():
            audio = types.FSInputFile(audio_path)
            await callback.message.answer_audio(audio)
        else:
            await callback.message.answer(f"⚠️ Аудио для {letter['name']} не найдено")

        # 3. Создаем клавиатуру с ВСЕМИ вариантами возврата
        builder = InlineKeyboardBuilder()
        
        # Определяем тип буквы
        letter_char = Path(letter['photo']).stem.upper()
        is_vowel = letter_char in VOWELS
        
        # Добавляем кнопки в зависимости от типа буквы
        if is_vowel:
            builder.button(text="🔙 Назад к гласным", callback_data=CALLBACK_ALPHABET_VOWELS)
        else:
            builder.button(text="🔙 Назад к согласным", callback_data=CALLBACK_ALPHABET_CONSONANTS)
        
        # ВСЕГДА добавляем кнопку "Все буквы"
        builder.button(text="🔠 Все буквы", callback_data=CALLBACK_ALPHABET_LETTERS)
        
        # И кнопку в главное меню алфавита
        builder.button(text="🏠 В меню алфавита", callback_data=CALLBACK_ALPHABET)
        
        # Располагаем кнопки: первая строка - 2 кнопки, вторая строка - 2 кнопки
        builder.adjust(2, 2)
        
        await callback.message.answer(
            "Выбери, куда вернуться:",
            reply_markup=builder.as_markup()
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в handle_alphabet_letter_detail: {e}", exc_info=True)
        await callback.answer("⚠️ Ошибка при загрузке информации о букве", show_alert=True)


@router.callback_query(F.data == CALLBACK_ALPHABET_DESCRIPTION)
async def handle_alphabet_description(callback: types.CallbackQuery):
    """Общее описание алфавита"""
    try:
        BASE_DIR = Path(__file__).resolve().parent.parent.parent
        phonetics_path = BASE_DIR / 'phonetics.json'
        
        text = "📝 <b>Общее описание алфавита</b>\n\n"
        
        try:
            with open(phonetics_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if "алфавит" in data and "название букв" in data["алфавит"]:
                text += data["алфавит"]["название букв"]
            else:
                text += "Общее описание алфавита не найдено в файле phonetics.json."
        except Exception as e:
            text += f"Ошибка загрузки описания: {e}"
        
        # Кнопки возврата
        builder = InlineKeyboardBuilder()
        builder.button(text="🔙 Назад к алфавиту", callback_data=CALLBACK_ALPHABET_LETTERS)
        builder.button(text="🏠 В меню алфавита", callback_data=CALLBACK_ALPHABET)
        builder.adjust(2)
        
        await callback.message.answer(
            text,
            reply_markup=builder.as_markup(),
            parse_mode=ParseMode.HTML
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в handle_alphabet_description: {e}")
        await callback.answer("⚠️ Ошибка при загрузке описания", show_alert=True)


@router.callback_query(F.data == CALLBACK_CONSONANTS_DESCRIPTION)
async def handle_consonants_description(callback: types.CallbackQuery):
    """Описание согласных звуков"""
    try:
        BASE_DIR = Path(__file__).resolve().parent.parent.parent
        phonetics_path = BASE_DIR / 'phonetics.json'
        
        with open(phonetics_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if "согласные" in data:
            text = data["согласные"]
        else:
            text = "Описание согласных звуков не найдено."
        
        await callback.message.answer(
            text,
            reply_markup=build_menu([], ("🔙 Назад", CALLBACK_ALPHABET_CONSONANTS))
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в handle_consonants_description: {e}")
        await callback.answer("⚠️ Ошибка при загрузке описания", show_alert=True)

@router.callback_query(F.data == CALLBACK_VOWELS_DESCRIPTION)
async def handle_vowels_description(callback: types.CallbackQuery):
    """Описание гласных звуков"""
    try:
        BASE_DIR = Path(__file__).resolve().parent.parent.parent
        phonetics_path = BASE_DIR / 'phonetics.json'
        
        text = "🔤 <b>Гласные звуки хантыйского алфавита</b>\n\n"
        
        try:
            with open(phonetics_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if "гласные" in data:
                text += data["гласные"]
            else:
                text += "Описание гласных звуков не найдено."
        except Exception as e:
            text += f"Ошибка загрузки описания: {e}"
        
        # Создаем клавиатуру для возврата
        builder = InlineKeyboardBuilder()
        builder.button(text="🔙 Назад к гласным", callback_data=CALLBACK_ALPHABET_VOWELS)
        builder.button(text="🔠 Все буквы", callback_data=CALLBACK_ALPHABET_LETTERS)
        builder.button(text="🏠 В меню алфавита", callback_data=CALLBACK_ALPHABET)
        builder.adjust(2, 1)  # 2 кнопки в первой строке, 1 во второй
        
        await callback.message.answer(
            text,
            reply_markup=builder.as_markup(),
            parse_mode=ParseMode.HTML
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в handle_vowels_description: {e}")
        await callback.answer("⚠️ Ошибка при загрузке описания", show_alert=True)   



@router.message(F.text)
async def handle_text(message: types.Message):
    """Обработчик текстовых сообщений"""
    await message.answer("Пожалуйста, используйте кнопки меню или команду /start")


@router.message()
async def handle_other(message: types.Message):
    """Обработчик всех необработанных сообщений"""
    await message.answer("Извините, я не понимаю этот тип сообщений. Используйте кнопки меню.")





@router.callback_query(F.data.startswith("lexicon_return_to_page_"))
async def handle_lexicon_return_to_themes(callback: types.CallbackQuery, state: FSMContext):
    """Возврат к списку тем — всегда отправляет новое сообщение"""
    try:
        page = int(callback.data.replace("lexicon_return_to_page_", ""))
        data = await state.get_data()
        themes_dict = data.get('themes_dict', {})

        # Нормализация страницы
        total_pages = (len(all_themes_list) + 6 - 1) // 6
        page = max(0, min(page, total_pages - 1))

        text = "📚 Выбери тематику словаря. Воспользуйся кнопками <b>Вперёд ▶️</b> и <b>◀️ Назад</b> для перехода по меню:"
        reply_markup = await lexicon_menu_kb(all_themes_list, page, themes_dict=themes_dict)

        # Отправляем НОВОЕ сообщение
        msg = await callback.message.answer(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        
        # Обновляем ID сообщения в состоянии, чтобы пагинация работала с новым сообщением
        await state.update_data({
            'lexicon_message_id': msg.message_id,
            'lexicon_page': page
        })

        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в handle_lexicon_return_to_themes: {e}")
        await callback.answer("⚠️ Ошибка при возврате к темам", show_alert=True)

















@router.callback_query(F.data == CALLBACK_LEXICON_POS_MENU)
async def handle_pos_menu(callback: types.CallbackQuery, state: FSMContext):
    """Показывает меню выбора части речи"""
    try:
        data = await state.get_data()
        themes_dict = data.get('themes_dict', {})
        if not themes_dict:
            await callback.answer("❌ Сначала откройте лексику по темам для загрузки словаря", show_alert=True)
            return

        # Строим индекс и сохраняем в состоянии (кэшируем)
        pos_index = build_pos_index(themes_dict)
        await state.update_data({'pos_index': pos_index})

        # Показываем только те категории, в которых есть слова
        available_pos = [pos for pos in ALL_POS_CATEGORIES if pos_index.get(pos)]
        if not available_pos:
            await callback.answer("⚠️ Нет слов ни для одной части речи", show_alert=True)
            return

        # Кнопки выбора части речи (все влезут на одну страницу)
        buttons = [(pos, f"{CALLBACK_LEXICON_POS_PREFIX}{pos}") for pos in available_pos]
        keyboard = build_menu(
            buttons,
            back_button=("🔙 Назад в словарь", CALLBACK_BACK_TO_VOCABULARY),
            columns=2
        )
        await callback.message.answer("🔤 Выбери одну из частей речи ниже:", reply_markup=keyboard)
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в handle_pos_menu: {e}")
        await callback.answer("⚠️ Ошибка при загрузке частей речи", show_alert=True)






@router.callback_query(F.data.startswith(CALLBACK_LEXICON_POS_PREFIX))
async def handle_show_words_by_pos(callback: types.CallbackQuery, state: FSMContext):
    """Показ слов по выбранной части речи"""
    try:
        pos = callback.data.replace(CALLBACK_LEXICON_POS_PREFIX, "")
        data = await state.get_data()
        pos_index = data.get('pos_index', {})
        words = pos_index.get(pos, [])
        if not words:
            await callback.answer(f"Слов с частью речи '{pos}' не найдено", show_alert=True)
            return

        lexicon_list = ""
        for han_word, rus_word in words:
            lexicon_list += f"• <b>{han_word}</b> — {rus_word}\n"
        full_text = f"🔤 <b>Словарь: {pos}</b> (Всего: {len(words)})\n\n{lexicon_list}"
        parts = await split_long_message(full_text, max_length=4000)

        back_button = ("🔙 К частям речи", CALLBACK_LEXICON_POS_MENU)
        for i, part in enumerate(parts):
            if i == 0 and len(parts) == 1:
                await callback.message.answer(part, parse_mode=ParseMode.HTML,
                                             reply_markup=build_menu([], back_button=back_button))
            else:
                await callback.message.answer(part, parse_mode=ParseMode.HTML)
        if len(parts) > 1:
            await callback.message.answer("Выбери действие:",
                                         reply_markup=build_menu([], back_button=back_button))
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в handle_show_words_by_pos: {e}")
        await callback.answer("⚠️ Ошибка при загрузке слов", show_alert=True)
