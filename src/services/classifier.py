# src/services/classifier.py
import spacy
import torch
import torch.nn as nn
import pickle
from gensim.models import KeyedVectors
from functools import lru_cache
import json
import numpy as np
from typing import List, Optional, Dict
from pathlib import Path

# Импорт из модулей проекта
from src.core.config import logger 

# Путь к корню проекта для моделей
BASE_DIR = Path(__file__).resolve().parent.parent.parent
MODEL_DIR = BASE_DIR / "models"
MANUAL_DICT_FILE = BASE_DIR / 'diccionario.json'



# Загрузка модели spaCy
try:
    nlp_spacy = spacy.load("ru_core_news_sm")
    logger.info("spaCy модель для частей речи загружена")
except Exception:
    nlp_spacy = None
    logger.warning("spaCy не загружена, части речи будут определяться по умолчанию")



import json
import re
from pathlib import Path
from typing import Dict

class PosTagger:
    """Определение части речи с приведением к детским категориям (spaCy + pymorphy3 + ручные правки)"""

    POS_MAP = {
        'NOUN': 'Существительное', 'PROPN': 'Существительное',
        'VERB': 'Глагол', 'ADJ': 'Прилагательное', 'ADV': 'Наречие',
        'NUM': 'Числительное', 'PRON': 'Местоимение',
        'CCONJ': 'Служебное', 'SCONJ': 'Служебное', 'ADP': 'Служебное',
        'PART': 'Служебное', 'INTJ': 'Служебное', 'DET': 'Местоимение',
    }

    # Путь к файлу с ручными исправлениями
    MANUAL_POS_FILE = BASE_DIR / 'manual_pos.json'
    _manual_pos_cache: Dict[str, str] = None  # кэш загруженных исправлений

    @classmethod
    def _load_manual_pos(cls) -> Dict[str, str]:
        """Загружает ручные исправления из JSON, кэширует и возвращает словарь"""
        if cls._manual_pos_cache is not None:
            return cls._manual_pos_cache
        try:
            if cls.MANUAL_POS_FILE.exists():
                with open(cls.MANUAL_POS_FILE, 'r', encoding='utf-8') as f:
                    cls._manual_pos_cache = json.load(f)
                logger.info(f"Загружено ручных исправлений частей речи: {len(cls._manual_pos_cache)}")
            else:
                logger.warning(f"Файл {cls.MANUAL_POS_FILE} не найден, ручные исправления отключены")
                cls._manual_pos_cache = {}
        except Exception as e:
            logger.error(f"Ошибка загрузки manual_pos.json: {e}")
            cls._manual_pos_cache = {}
        return cls._manual_pos_cache

    @staticmethod
    def clean_word(text: str) -> str:
        """Убирает пояснения в скобках и запятые, берёт первое слово"""
        text = re.sub(r'\([^)]*\)', '', text)
        text = text.split(',')[0].strip()
        return text if text else None

    @classmethod
    def _pymorphy_pos(cls, word: str) -> str:
        """Fallback с использованием pymorphy3, если spaCy не загружена"""
        import pymorphy3
        morph = pymorphy3.MorphAnalyzer()
        parsed = morph.parse(word)[0]
        tag = parsed.tag.POS
        mapping = {
            'NOUN': 'Существительное',
            'ADJF': 'Прилагательное', 'ADJS': 'Прилагательное',
            'VERB': 'Глагол', 'INFN': 'Глагол', 'GRND': 'Глагол',
            'PRTF': 'Прилагательное', 'PRTS': 'Прилагательное',
            'NUMR': 'Числительное',
            'NPRO': 'Местоимение',
            'ADVB': 'Наречие',
            'CONJ': 'Служебное', 'PREP': 'Служебное', 'PRCL': 'Служебное', 'INTJ': 'Служебное',
        }
        return mapping.get(tag, 'Существительное')

    @classmethod
    def get_pos(cls, text: str) -> str:
        """Возвращает часть речи для слова/фразы (с учётом ручных исправлений)"""
        cleaned = cls.clean_word(text)
        if not cleaned:
            return 'Существительное'

        # 1. Проверяем ручные исправления (из JSON)
        manual = cls._load_manual_pos()
        if cleaned in manual:
            return manual[cleaned]

        # 2. Пробуем spaCy, если загружена
        if nlp_spacy:
            doc = nlp_spacy(cleaned)
            if len(doc) > 0:
                return cls.POS_MAP.get(doc[0].pos_, 'Существительное')

        # 3. Запасной вариант – pymorphy3
        try:
            return cls._pymorphy_pos(cleaned)
        except Exception:
            return 'Существительное'
        













