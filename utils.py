# ./utils.py
"""
Общие утилиты для проекта CRL Checker
"""
import os
import logging
from datetime import datetime, timezone
from typing import Optional
from config import MOSCOW_TZ

logger = logging.getLogger(__name__)

def ensure_moscow_tz(dt):
    """Убедиться, что datetime имеет московский часовой пояс."""
    if dt and dt.tzinfo is None:
        # Предполагаем, что naive datetime в UTC, затем конвертируем в Москву
        dt = dt.replace(tzinfo=timezone.utc).astimezone(MOSCOW_TZ)
    elif dt:
        # Если уже есть tz, просто конвертируем в Москву
        dt = dt.astimezone(MOSCOW_TZ)
    return dt

def parse_datetime_with_tz(dt_str):
    """
    Парсинг строки даты/времени с учетом часового пояса.
    Возвращает None в случае ошибки, а не текущее время.
    """
    if not dt_str:
        return None
    try:
        dt = datetime.fromisoformat(dt_str)
        return ensure_moscow_tz(dt)
    except (ValueError, TypeError):
        logger.warning(f"Не удалось распарсить дату: {dt_str}. Возвращено None.")
        return None

def parse_tsl_datetime(date_str):
    """Вспомогательная функция для парсинга даты из TSL."""
    if not date_str:
        return None
    try:
        if 'Z' in date_str:
            return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        else:
            return datetime.fromisoformat(date_str)
    except ValueError:
        try:
            if '.' in date_str and 'Z' in date_str:
                parts = date_str.split('.')
                if len(parts) == 2 and parts[1].endswith('Z'):
                    cleaned_date_str = parts[0] + 'Z'
                    dt_obj = datetime.strptime(cleaned_date_str, "%Y-%m-%dT%H:%M:%SZ")
                    return dt_obj.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    logger.warning(f"Не удалось распарсить дату: {date_str}")
    return None

def format_datetime_for_message(dt_iso_str):
    """Форматирование даты для сообщения"""
    if not dt_iso_str:
        return "Не указана"
    try:
        dt_obj = datetime.fromisoformat(dt_iso_str)
        dt_msk = dt_obj.astimezone(MOSCOW_TZ)
        return dt_msk.strftime('%d.%m.%Y %H:%M:%S')
    except Exception as e:
        logger.error(f"Ошибка форматирования даты {dt_iso_str}: {e}")
        return dt_iso_str

def get_current_time_msk():
    """Получение текущего времени в московском часовом поясе"""
    return datetime.now(MOSCOW_TZ)

def setup_logging(log_file: str, logger_name: str = None):
    """Настройка логирования для модуля"""
    if logger_name:
        logger_obj = logging.getLogger(logger_name)
    else:
        logger_obj = logging.getLogger(__name__)
    
    # Создаем директорию для логов если не существует
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )
    return logger_obj
