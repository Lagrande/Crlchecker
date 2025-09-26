# ./telegram_notifier.py
import requests
import logging
from datetime import datetime
import time  # <-- Новый импорт
import re    # <-- Новый импорт (на всякий случай, если Retry-After будет в body)
from config import *

logger = logging.getLogger(__name__)

class TelegramNotifier:
    def __init__(self):
        self.bot_token = TELEGRAM_BOT_TOKEN
        self.chat_id = TELEGRAM_CHAT_ID
        self.max_retries = 3 # Максимальное количество повторных попыток отправки
        self.base_delay = 1  # Базовая задержка в секундах между попытками

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
        data = {
            'chat_id': self.chat_id,
            'text': message,
            'parse_mode': 'HTML' # Используем HTML для форматирования
        }
        for attempt in range(self.max_retries):
             try:
                 response = requests.post(url, data=data, timeout=30) # Добавим таймаут
                 response.raise_for_status() # Вызовет исключение для статусов 4xx и 5xx
                 logger.warning("Уведомление успешно отправлено в Telegram.")
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
                             import json
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
                    from datetime import timezone
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
        if not NOTIFY_EXPIRING_CRL:
            logger.debug("Уведомления об истекающих CRL отключены в конфигурации.")
            return
        now_msk = datetime.now(MOSCOW_TZ)
        # Форматируем серийный номер CRL
        crl_number_formatted = "Неизвестен" if crl_number is None else f"{crl_number:x}"
        
        message = (
            f"⚠️ <b>ВНИМАНИЕ: CRL скоро истекает</b>\n"
            f"📁 Имя файла: <code>{crl_name}</code>\n"
            f"🏢 Удостоверяющий центр: <b>{ca_name or 'Неизвестный УЦ'}</b>\n"
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
        if not NOTIFY_EXPIRED_CRL:
            logger.debug("Уведомления об истекших CRL отключены в конфигурации.")
            return
        now_msk = datetime.now(MOSCOW_TZ)
        # Форматируем серийный номер CRL
        crl_number_formatted = "Неизвестен" if crl_number is None else f"{crl_number:x}"
        
        message = (
            f"🚨 <b>КРИТИЧНО: CRL истек</b>\n"
            f"📁 Имя файла: <code>{crl_name}</code>\n"
            f"🏢 Удостоверяющий центр: <b>{ca_name or 'Неизвестный УЦ'}</b>\n"
            f"🔢 Реестровый номер: <code>{ca_reg_number or 'Неизвестный номер'}</code>\n"
            f"🔗 URL: <code>{crl_url}</code>\n"
            f"🔢 Серийный номер CRL: <code>{crl_number_formatted}</code>\n"
            f"🔑 Идентификатор ключа издателя: <code>{crl_key_identifier or 'Неизвестен'}</code>\n"
            f"⏰ Истек: {self.format_datetime(expired_time)}\n"
            f"🕐 Текущее время: {self.format_datetime(now_msk)}"
        )
        self.send_message(message)

    def send_new_crl_info(self, crl_name, revoked_count, revoked_increase, categories, publication_time, crl_number, crl_url, total_revoked, next_update, size_mb=None, ca_name=None, ca_reg_number=None, crl_fingerprint=None, crl_key_identifier=None):
        """Уведомление о новом CRL и приросте отозванных сертификатов"""
        if not NOTIFY_NEW_CRL:
            logger.debug("Уведомления о новых CRL отключены в конфигурации.")
            return
        categories_text = ""
        if categories:
            categories_text = "\n".join([f"  • {cat}: {count}" for cat, count in sorted(categories.items())])
        
        # Форматируем номер CRL, убирая ведущие нули
        if crl_number is None:
            crl_number_formatted = "Неизвестен"
        else:
            # Убираем ведущие нули из hex представления
            crl_number_formatted = f"{crl_number:x}"
        
        message = (
            f"🆕 <b>Новая версия CRL опубликована</b>\n"
            f"📁 Имя файла: <code>{crl_name}</code>\n"
            f"🏢 Удостоверяющий центр: <b>{ca_name or 'Неизвестный УЦ'}</b>\n"
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
        if not NOTIFY_MISSED_CRL:
            logger.debug("Уведомления о пропущенных CRL отключены в конфигурации.")
            return
        now_msk = datetime.now(MOSCOW_TZ)
        message = (
            f"❌ <b>ОШИБКА: CRL не опубликован вовремя</b>\n"
            f"📁 Имя файла: <code>{crl_name}</code>\n"
            f"🏢 Удостоверяющий центр: <b>{ca_name or 'Неизвестный УЦ'}</b>\n"
            f"🔢 Реестровый номер: <code>{ca_reg_number or 'Неизвестный номер'}</code>\n"
            f"🔗 URL: <code>{crl_url}</code>\n"
            f"📅 Ожидалось: {self.format_datetime(expected_update_time)}\n"
            f"🕐 Текущее время: {self.format_datetime(now_msk)}"
        )
        self.send_message(message)

    def send_weekly_stats(self, stats):
        """Уведомление о недельной статистике"""
        if not NOTIFY_WEEKLY_STATS:
            logger.debug("Уведомления о недельной статистике отключены в конфигурации.")
            return
        categories_text = "\n".join([f"  • {cat}: {count}" for cat, count in stats.items()])
        now_msk = datetime.now(MOSCOW_TZ)
        message = (
            f"📊 <b>Недельная статистика отозванных сертификатов</b>\n"
            f"📅 Период: последняя неделя\n"
            f"📈 Прирост по категориям:\n{categories_text}\n"
            f"🕐 Отчет сформирован: {self.format_datetime(now_msk)}"
        )
        self.send_message(message)

    # --- Добавленные методы для уведомлений TSL ---
    def send_tsl_new_ca(self, ca_info):
        """Уведомление о новом действующем УЦ"""
        if not NOTIFY_NEW_CAS:
            logger.debug("Уведомления о новых УЦ отключены в конфигурации.")
            return
        now_msk = datetime.now(MOSCOW_TZ)
        message = (
            f"🆕 <b>Новый действующий УЦ в TSL</b>\n"
            f"🏢 Название: <b>{ca_info['name']}</b>\n"
            f"🔢 Реестровый номер: <code>{ca_info['reg_number']}</code>\n"
            f"📅 Дата аккредитации: {self.format_datetime(ca_info['effective_date'])}\n"
            f"🕐 Время проверки: {self.format_datetime(now_msk.isoformat())}"
        )
        self.send_message(message)

    def send_tsl_date_change(self, ca_info, old_date, new_date):
        """Уведомление об изменении даты аккредитации УЦ"""
        if not NOTIFY_DATE_CHANGES:
            logger.debug("Уведомления об изменениях дат отключены в конфигурации.")
            return
        now_msk = datetime.now(MOSCOW_TZ)
        message = (
            f"📆 <b>Изменение даты аккредитации УЦ</b>\n"
            f"🏢 Название: <b>{ca_info['name']}</b>\n"
            f"🔢 Реестровый номер: <code>{ca_info['reg_number']}</code>\n"
            f"📅 Старая дата: {self.format_datetime(old_date)}\n"
            f"📅 Новая дата: {self.format_datetime(new_date)}\n"
            f"🕐 Время проверки: {self.format_datetime(now_msk.isoformat())}"
        )
        self.send_message(message)

    def send_tsl_crl_change(self, ca_info, new_crls):
        """Уведомление о новых или измененных CRL у действующих УЦ"""
        if not NOTIFY_CRL_CHANGES:
            logger.debug("Уведомления об изменениях CRL отключены в конфигурации.")
            return
        now_msk = datetime.now(MOSCOW_TZ)
        crl_list_items = [f"  • <code>{url}</code>" for url in new_crls[:10]]
        if len(new_crls) > 10:
            crl_list_items.append(f"  • ... и еще {len(new_crls) - 10}")
        crl_list = "\n".join(crl_list_items)
        message = (
            f"🔗 <b>Новые или измененные CRL у действующих УЦ</b>\n"
            f"🏢 Название: <b>{ca_info['name']}</b>\n"
            f"🔢 Реестровый номер: <code>{ca_info['reg_number']}</code>\n"
            f"📄 Новые CRL:\n{crl_list}\n"
            f"🕐 Время проверки: {self.format_datetime(now_msk.isoformat())}"
        )
        self.send_message(message)

    def send_tsl_status_change(self, ca_info, reason):
        """Уведомление об изменении статуса УЦ"""
        if not NOTIFY_STATUS_CHANGES:
            logger.debug("Уведомления об изменениях статуса УЦ отключены в конфигурации.")
            return
        now_msk = datetime.now(MOSCOW_TZ)
        message = (
            f"❌ <b>Изменение статуса УЦ</b>\n"
            f"🏢 Название: <b>{ca_info['name']}</b>\n"
            f"🔢 Реестровый номер: <code>{ca_info['reg_number']}</code>\n"
            f"📝 Причина: {reason}\n"
            f"🕐 Время проверки: {self.format_datetime(now_msk.isoformat())}"
        )
        self.send_message(message)
    def send_tsl_status_change(self, ca_info, reason):
        """Уведомление об изменении статуса УЦ"""
        if not NOTIFY_STATUS_CHANGES:
            logger.debug("Уведомления об изменениях статуса УЦ отключены в конфигурации.")
            return
        now_msk = datetime.now(MOSCOW_TZ)
        message = (
            f"❌ <b>Изменение статуса УЦ</b>\n"
            f"🏢 Название: <b>{ca_info['name']}</b>\n"
            f"🔢 Реестровый номер: <code>{ca_info['reg_number']}</code>\n"
            f"📝 Причина: {reason}\n"
            f"🕐 Время проверки: {self.format_datetime(now_msk.isoformat())}"
        )
        self.send_message(message)

    def send_tsl_removed_ca(self, ca_info):
        """Уведомление об удаленном УЦ"""
        if not NOTIFY_STATUS_CHANGES:
            logger.debug("Уведомления об изменениях статуса УЦ отключены в конфигурации.")
            return
        now_msk = datetime.now(MOSCOW_TZ)
        message = (
            f"🗑️ <b>УЦ удален из списка</b>\n"
            f"🏢 Название: <b>{ca_info['name']}</b>\n"
            f"🔢 Реестровый номер: <code>{ca_info['reg_number']}</code>\n"
            f"🏛️ ОГРН: <code>{ca_info.get('ogrn', 'Не указан')}</code>\n"
            f"📝 Причина: {ca_info['reason']}\n"
            f"🕐 Время проверки: {self.format_datetime(now_msk.isoformat())}"
        )
        self.send_message(message)

    def send_tsl_name_change(self, change_info):
        """Уведомление об изменении названия УЦ"""
        if not NOTIFY_STATUS_CHANGES:
            logger.debug("Уведомления об изменениях статуса УЦ отключены в конфигурации.")
            return
        now_msk = datetime.now(MOSCOW_TZ)
        message = (
            f"📝 <b>Изменение названия УЦ</b>\n"
            f"🔢 Реестровый номер: <code>{change_info['reg_number']}</code>\n"
            f"📄 Было: <b>{change_info['old_name']}</b>\n"
            f"📄 Стало: <b>{change_info['new_name']}</b>\n"
            f"🕐 Время проверки: {self.format_datetime(now_msk.isoformat())}"
        )
        self.send_message(message)

    def send_tsl_ogrn_change(self, change_info):
        """Уведомление об изменении ОГРН УЦ"""
        if not NOTIFY_STATUS_CHANGES:
            logger.debug("Уведомления об изменениях статуса УЦ отключены в конфигурации.")
            return
        now_msk = datetime.now(MOSCOW_TZ)
        message = (
            f"🏛️ <b>Изменение ОГРН УЦ</b>\n"
            f"🏢 Название: <b>{change_info['name']}</b>\n"
            f"🔢 Реестровый номер: <code>{change_info['reg_number']}</code>\n"
            f"📄 Было: <code>{change_info['old_ogrn']}</code>\n"
            f"📄 Стало: <code>{change_info['new_ogrn']}</code>\n"
            f"🕐 Время проверки: {self.format_datetime(now_msk.isoformat())}"
        )
        self.send_message(message)

    def send_tsl_crl_added(self, change_info):
        """Уведомление о добавлении новых CRL"""
        if not NOTIFY_CRL_CHANGES:
            logger.debug("Уведомления об изменениях CRL отключены в конфигурации.")
            return
        now_msk = datetime.now(MOSCOW_TZ)
        crl_list = "\n".join([f"• <code>{crl}</code>" for crl in change_info['crls']])
        message = (
            f"➕ <b>Добавлены новые CRL</b>\n"
            f"🏢 УЦ: <b>{change_info['name']}</b>\n"
            f"🔢 Реестровый номер: <code>{change_info['reg_number']}</code>\n"
            f"📋 Новые CRL:\n{crl_list}\n"
            f"🕐 Время проверки: {self.format_datetime(now_msk.isoformat())}"
        )
        self.send_message(message)

    def send_tsl_crl_removed(self, change_info):
        """Уведомление об удалении CRL"""
        if not NOTIFY_CRL_CHANGES:
            logger.debug("Уведомления об изменениях CRL отключены в конфигурации.")
            return
        now_msk = datetime.now(MOSCOW_TZ)
        crl_list = "\n".join([f"• <code>{crl}</code>" for crl in change_info['crls']])
        message = (
            f"➖ <b>Удалены CRL</b>\n"
            f"🏢 УЦ: <b>{change_info['name']}</b>\n"
            f"🔢 Реестровый номер: <code>{change_info['reg_number']}</code>\n"
            f"📋 Удаленные CRL:\n{crl_list}\n"
            f"🕐 Время проверки: {self.format_datetime(now_msk.isoformat())}"
        )
        self.send_message(message)

    def send_tsl_crl_url_change(self, change_info):
        """Уведомление об изменении адресов CRL"""
        if not NOTIFY_CRL_CHANGES:
            logger.debug("Уведомления об изменениях CRL отключены в конфигурации.")
            return
        now_msk = datetime.now(MOSCOW_TZ)
        old_urls = "\n".join([f"• <code>{url}</code>" for url in change_info['old_urls']])
        new_urls = "\n".join([f"• <code>{url}</code>" for url in change_info['new_urls']])
        message = (
            f"🔄 <b>Изменены адреса CRL</b>\n"
            f"🏢 УЦ: <b>{change_info['name']}</b>\n"
            f"🔢 Реестровый номер: <code>{change_info['reg_number']}</code>\n"
            f"📄 Было:\n{old_urls}\n"
            f"📄 Стало:\n{new_urls}\n"
            f"🕐 Время проверки: {self.format_datetime(now_msk.isoformat())}"
        )
        self.send_message(message)

    def send_tsl_other_change(self, change_info):
        """Уведомление о других изменениях в TSL"""
        if not NOTIFY_STATUS_CHANGES:
            logger.debug("Уведомления об изменениях статуса УЦ отключены в конфигурации.")
            return
        now_msk = datetime.now(MOSCOW_TZ)
        message = (
            f"📋 <b>Другие изменения в TSL</b>\n"
            f"🏢 УЦ: <b>{change_info['name']}</b>\n"
            f"🔢 Реестровый номер: <code>{change_info['reg_number']}</code>\n"
            f"📝 Поле: <b>{change_info['field']}</b>\n"
            f"📄 Было: <code>{change_info['old_value']}</code>\n"
            f"📄 Стало: <code>{change_info['new_value']}</code>\n"
            f"🕐 Время проверки: {self.format_datetime(now_msk.isoformat())}"
        )
        self.send_message(message)

    def send_tsl_short_name_change(self, change_info):
        """Уведомление об изменении краткого названия УЦ"""
        if not NOTIFY_STATUS_CHANGES:
            logger.debug("Уведомления об изменениях статуса УЦ отключены в конфигурации.")
            return
        now_msk = datetime.now(MOSCOW_TZ)
        message = (
            f"📝 <b>Изменение краткого названия УЦ</b>\n"
            f"🏢 УЦ: <b>{change_info['name']}</b>\n"
            f"🔢 Реестровый номер: <code>{change_info['reg_number']}</code>\n"
            f"📄 Было: <b>{change_info['old_short_name']}</b>\n"
            f"📄 Стало: <b>{change_info['new_short_name']}</b>\n"
            f"🕐 Время проверки: {self.format_datetime(now_msk.isoformat())}"
        )
        self.send_message(message)

    def send_tsl_inn_change(self, change_info):
        """Уведомление об изменении ИНН УЦ"""
        if not NOTIFY_STATUS_CHANGES:
            logger.debug("Уведомления об изменениях статуса УЦ отключены в конфигурации.")
            return
        now_msk = datetime.now(MOSCOW_TZ)
        message = (
            f"🏛️ <b>Изменение ИНН УЦ</b>\n"
            f"🏢 Название: <b>{change_info['name']}</b>\n"
            f"🔢 Реестровый номер: <code>{change_info['reg_number']}</code>\n"
            f"📄 Было: <code>{change_info['old_inn']}</code>\n"
            f"📄 Стало: <code>{change_info['new_inn']}</code>\n"
            f"🕐 Время проверки: {self.format_datetime(now_msk.isoformat())}"
        )
        self.send_message(message)

    def send_tsl_email_change(self, change_info):
        """Уведомление об изменении email УЦ"""
        if not NOTIFY_STATUS_CHANGES:
            logger.debug("Уведомления об изменениях статуса УЦ отключены в конфигурации.")
            return
        now_msk = datetime.now(MOSCOW_TZ)
        message = (
            f"📧 <b>Изменение email УЦ</b>\n"
            f"🏢 Название: <b>{change_info['name']}</b>\n"
            f"🔢 Реестровый номер: <code>{change_info['reg_number']}</code>\n"
            f"📄 Было: <code>{change_info['old_email']}</code>\n"
            f"📄 Стало: <code>{change_info['new_email']}</code>\n"
            f"🕐 Время проверки: {self.format_datetime(now_msk.isoformat())}"
        )
        self.send_message(message)

    def send_tsl_website_change(self, change_info):
        """Уведомление об изменении веб-сайта УЦ"""
        if not NOTIFY_STATUS_CHANGES:
            logger.debug("Уведомления об изменениях статуса УЦ отключены в конфигурации.")
            return
        now_msk = datetime.now(MOSCOW_TZ)
        message = (
            f"🌐 <b>Изменение веб-сайта УЦ</b>\n"
            f"🏢 Название: <b>{change_info['name']}</b>\n"
            f"🔢 Реестровый номер: <code>{change_info['reg_number']}</code>\n"
            f"📄 Было: <code>{change_info['old_website']}</code>\n"
            f"📄 Стало: <code>{change_info['new_website']}</code>\n"
            f"🕐 Время проверки: {self.format_datetime(now_msk.isoformat())}"
        )
        self.send_message(message)

    def send_tsl_registry_url_change(self, change_info):
        """Уведомление об изменении URL реестра сертификатов УЦ"""
        if not NOTIFY_STATUS_CHANGES:
            logger.debug("Уведомления об изменениях статуса УЦ отключены в конфигурации.")
            return
        now_msk = datetime.now(MOSCOW_TZ)
        message = (
            f"📋 <b>Изменение URL реестра сертификатов УЦ</b>\n"
            f"🏢 Название: <b>{change_info['name']}</b>\n"
            f"🔢 Реестровый номер: <code>{change_info['reg_number']}</code>\n"
            f"📄 Было: <code>{change_info['old_registry_url']}</code>\n"
            f"📄 Стало: <code>{change_info['new_registry_url']}</code>\n"
            f"🕐 Время проверки: {self.format_datetime(now_msk.isoformat())}"
        )
        self.send_message(message)

    def send_tsl_address_change(self, change_info):
        """Уведомление об изменении адреса УЦ"""
        if not NOTIFY_STATUS_CHANGES:
            logger.debug("Уведомления об изменениях статуса УЦ отключены в конфигурации.")
            return
        now_msk = datetime.now(MOSCOW_TZ)
        message = (
            f"📍 <b>Изменение адреса УЦ</b>\n"
            f"🏢 Название: <b>{change_info['name']}</b>\n"
            f"🔢 Реестровый номер: <code>{change_info['reg_number']}</code>\n"
            f"📄 Было: <code>{change_info['old_address']}</code>\n"
            f"📄 Стало: <code>{change_info['new_address']}</code>\n"
            f"🕐 Время проверки: {self.format_datetime(now_msk.isoformat())}"
        )
        self.send_message(message)