# 1. Определение архитектуры модели (должно совпадать с обучением)
class MultiLabelClassifier(nn.Module):
    def __init__(self, input_size, output_size):
        super().__init__()
        self.layers = nn.Sequential(
            nn.Linear(input_size, 256),
            nn.ReLU(),
            nn.Dropout(0.5),
            nn.Linear(256, 128),
            nn.ReLU(),
            nn.Linear(128, output_size),
            nn.Sigmoid()
        )

    def forward(self, x):
        return self.layers(x)

# 2. Инициализация устройства
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"Используется устройство: {device}")

# 3. Пути к файлам 
PATHS = {
    'word2vec': MODEL_DIR / "word_embeddings.model",
    'pytorch': MODEL_DIR / "multilabel_classifier.pth",
    'mlb': MODEL_DIR / "mlb.pkl"
}


# 4. Загрузка компонентов
def load_models():
    """Загрузка всех необходимых компонентов модели"""
    try:
        # Загружаем Word2Vec модель
        try:
            model_emb = KeyedVectors.load(str(PATHS['word2vec']))
            print("✔ Word2Vec модель загружена успешно!")
            print(f"Размерность эмбеддингов: {model_emb.vector_size}")
        except Exception as e:
            print(f"❌ Ошибка загрузки Word2Vec: {e}")
            raise

        # Загружаем MultiLabelBinarizer
        try:
            with open(PATHS['mlb'], 'rb') as f:
                mlb = pickle.load(f)
            print("✔ MultiLabelBinarizer загружен успешно!")
            print(f"Классы: {mlb.classes_}")
        except Exception as e:
            print(f"❌ Ошибка загрузки mlb.pkl: {e}")
            raise

        # Инициализируем и загружаем PyTorch модель
        try:
            model = MultiLabelClassifier(model_emb.vector_size, len(mlb.classes_)).to(device)
            model.load_state_dict(torch.load(PATHS['pytorch'], map_location=device))
            model.eval()
            print("✔ PyTorch модель загружена успешно!")
        except Exception as e:
            print(f"❌ Ошибка загрузки модели PyTorch: {e}")
            raise

        return model_emb, model, mlb

    except Exception as e:
        print(f"⚠️ Критическая ошибка при загрузке моделей: {e}")
        raise

# 5. Загружаем модели и создаем классификатор
try:
    model_emb, model, mlb = load_models()
    logger.info("Все модели успешно загружены!")
    
    class NeuralThemeClassifier:
        def __init__(self, word2vec_model, pytorch_model, mlb):
            self.word2vec = word2vec_model
            self.model = pytorch_model
            self.mlb = mlb

        @lru_cache(maxsize=5000)
        def predict_themes(self, word: str) -> List[str]:
            """Определение тем слова с помощью нейросети, возвращает список тем"""
            try:
                # В word2vec могут храниться слова только в нижнем регистре
                word_lower = word.lower()
                vec = torch.FloatTensor(np.copy(self.word2vec[word_lower])).unsqueeze(0).to(device)
                with torch.no_grad():
                    out = self.model(vec)
                    # out_np = (out.cpu().numpy() > 0.5).astype(int) # Использование порога 0.5
                    # Для Sigmoid лучше использовать метод Argmax, но здесь оставим порог 0.5
                    out_np = (out.cpu().numpy() > 0.5).astype(int)

                labels = self.mlb.inverse_transform(out_np)[0]
                if labels:
                    return [label.capitalize() for label in labels]
                else:
                    return ["Общее"]
            except KeyError:
                return ["Общее"]  # Если слова нет в word2vec
            except Exception as e:
                logger.error(f"Ошибка предсказания: {e}")
                return ["Общее"]

    theme_classifier = NeuralThemeClassifier(model_emb, model, mlb)
    logger.info("Нейросетевой классификатор тем инициализирован!")

