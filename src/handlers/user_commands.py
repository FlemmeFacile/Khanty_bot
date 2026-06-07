# src/handlers/user_commands.py

import html
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import BotCommand
from src.core.config import all_themes_list
from src.core.config import logger, CALLBACK_BACK_TO_MAIN
from src.utils.keyboards import main_menu_kb
from src.db.database import Database

router = Router()

async def set_bot_commands(bot):
    """Установка команд бота"""
    commands = [
        BotCommand(command="/start", description="Начать работу с ботом"),
        BotCommand(command="/menu", description="Главное меню"),
        BotCommand(command="/progress", description="Показать прогресс")
    ]
    await bot.set_my_commands(commands)

@router.message(Command("start", "menu"))
async def cmd_start_or_menu(message: types.Message, db: Database):
    """Обработчик команды /start и /menu"""
    try:
        user = message.from_user
        db.add_user(user)
        
        name = user.first_name if user.first_name else "друг"
        
        welcome_text = (
            f"🌟 <b>{html.escape(name)}</b>, ты в главном меню! \n \n"
            "Выбери <b>📖 Cказки</b>, если хочешь: \n"
            " • почитать или послушать сказки на хантыйском,\n"
            " • увидеть русский перевод сказки,\n"
            " • пройти тест на знание материала,\n\n"
             
            "Выбери <b>📚 Словарик</b>, если хочешь:\n"
            " • услышать произношение букв хантыйского алфавита,\n"
            " • увидеть список слов с переводом,\n"
            " • узнать грамматические правила. \n\n"
        )
        
        await message.answer(
            welcome_text,
            reply_markup=await main_menu_kb(),
            parse_mode=ParseMode.HTML
        )
        
    except Exception as e:
        logger.error(f"Ошибка в cmd_start_or_menu: {e}")
        await message.answer(
            "🌟 Добро пожаловать! Пожалуйста, выбери раздел:",
            reply_markup=await main_menu_kb()
        )

@router.callback_query(F.data == CALLBACK_BACK_TO_MAIN)
async def handle_back_to_main(callback: types.CallbackQuery, db: Database):
    """Обработчик нажатия на кнопку 'Главное меню'"""
    try:
        await cmd_start_or_menu(callback.message, db)
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка в handle_back_to_main: {e}")
        await callback.answer("⚠️ Ошибка при возврате в меню", show_alert=True)


