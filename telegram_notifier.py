# ./telegram_notifier.py
import requests
import logging
from datetime import datetime, timezone
import time  # <-- Новый импорт
import re    # <-- Новый импорт (на всякий случай, если Retry-After будет в body)
import json
from config import *

logger = logging.getLogger(__name__)

class TelegramNotifier:
    def __init__(self):
        self.bot_token = TELEGRAM_BOT_TOKEN
        self.chat_id = TELEGRAM_CHAT_ID
        self.max_retries = 3 # Максимальное количество повторных попыток отправки
        self.base_delay = 1  # Базовая задержка в секундах между попытками

    def split_message(self, message, max_length=4096):
        """Разбивает длинное сообщение на части для Telegram (лимит 4096 символов)"""
        if len(message) <= max_length:
            return [message]
        
        parts = []
        current_part = ""
        lines = message.split('\n')
        
        for line in lines:
            # Если добавление строки не превысит лимит
            if len(current_part) + len(line) + 1 <= max_length:
                if current_part:
                    current_part += '\n' + line
                else:
                    current_part = line
            else:
                # Если текущая часть не пустая, сохраняем её
                if current_part:
                    parts.append(current_part)
                    current_part = line
                else:
                    # Если даже одна строка превышает лимит, обрезаем её
                    parts.append(line[:max_length])
                    current_part = ""
        
        # Добавляем последнюю часть, если она есть
        if current_part:
            parts.append(current_part)
            
        return parts

    def send_message(self, message):
        """Отправка сообщения в Telegram с обработкой 429"""
        # Проверяем режим Dry-run
        if DRY_RUN:
            logger.info(f"[DRY-RUN] Уведомление НЕ отправлено в Telegram: {message[:100]}...")
            return
            
        if not self.bot_token or not self.chat_id:
            logger.warning("Токен бота или ID чата не заданы. Уведомление не отправлено.")
            return
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        # Убедимся, что message - это строка
        if not isinstance(message, str):
             logger.error(f"Попытка отправить сообщение неверного типа: {type(message)}. Ожидалась строка.")
             return
        # Убираем или заменяем недопустимые символы UTF-16 суррогатов
        # Telegram API может не принимать их напрямую
        try:
             # Кодируем и декодируем, заменяя ошибки
             message = message.encode('utf-16', 'surrogatepass').decode('utf-16', 'replace')
        except (UnicodeError, UnicodeEncodeError):
             # Если не удалось, попробуем заменить "плохие" символы
             # Это грубая замена, но может помочь
             message = message.encode('utf-8', 'replace').decode('utf-8', 'replace')
             logger.warning("Обнаружены и заменены проблемные символы UTF в сообщении.")
        # Разбиваем сообщение на части, если оно слишком длинное
        message_parts = self.split_message(message)
        
        for part_index, message_part in enumerate(message_parts):
            # Добавляем номер части, если сообщение разбито
            if len(message_parts) > 1:
                message_part = f"📄 Часть {part_index + 1}/{len(message_parts)}\n\n{message_part}"
            
            data = {
                'chat_id': self.chat_id,
                'text': message_part,
                'parse_mode': 'HTML' # Используем HTML для форматирования
            }
            
            # Отправляем каждую часть отдельно
            self._send_single_message(data, part_index + 1, len(message_parts))
            
            # Небольшая задержка между частями, чтобы избежать rate limiting
            if part_index < len(message_parts) - 1:
                time.sleep(0.5)

    def _send_single_message(self, data, part_number=None, total_parts=None):
        """Отправка одной части сообщения"""
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        
        for attempt in range(self.max_retries):
             try:
                 response = requests.post(url, data=data, timeout=30) # Добавим таймаут
                 response.raise_for_status() # Вызовет исключение для статусов 4xx и 5xx
                 if part_number and total_parts:
                     logger.info(f"Часть {part_number}/{total_parts} успешно отправлена в Telegram.")
                 else:
                     logger.info("Уведомление успешно отправлено в Telegram.")
                 return # Успешно отправлено, выходим из функции
             except requests.exceptions.HTTPError as e:
                 if response.status_code == 429:
                     # Обработка ошибки 429 Too Many Requests
                     logger.warning(f"Получен статус 429 (Too Many Requests) при отправке в Telegram. Попытка {attempt + 1}/{self.max_retries}")
                     # Извлекаем время ожидания из заголовка Retry-After
                     retry_after = None
                     if 'Retry-After' in response.headers:
                         try:
                             retry_after = int(response.headers['Retry-After'])
                             logger.debug(f"Retry-After из заголовка: {retry_after} секунд")
                         except (ValueError, TypeError):
                             logger.warning(f"Невозможно распарсить Retry-After из заголовка: {response.headers.get('Retry-After')}")
                     # Если Retry-After не в заголовке, попробуем найти его в теле ответа (менее стандартно)
                     # Пример тела: {"ok":false,"error_code":429,"description":"Too Many Requests: retry after X","parameters":{"retry_after":X}}
                     if retry_after is None:
                         try:
                             error_data = response.json()
                             if 'parameters' in error_data and 'retry_after' in error_data['parameters']:
                                 retry_after = error_data['parameters']['retry_after']
                                 logger.debug(f"Retry-After из тела ответа: {retry_after} секунд")
                         except (json.JSONDecodeError, KeyError, TypeError):
                             logger.warning("Retry-After не найден ни в заголовках, ни в теле ответа.")
                     # Если не удалось получить retry_after, используем экспоненциальную задержку
                     if retry_after is None:
                         retry_after = self.base_delay * (2 ** attempt) # Экспоненциальная задержка
                         logger.warning(f"Retry-After не определен. Используется экспоненциальная задержка: {retry_after} секунд.")
                     # Добавим небольшой запас к времени ожидания
                     wait_time = retry_after + 1
                     logger.warning(f"Ожидание {wait_time} секунд перед повторной попыткой...")
                     time.sleep(wait_time)
                 else:
                     # Другая HTTP ошибка (не 429)
                     logger.error(f"Ошибка отправки сообщения в Telegram (попытка {attempt + 1}/{self.max_retries}): {e}")
                     if attempt < self.max_retries - 1:
                         # Ждем перед следующей попыткой
                         time.sleep(self.base_delay * (2 ** attempt))
                     # Если это последняя попытка, исключение пробросится дальше
             except requests.exceptions.RequestException as e:
                 # Другая сетевая ошибка (таймаут, DNS, соединение и т.д.)
                 logger.error(f"Сетевая ошибка при отправке сообщения в Telegram (попытка {attempt + 1}/{self.max_retries}): {e}")
                 if attempt < self.max_retries - 1:
                     time.sleep(self.base_delay * (2 ** attempt))
                 # Если это последняя попытка, исключение пробросится дальше
             except Exception as e:
                 # Неожиданная ошибка
                 logger.error(f"Неожиданная ошибка при отправке сообщения в Telegram: {e}", exc_info=True)
                 # В случае неожиданной ошибки, возможно, нет смысла повторять
                 break # Прерываем цикл повторных попыток
        # Если дошли до этой точки, все попытки исчерпаны
        logger.error(f"Не удалось отправить сообщение в Telegram после {self.max_retries} попыток.")

    def get_current_time_msk(self):
        """Получение текущего времени в московском часовом поясе"""
        return datetime.now(MOSCOW_TZ)
    
    def format_crl_number(self, crl_number):
        """Безопасное форматирование серийного номера CRL в hex"""
        if crl_number is None:
            return "Неизвестен"
        try:
            # Если это число, конвертируем в hex
            if isinstance(crl_number, (int, float)):
                return f"{int(crl_number):x}"
            else:
                # Если это строка, пытаемся конвертировать в число, затем в hex
                return f"{int(crl_number):x}"
        except (ValueError, TypeError):
            # Если не удается конвертировать, используем как есть
            return str(crl_number)

    def get_check_time_string(self):
        """Получение строки с временем проверки"""
        return f"🕐 Время проверки: {self.format_datetime(self.get_current_time_msk().isoformat())}"

    def check_notification_enabled(self, notification_type, description):
        """Проверка включения уведомлений с логированием"""
        if not notification_type:
            logger.debug(f"Уведомления {description} отключены в конфигурации.")
            return False
        return True

    def format_datetime(self, dt):
        """Форматирование даты и времени по Московскому времени"""
        if dt:
            try:
                # Если dt - строка, пытаемся преобразовать
                if isinstance(dt, str):
                    dt = datetime.fromisoformat(dt)
                # Конвертируем в московское время
                if dt.tzinfo is None:
                    # Если нет информации о часовом поясе, считаем UTC и конвертируем в Москву
                    dt = dt.replace(tzinfo=timezone.utc).astimezone(MOSCOW_TZ)
                else:
                    # Конвертируем в московское время
                    dt = dt.astimezone(MOSCOW_TZ)
                return dt.strftime('%d.%m.%Y %H:%M:%S')
            except Exception as e:
                logger.error(f"Ошибка форматирования даты: {e}")
                return str(dt)
        return "Не указано"

    def send_expiring_crl_alert(self, crl_name, time_left_hours, next_update, crl_url, size_mb=None, ca_name=None, ca_reg_number=None, crl_fingerprint=None, crl_key_identifier=None, crl_number=None):
        """Уведомление об истекающем CRL"""
        if not self.check_notification_enabled(NOTIFY_EXPIRING_CRL, "об истекающих CRL"):
            return
        now_msk = self.get_current_time_msk()
        # Форматируем серийный номер CRL
        crl_number_formatted = self.format_crl_number(crl_number)
        
        message = (
            f"⚠️ <b>ВНИМАНИЕ: CRL скоро истекает</b>\n"
            f"📁 Имя файла: <code>{crl_name}</code>\n"
            f"🏢 Удостоверяющий центр: <b>{ca_name or 'Неизвестный АУЦ'}</b>\n"
            f"🔢 Реестровый номер: <code>{ca_reg_number or 'Неизвестный номер'}</code>\n"
            f"🔗 URL: <code>{crl_url}</code>\n"
            f"🔢 Серийный номер CRL: <code>{crl_number_formatted}</code>\n"
            f"🔑 Идентификатор ключа издателя: <code>{crl_key_identifier or 'Неизвестен'}</code>\n"
            f"⏰ Осталось: <b>{time_left_hours:.1f} часа</b>\n"
            f"📅 Следующее обновление: {self.format_datetime(next_update)}\n"
            f"🕐 Текущее время: {self.format_datetime(now_msk)}"
        )
        self.send_message(message)

    def send_expired_crl_alert(self, crl_name, expired_time, crl_url, size_mb=None, ca_name=None, ca_reg_number=None, crl_fingerprint=None, crl_key_identifier=None, crl_number=None):
        """Уведомление об истекшем CRL"""
        if not self.check_notification_enabled(NOTIFY_EXPIRED_CRL, "об истекших CRL"):
            return
        now_msk = self.get_current_time_msk()
        # Форматируем серийный номер CRL
        crl_number_formatted = self.format_crl_number(crl_number)
        
        message = (
            f"🚨 <b>КРИТИЧНО: CRL истек</b>\n"
            f"📁 Имя файла: <code>{crl_name}</code>\n"
            f"🏢 Удостоверяющий центр: <b>{ca_name or 'Неизвестный АУЦ'}</b>\n"
            f"🔢 Реестровый номер: <code>{ca_reg_number or 'Неизвестный номер'}</code>\n"
            f"🔗 URL: <code>{crl_url}</code>\n"
            f"🔢 Серийный номер CRL: <code>{crl_number_formatted}</code>\n"
            f"🔑 Идентификатор ключа издателя: <code>{crl_key_identifier or 'Неизвестен'}</code>\n"
            f"⏰ Истек: {self.format_datetime(expired_time)}\n"
            f"🕐 Текущее время: {self.format_datetime(now_msk)}"
        )
        self.send_message(message)

    def send_new_crl_info(self, crl_name, revoked_count, revoked_increase, categories_total, categories_delta, publication_time, crl_number, crl_url, total_revoked, next_update, size_mb=None, ca_name=None, ca_reg_number=None, crl_fingerprint=None, crl_key_identifier=None):
        """Уведомление о новом CRL и приросте отозванных сертификатов"""
        if not self.check_notification_enabled(NOTIFY_NEW_CRL, "о новых CRL"):
            return
        categories_text = ""
        try:
            categories_total = categories_total or {}
            categories_delta = categories_delta or {}
            all_keys = sorted(set(categories_total.keys()) | set(categories_delta.keys()))
            if all_keys:
                lines = []
                for key in all_keys:
                    total_val = int(categories_total.get(key, 0))
                    delta_val = int(categories_delta.get(key, 0))
                    # Показываем прирост только если он положительный и меньше общего значения,
                    # чтобы не дублировать тот же номер (случай первого запуска/полной замены)
                    if delta_val > 0 and delta_val < total_val:
                        lines.append(f"  • {key}: {total_val} (+{delta_val})")
                    else:
                        lines.append(f"  • {key}: {total_val}")
                categories_text = "\n".join(lines)
                logger.info(f"Категории для {crl_name}: total={categories_total}, delta={categories_delta}")
            else:
                logger.warning(f"Категории пустые для {crl_name}")
        except Exception as e:
            logger.error(f"Ошибка формирования текста категорий для {crl_name}: {e}")
        
        # Форматируем номер CRL, убирая ведущие нули
        crl_number_formatted = self.format_crl_number(crl_number)
        
        message = (
            f"🆕 <b>Новая версия CRL опубликована</b>\n"
            f"📁 Имя файла: <code>{crl_name}</code>\n"
            f"🏢 Удостоверяющий центр: <b>{ca_name or 'Неизвестный АУЦ'}</b>\n"
            f"🔢 Реестровый номер: <code>{ca_reg_number or 'Неизвестный номер'}</code>\n"
            f"🔗 URL: <code>{crl_url}</code>\n"
            f"🔢 Серийный номер CRL: <code>{crl_number_formatted}</code>\n"
            f"🔑 Идентификатор ключа издателя: <code>{crl_key_identifier or 'Неизвестен'}</code>\n"
            f"📄 Всего отозвано: <b>{total_revoked}</b>\n"
            f"📈 Прирост: <b>+{revoked_increase}</b>\n"
            f"📅 Время публикации: {self.format_datetime(publication_time)}\n"
            f"📅 Следующее обновление: {self.format_datetime(next_update)}\n"
        )
        
        # Опционально добавляем размер CRL
        if SHOW_CRL_SIZE_MB and size_mb is not None:
            try:
                message += f"📦 Размер CRL: <b>{float(size_mb):.2f} МБ</b>\n"
            except Exception:
                pass
        if categories_text:
            message += f"📊 По категориям:\n{categories_text}"
        self.send_message(message)

    def send_missed_crl_alert(self, crl_name, expected_update_time, crl_url, ca_name=None, ca_reg_number=None):
        """Уведомление о неопубликованном CRL"""
        if not self.check_notification_enabled(NOTIFY_MISSED_CRL, "о пропущенных CRL"):
            return
        now_msk = self.get_current_time_msk()
        message = (
            f"❌ <b>ОШИБКА: CRL не опубликован вовремя</b>\n"
            f"📁 Имя файла: <code>{crl_name}</code>\n"
            f"🏢 Удостоверяющий центр: <b>{ca_name or 'Неизвестный АУЦ'}</b>\n"
            f"🔢 Реестровый номер: <code>{ca_reg_number or 'Неизвестный номер'}</code>\n"
            f"🔗 URL: <code>{crl_url}</code>\n"
            f"📅 Ожидалось: {self.format_datetime(expected_update_time)}\n"
            f"🕐 Текущее время: {self.format_datetime(now_msk)}"
        )
        self.send_message(message)

    def send_weekly_stats(self, stats):
        """Уведомление о недельной статистике"""
        if not self.check_notification_enabled(NOTIFY_WEEKLY_STATS, "о недельной статистике"):
            return
        categories_text = "\n".join([f"  • {cat}: {count}" for cat, count in stats.items()])
        now_msk = self.get_current_time_msk()
        message = (
            f"📊 <b>Недельная статистика отозванных сертификатов</b>\n"
            f"📅 Период: последняя неделя\n"
            f"📈 Прирост по категориям:\n{categories_text}\n"
            f"🕐 Отчет сформирован: {self.format_datetime(now_msk)}"
        )
        self.send_message(message)

    # --- Добавленные методы для уведомлений TSL ---
    def send_tsl_new_ca(self, ca_info):
        """Уведомление о новом действующем АУЦ"""
        if not self.check_notification_enabled(NOTIFY_NEW_CAS, "о новых АУЦ"):
            return
        now_msk = self.get_current_time_msk()
        message = (
            f"🆕 <b>Новый действующий АУЦ</b>\n"
            f"📦 Версия TSL: <b>{ca_info.get('tsl_version', 'Не указана')}</b>\n"
            f"🏢 Название: <b>{ca_info['name']}</b>\n"
            f"🔢 Реестровый номер: <code>{ca_info['reg_number']}</code>\n"
            f"📅 Дата аккредитации: {self.format_datetime(ca_info['effective_date'])}\n"
            f"{self.get_check_time_string()}"
        )
        self.send_message(message)

    def send_tsl_date_change(self, ca_info, old_date, new_date):
        """Уведомление об изменении даты аккредитации АУЦ"""
        if not self.check_notification_enabled(NOTIFY_DATE_CHANGES, "об изменениях дат"):
            return
        now_msk = self.get_current_time_msk()
        message = (
            f"📆 <b>Изменение даты аккредитации АУЦ</b>\n"
            f"📦 Версия TSL: <b>{ca_info.get('tsl_version', 'Не указана')}</b>\n"
            f"🏢 Название: <b>{ca_info['name']}</b>\n"
            f"🔢 Реестровый номер: <code>{ca_info['reg_number']}</code>\n"
            f"📅 Старая дата: {self.format_datetime(old_date)}\n"
            f"📅 Новая дата: {self.format_datetime(new_date)}\n"
            f"{self.get_check_time_string()}"
        )
        self.send_message(message)

    def send_tsl_crl_change(self, ca_info, new_crls):
        """Уведомление о новых или измененных CRL у действующих АУЦ"""
        if not self.check_notification_enabled(NOTIFY_CRL_CHANGES, "об изменениях CRL"):
            return
        now_msk = self.get_current_time_msk()
        crl_list_items = [f"  • <code>{url}</code>" for url in new_crls[:10]]
        if len(new_crls) > 10:
            crl_list_items.append(f"  • ... и еще {len(new_crls) - 10}")
        crl_list = "\n".join(crl_list_items)
        message = (
            f"🔗 <b>Новые или измененные CRL у действующих АУЦ</b>\n"
            f"📦 Версия TSL: <b>{ca_info.get('tsl_version', 'Не указана')}</b>\n"
            f"🏢 Название: <b>{ca_info['name']}</b>\n"
            f"🔢 Реестровый номер: <code>{ca_info['reg_number']}</code>\n"
            f"📄 Новые CRL:\n{crl_list}\n"
            f"{self.get_check_time_string()}"
        )
        self.send_message(message)

    def send_tsl_status_change(self, ca_info, reason):
        """Уведомление об изменении статуса АУЦ"""
        if not self.check_notification_enabled(NOTIFY_STATUS_CHANGES, "об изменениях статуса АУЦ"):
            return
        now_msk = self.get_current_time_msk()
        message = (
            f"❌ <b>Изменение статуса АУЦ</b>\n"
            f"📦 Версия TSL: <b>{ca_info.get('tsl_version', 'Не указана')}</b>\n"
            f"🏢 Название: <b>{ca_info['name']}</b>\n"
            f"🔢 Реестровый номер: <code>{ca_info['reg_number']}</code>\n"
            f"📝 Причина: {reason}\n"
            f"{self.get_check_time_string()}"
        )
        self.send_message(message)

    def send_tsl_removed_ca(self, ca_info):
        """Уведомление об удаленном АУЦ"""
        if not self.check_notification_enabled(NOTIFY_STATUS_CHANGES, "об изменениях статуса АУЦ"):
            return
        now_msk = self.get_current_time_msk()
        message = (
            f"🗑️ <b>АУЦ удален из списка</b>\n"
            f"📦 Версия TSL: <b>{ca_info.get('tsl_version', 'Не указана')}</b>\n"
            f"🏢 Название: <b>{ca_info['name']}</b>\n"
            f"🔢 Реестровый номер: <code>{ca_info['reg_number']}</code>\n"
            f"🏛️ ОГРН: <code>{ca_info.get('ogrn', 'Не указан')}</code>\n"
            f"📝 Причина: {ca_info['reason']}\n"
            f"{self.get_check_time_string()}"
        )
        self.send_message(message)

    def send_tsl_name_change(self, change_info):
        """Уведомление об изменении названия АУЦ"""
        if not self.check_notification_enabled(NOTIFY_STATUS_CHANGES, "об изменениях статуса АУЦ"):
            return
        now_msk = self.get_current_time_msk()
        message = (
            f"📝 <b>Изменение названия АУЦ</b>\n"
            f"📦 Версия TSL: <b>{change_info.get('tsl_version', 'Не указана')}</b>\n"
            f"🔢 Реестровый номер: <code>{change_info['reg_number']}</code>\n"
            f"📄 Было: <b>{change_info['old_name']}</b>\n"
            f"📄 Стало: <b>{change_info['new_name']}</b>\n"
            f"{self.get_check_time_string()}"
        )
        self.send_message(message)

    def send_tsl_ogrn_change(self, change_info):
        """Уведомление об изменении ОГРН АУЦ"""
        if not self.check_notification_enabled(NOTIFY_STATUS_CHANGES, "об изменениях статуса АУЦ"):
            return
        now_msk = self.get_current_time_msk()
        message = (
            f"🏛️ <b>Изменение ОГРН АУЦ</b>\n"
            f"📦 Версия TSL: <b>{change_info.get('tsl_version', 'Не указана')}</b>\n"
            f"🏢 Название: <b>{change_info['name']}</b>\n"
            f"🔢 Реестровый номер: <code>{change_info['reg_number']}</code>\n"
            f"📄 Было: <code>{change_info['old_ogrn']}</code>\n"
            f"📄 Стало: <code>{change_info['new_ogrn']}</code>\n"
            f"{self.get_check_time_string()}"
        )
        self.send_message(message)

    def send_tsl_crl_added(self, change_info):
        """Уведомление о добавлении новых CRL"""
        if not self.check_notification_enabled(NOTIFY_CRL_CHANGES, "об изменениях CRL"):
            return
        now_msk = self.get_current_time_msk()
        crl_list = "\n".join([f"• <code>{crl}</code>" for crl in change_info['crls']])
        # Дополнительные поля из TSL/контекста, если переданы
        crl_number = change_info.get('crl_number')
        crl_number_formatted = "Не указано"
        crl_number_formatted = self.format_crl_number(crl_number)

        issuer_key_id = change_info.get('issuer_key_id') or change_info.get('crl_key_identifier') or 'Не указано'

        ca_tool = change_info.get('ca_tool', 'Не указано')
        ca_tool_class = change_info.get('ca_tool_class', 'Не указано')
        cert_subject = change_info.get('cert_subject', 'Не указано')
        cert_issuer = change_info.get('cert_issuer', 'Не указано')
        cert_serial = change_info.get('cert_serial', 'Не указано')
        cert_validity = change_info.get('cert_validity', 'Не указано')
        cert_fingerprint = change_info.get('cert_fingerprint', 'Не указано')

        message = (
            f"➕ <b>Добавлены новые CRL</b>\n"
            f"📦 Версия TSL: <b>{change_info.get('tsl_version', 'Не указана')}</b>\n"
            f"🏢 АУЦ: <b>{change_info['name']}</b>\n"
            f"🔢 Реестровый номер: <code>{change_info['reg_number']}</code>\n"
            f"🔢 Серийный номер CRL: <code>{crl_number_formatted}</code>\n"
            f"🔑 Идентификатор ключа издателя: <code>{issuer_key_id}</code>\n"
            f"🛠️ Средство УЦ: <b>{ca_tool}</b>\n"
            f"🏷️ Класс средства УЦ: <b>{ca_tool_class}</b>\n"
            f"👤 Кому выдан: <code>{cert_subject}</code>\n"
            f"🏛️ Кем выдан: <code>{cert_issuer}</code>\n"
            f"#️⃣ Серийный номер: <code>{cert_serial}</code>\n"
            f"📅 Действует: <code>{cert_validity}</code>\n"
            f"🔏 Отпечаток: <code>{cert_fingerprint}</code>\n"
            f"📋 Новые CRL:\n{crl_list}\n"
            f"{self.get_check_time_string()}"
        )
        self.send_message(message)

    def send_tsl_crl_removed(self, change_info):
        """Уведомление об удалении CRL"""
        if not self.check_notification_enabled(NOTIFY_CRL_CHANGES, "об изменениях CRL"):
            return
        now_msk = self.get_current_time_msk()
        crl_list = "\n".join([f"• <code>{crl}</code>" for crl in change_info['crls']])
        message = (
            f"➖ <b>Удалены CRL</b>\n"
            f"📦 Версия TSL: <b>{change_info.get('tsl_version', 'Не указана')}</b>\n"
            f"🏢 АУЦ: <b>{change_info['name']}</b>\n"
            f"🔢 Реестровый номер: <code>{change_info['reg_number']}</code>\n"
            f"📋 Удаленные CRL:\n{crl_list}\n"
            f"{self.get_check_time_string()}"
        )
        self.send_message(message)

    def send_tsl_crl_url_change(self, change_info):
        """Уведомление об изменении адресов CRL"""
        if not self.check_notification_enabled(NOTIFY_CRL_CHANGES, "об изменениях CRL"):
            return
        now_msk = self.get_current_time_msk()
        old_urls = "\n".join([f"• <code>{url}</code>" for url in change_info['old_urls']])
        new_urls = "\n".join([f"• <code>{url}</code>" for url in change_info['new_urls']])
        message = (
            f"🔄 <b>Изменены адреса CRL</b>\n"
            f"📦 Версия TSL: <b>{change_info.get('tsl_version', 'Не указана')}</b>\n"
            f"🏢 АУЦ: <b>{change_info['name']}</b>\n"
            f"🔢 Реестровый номер: <code>{change_info['reg_number']}</code>\n"
            f"📄 Было:\n{old_urls}\n"
            f"📄 Стало:\n{new_urls}\n"
            f"{self.get_check_time_string()}"
        )
        self.send_message(message)

    def send_tsl_other_change(self, change_info):
        """Уведомление о других изменениях в TSL"""
        if not self.check_notification_enabled(NOTIFY_STATUS_CHANGES, "об изменениях статуса АУЦ"):
            return
        now_msk = self.get_current_time_msk()
        message = (
            f"📋 <b>Другие изменения в файле TSL</b>\n"
            f"📦 Версия TSL: <b>{change_info.get('tsl_version', 'Не указана')}</b>\n"
            f"🏢 АУЦ: <b>{change_info['name']}</b>\n"
            f"🔢 Реестровый номер: <code>{change_info['reg_number']}</code>\n"
            f"📝 Поле: <b>{change_info['field']}</b>\n"
            f"📄 Было: <code>{change_info['old_value']}</code>\n"
            f"📄 Стало: <code>{change_info['new_value']}</code>\n"
            f"{self.get_check_time_string()}"
        )
        self.send_message(message)

    def send_tsl_short_name_change(self, change_info):
        """Уведомление об изменении краткого названия АУЦ"""
        if not self.check_notification_enabled(NOTIFY_STATUS_CHANGES, "об изменениях статуса АУЦ"):
            return
        now_msk = self.get_current_time_msk()
        message = (
            f"📝 <b>Изменение краткого названия АУЦ</b>\n"
            f"📦 Версия TSL: <b>{change_info.get('tsl_version', 'Не указана')}</b>\n"
            f"🏢 АУЦ: <b>{change_info['name']}</b>\n"
            f"🔢 Реестровый номер: <code>{change_info['reg_number']}</code>\n"
            f"📄 Было: <b>{change_info['old_short_name']}</b>\n"
            f"📄 Стало: <b>{change_info['new_short_name']}</b>\n"
            f"{self.get_check_time_string()}"
        )
        self.send_message(message)

    def send_tsl_inn_change(self, change_info):
        """Уведомление об изменении ИНН АУЦ"""
        if not self.check_notification_enabled(NOTIFY_STATUS_CHANGES, "об изменениях статуса АУЦ"):
            return
        now_msk = self.get_current_time_msk()
        message = (
            f"🏛️ <b>Изменение ИНН АУЦ</b>\n"
            f"📦 Версия TSL: <b>{change_info.get('tsl_version', 'Не указана')}</b>\n"
            f"🏢 Название: <b>{change_info['name']}</b>\n"
            f"🔢 Реестровый номер: <code>{change_info['reg_number']}</code>\n"
            f"📄 Было: <code>{change_info['old_inn']}</code>\n"
            f"📄 Стало: <code>{change_info['new_inn']}</code>\n"
            f"{self.get_check_time_string()}"
        )
        self.send_message(message)

    def send_tsl_email_change(self, change_info):
        """Уведомление об изменении email АУЦ"""
        if not self.check_notification_enabled(NOTIFY_STATUS_CHANGES, "об изменениях статуса АУЦ"):
            return
        now_msk = self.get_current_time_msk()
        message = (
            f"📧 <b>Изменение email АУЦ</b>\n"
            f"📦 Версия TSL: <b>{change_info.get('tsl_version', 'Не указана')}</b>\n"   
            f"🏢 Название: <b>{change_info['name']}</b>\n"
            f"🔢 Реестровый номер: <code>{change_info['reg_number']}</code>\n"
            f"📄 Было: <code>{change_info['old_email']}</code>\n"
            f"📄 Стало: <code>{change_info['new_email']}</code>\n"
            f"{self.get_check_time_string()}"
        )
        self.send_message(message)

    def send_tsl_website_change(self, change_info):
        """Уведомление об изменении веб-сайта АУЦ"""
        if not self.check_notification_enabled(NOTIFY_STATUS_CHANGES, "об изменениях статуса АУЦ"):
            return
        now_msk = self.get_current_time_msk()
        message = (
            f"🌐 <b>Изменение веб-сайта АУЦ</b>\n"
            f"📦 Версия TSL: <b>{change_info.get('tsl_version', 'Не указана')}</b>\n"
            f"🏢 Название: <b>{change_info['name']}</b>\n"
            f"🔢 Реестровый номер: <code>{change_info['reg_number']}</code>\n"
            f"📄 Было: <code>{change_info['old_website']}</code>\n"
            f"📄 Стало: <code>{change_info['new_website']}</code>\n"
            f"{self.get_check_time_string()}"
        )
        self.send_message(message)

    def send_tsl_registry_url_change(self, change_info):
        """Уведомление об изменении URL реестра сертификатов АУЦ"""
        if not self.check_notification_enabled(NOTIFY_STATUS_CHANGES, "об изменениях статуса АУЦ"):
            return
        now_msk = self.get_current_time_msk()
        message = (
            f"📋 <b>Изменение URL реестра сертификатов АУЦ</b>\n"
            f"📦 Версия TSL: <b>{change_info.get('tsl_version', 'Не указана')}</b>\n"
            f"🏢 Название: <b>{change_info['name']}</b>\n"
            f"🔢 Реестровый номер: <code>{change_info['reg_number']}</code>\n"
            f"📄 Было: <code>{change_info['old_registry_url']}</code>\n"
            f"📄 Стало: <code>{change_info['new_registry_url']}</code>\n"
            f"{self.get_check_time_string()}"
        )
        self.send_message(message)

    def send_tsl_address_change(self, change_info):
        """Уведомление об изменении адреса АУЦ"""
        if not self.check_notification_enabled(NOTIFY_STATUS_CHANGES, "об изменениях статуса АУЦ"):
            return
        now_msk = self.get_current_time_msk()
        message = (
            f"📍 <b>Изменение адреса АУЦ</b>\n"
            f"📦 Версия TSL: <b>{change_info.get('tsl_version', 'Не указана')}</b>\n"
            f"🏢 Название: <b>{change_info['name']}</b>\n"
            f"🔢 Реестровый номер: <code>{change_info['reg_number']}</code>\n"
            f"📄 Было: <code>{change_info['old_address']}</code>\n"
            f"📄 Стало: <code>{change_info['new_address']}</code>\n"
            f"{self.get_check_time_string()}"
        )
        self.send_message(message)

    def send_crl_download_failed(self, crl_name, tried_urls, last_error, ca_name=None, ca_reg_number=None, crl_number=None, issuer_key_id=None):
        """Отдельное уведомление: не удалось скачать/найти CRL (по итогам всех попыток)"""
        if not self.check_notification_enabled(NOTIFY_CRL_DOWNLOAD_FAIL, "об ошибках скачивания CRL"):
            return
        now_msk = self.get_current_time_msk()
        url_list = "\n".join([f"• <code>{u}</code>" for u in tried_urls])
        crl_number_formatted = None
        crl_number_formatted = self.format_crl_number(crl_number)
        
        logger.warning(f"Отправка уведомления о провале скачивания CRL: crl_name={crl_name}, urls={tried_urls}, ca={ca_name}, reg={ca_reg_number}")
        message = (
            f"❗ <b>Не удалось скачать CRL — CRL не существует</b>\n"
            f"🏢 АУЦ: <b>{ca_name or 'Неизвестный АУЦ'}</b>\n"
            f"🔢 Реестровый номер: <code>{ca_reg_number or 'Неизвестен'}</code>\n"
            f"📁 Имя файла: <code>{crl_name}</code>\n"
            f"🔗 URL:\n{url_list}\n"
            f"🔢 Серийный номер CRL: <code>{crl_number_formatted or 'Не указано'}</code>\n"
            f"🔑 Идентификатор ключа издателя: <code>{issuer_key_id or 'Не указано'}</code>\n"
            f"{self.get_check_time_string()}"
        )
        self.send_message(message)