except Exception as e:
    logger.error(f"❌ Ошибка загрузки нейросетевых моделей: {e}")
    class DummyThemeClassifier:
        @lru_cache(maxsize=5000)
        def predict_themes(self, word: str) -> List[str]:
            return ["Общее"]
    
    theme_classifier = DummyThemeClassifier()
    logger.warning("⚠️ Используется заглушечный классификатор тем")

def load_manual_dictionary() -> Dict[str, List[str]]:
    """Загрузка ручного словаря из JSON с поддержкой составных слов."""
    try:
        with open(MANUAL_DICT_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        manual_dict = {}
        
        for item in data:
            original_word = item['word']
            labels = item['labels']
            # Сохраняем составное слово целиком (ключ с запятой остаётся)
            clean_original = original_word.lower().strip()
            manual_dict[clean_original] = labels   # составное слово как единый ключ
            
            # Обрабатываем одиночные варианты, если есть запятая
            if ',' in original_word:
                variants = [v.strip() for v in original_word.split(',')]
                for variant in variants:
                    clean_variant = variant.lower().strip()
                    clean_variant = clean_variant.replace('?', '').replace('!', '').replace('.', '').strip()
                    if clean_variant and clean_variant not in manual_dict:
                        manual_dict[clean_variant] = labels
            else:
                # Одиночное слово уже сохранено выше
                pass
        
        logger.info(f"Ручной словарь загружен: {len(manual_dict)} ключей (включая составные)")
        return manual_dict
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки ручного словаря: {e}")
        return {}
    
manual_dictionary = load_manual_dictionary()

class HybridThemeClassifier:
    def __init__(self, manual_dict, neural_classifier):
        self.manual_dict = manual_dict
        self.neural = neural_classifier

    def clean_input_word(self, word: str) -> str:
        """Очищает входное слово для сравнения"""
        if not word:
            return ""
        cleaned = word.lower().strip()
        cleaned = cleaned.replace('?', '').replace('!', '').replace('.', '').replace(',', '').strip()
        return cleaned

    def are_words_similar(self, word1: str, word2: str) -> bool:
        """
        Проверяет, похожи ли слова (для обработки опечаток и вариантов)
        """
        # Простая проверка на схожесть - можно улучшить
        if len(word1) < 3 or len(word2) < 3:
            return False
        
        # Общие буквы в начале слова
        if word1[:3] == word2[:3]:
            return True
        
        # Общие буквы в конце слова  
        if word1[-3:] == word2[-3:]:
            return True
        
        return False


    def smart_dict_search(self, word: str) -> Optional[List[str]]:
        clean_word = self.clean_input_word(word)
        if not clean_word:
            return None

        # 1. Ищем точное совпадение входящей строки (с запятыми)
        if word.lower().strip() in self.manual_dict:
            return self.manual_dict[word.lower().strip()]

        # 2. Ищем очищенное слово (без запятых, скобок и т.п.)
        if clean_word in self.manual_dict:
            return self.manual_dict[clean_word]

        # 3. Поиск по подстроке, как раньше (Ctrl+F)
        clean_word_lower = clean_word.lower()
        for dict_word, labels in self.manual_dict.items():
            dict_word_lower = dict_word.lower()
            if (clean_word_lower == dict_word_lower or
                clean_word_lower in dict_word_lower or
                dict_word_lower in clean_word_lower or
                clean_word_lower.replace(' ', '') == dict_word_lower.replace(' ', '') or
                self.are_words_similar(clean_word_lower, dict_word_lower)):
                return labels
        return None

  
    @lru_cache(maxsize=5000)
    def predict_themes(self, word: str) -> List[str]:
        try:
            # Отладочный вывод
            logger.info(f"Hybrid predict_themes input: '{word}'")

            labels = self.smart_dict_search(word)
            if labels:
                logger.info(f" -> найдено в ручном словаре: {labels}")
                return labels
            
            logger.info(f" -> НЕ НАЙДЕНО в ручном словаре, используется нейросеть")
            return self.neural.predict_themes(word)
        except Exception as e:
            logger.error(f"Ошибка в гибридном классификаторе для слова '{word}': {e}")
            return ["Общее"]

        
# Создаем гибридный классификатор
hybrid_classifier = HybridThemeClassifier(manual_dictionary, theme_classifier)
logger.info("Гибридный классификатор инициализирован!")
