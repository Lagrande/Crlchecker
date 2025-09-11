# ./crl_monitor.py
#!/usr/bin/env python3
import os
import json
import schedule
import time
import logging
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from config import *
from crl_parser import CRLParser
from telegram_notifier import TelegramNotifier
from prometheus_client import Counter, Gauge
from metrics_server import MetricsRegistry

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Путь к файлу с URL CRL из TSL
TSL_CRL_URLS_FILE = os.path.join(DATA_DIR, 'crl_urls_from_tsl.txt')

def ensure_moscow_tz(dt):
    """Убедиться, что datetime имеет московский часовой пояс."""
    if dt and dt.tzinfo is None:
        # Предполагаем, что naive datetime в UTC, затем конвертируем в Москву
        dt = dt.replace(tzinfo=timezone.utc).astimezone(MOSCOW_TZ)
    elif dt:
        # Если уже есть tz, просто конвертируем в Москву
        dt = dt.astimezone(MOSCOW_TZ)
    return dt

class CRLMonitor:
    def __init__(self):
        self.parser = CRLParser(CRL_CACHE_DIR)
        self.notifier = TelegramNotifier()
        self.state = self.load_state()
        self.weekly_stats = self.load_weekly_stats()
        # Для отслеживания уже залогированных пустых CRL
        self.logged_empty_crls = self.load_logged_empty_crls()
        # Метрики
        self.metric_checks_total = Counter('crl_checks_total', 'Total CRL check runs', registry=MetricsRegistry.registry)
        self.metric_processed_total = Counter('crl_processed_total', 'Processed CRL files', ['result'], registry=MetricsRegistry.registry)
        self.metric_unique_urls = Gauge('crl_unique_urls', 'Unique CRL URLs per run', registry=MetricsRegistry.registry)
        self.metric_skipped_empty = Counter('crl_skipped_empty', 'Skipped empty CRLs with long validity', registry=MetricsRegistry.registry)

    def load_state(self):
        """Загрузка состояния из файла"""
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, 'r', encoding='utf-8') as f:
                    raw_state = json.load(f)
                    # Валидация и нормализация дат в состоянии
                    for crl_name, crl_state in raw_state.items():
                        if 'this_update' in crl_state and crl_state['this_update']:
                            try:
                                dt = datetime.fromisoformat(crl_state['this_update'])
                                crl_state['this_update'] = ensure_moscow_tz(dt).isoformat()
                            except ValueError:
                                logger.warning(f"Некорректная дата this_update для {crl_name}: {crl_state['this_update']}")
                        
                        if 'next_update' in crl_state and crl_state['next_update']:
                            try:
                                dt = datetime.fromisoformat(crl_state['next_update'])
                                crl_state['next_update'] = ensure_moscow_tz(dt).isoformat()
                            except ValueError:
                                logger.warning(f"Некорректная дата next_update для {crl_name}: {crl_state['next_update']}")
                        
                        if 'last_check' in crl_state and crl_state['last_check']:
                            try:
                                dt = datetime.fromisoformat(crl_state['last_check'])
                                crl_state['last_check'] = ensure_moscow_tz(dt).isoformat()
                            except ValueError:
                                logger.warning(f"Некорректная дата last_check для {crl_name}: {crl_state['last_check']}")
                        
                        # Проверка last_alerts
                        if 'last_alerts' in crl_state and isinstance(crl_state['last_alerts'], dict):
                            for alert_key, alert_time_str in crl_state['last_alerts'].items():
                                try:
                                    dt = datetime.fromisoformat(alert_time_str)
                                    crl_state['last_alerts'][alert_key] = ensure_moscow_tz(dt).isoformat()
                                except ValueError:
                                    logger.warning(f"Некорректная дата last_alerts[{alert_key}] для {crl_name}: {alert_time_str}")
                    return raw_state
            except Exception as e:
                logger.error(f"Ошибка загрузки состояния: {e}")
        return {}

    def save_state(self):
        """Сохранение состояния в файл"""
        try:
            # Создаем копию состояния для сохранения, чтобы не модифицировать оригинал
            state_to_save = {}
            for k, v in self.state.items():
                state_to_save[k] = v.copy() if isinstance(v, dict) else v
            with open(STATE_FILE, 'w', encoding='utf-8') as f:
                json.dump(state_to_save, f, ensure_ascii=False, indent=2, default=str)
        except Exception as e:
            logger.error(f"Ошибка сохранения состояния: {e}")

    def load_weekly_stats(self):
        """Загрузка недельной статистики"""
        if os.path.exists(STATS_FILE):
            try:
                with open(STATS_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Ошибка загрузки статистики: {e}")
        return {}

    def save_weekly_stats(self):
        """Сохранение недельной статистики"""
        try:
            with open(STATS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.weekly_stats, f, ensure_ascii=False, indent=2, default=str)
        except Exception as e:
            logger.error(f"Ошибка сохранения статистики: {e}")

    def load_logged_empty_crls(self):
        """Загружает список уже залогированных пустых CRL"""
        try:
            with open(os.path.join(DATA_DIR, 'logged_empty_crls.json'), 'r') as f:
                return set(json.load(f))
        except (FileNotFoundError, json.JSONDecodeError):
            return set()

    def save_logged_empty_crls(self):
        """Сохраняет список уже залогированных пустых CRL"""
        try:
            with open(os.path.join(DATA_DIR, 'logged_empty_crls.json'), 'w') as f:
                json.dump(list(self.logged_empty_crls), f)
        except Exception as e:
            logger.error(f"Ошибка сохранения logged_empty_crls: {e}")

    def get_all_crl_urls(self):
        """Получение всех CRL URL: из CDP_SOURCES, KNOWN_CRL_PATHS и из файла TSL_CRL_URLS_FILE"""
        all_urls = set() # Используем set для автоматического удаления дубликатов

        # 1. URL из CDP_SOURCES и KNOWN_CRL_PATHS
        for cdp_url in CDP_SOURCES:
            # Проверяем, нужно ли фильтровать по доменам ФНС
            if FNS_ONLY:
                # В режиме FNS_ONLY обрабатываем только CDP, принадлежащие ФНС
                if any(domain in cdp_url.lower() for domain in FNS_DOMAINS):
                    # Получаем URL напрямую из CDP
                    urls_from_cdp = self.parser.get_crl_urls_from_cdp(cdp_url)
                    # Фильтруем полученные URL по доменам ФНС
                    filtered_urls_from_cdp = {url for url in urls_from_cdp if any(domain in url.lower() for domain in FNS_DOMAINS)}
                    all_urls.update(filtered_urls_from_cdp)
                    logger.info(f"Найдено {len(filtered_urls_from_cdp)} CRL в CDP {cdp_url} (ФНС)")
                    # Добавляем известные пути вручную (тоже фильтруем)
                    for path in KNOWN_CRL_PATHS:
                        full_url = cdp_url.rstrip('/') + '/' + path
                         # Фильтруем и добавляем вручную указанные пути
                        if any(domain in full_url.lower() for domain in FNS_DOMAINS):
                             all_urls.add(full_url)
                else:
                    logger.info(f"CDP источник {cdp_url} не принадлежит доменам ФНС. Пропускаем в режиме FNS_ONLY.")
            else:
                # В режиме "все УЦ" обрабатываем все CDP
                # Получаем URL напрямую из CDP
                urls_from_cdp = self.parser.get_crl_urls_from_cdp(cdp_url)
                all_urls.update(urls_from_cdp)
                logger.info(f"Найдено {len(urls_from_cdp)} CRL в CDP {cdp_url}")
                # Добавляем известные пути вручную (без фильтрации)
                for path in KNOWN_CRL_PATHS:
                    full_url = cdp_url.rstrip('/') + '/' + path
                    all_urls.add(full_url)


        # 2. URL из файла, созданного TSL монитором
        # Обрабатываем файл TSL_CRL_URLS_FILE только если НЕ в режиме FNS_ONLY или если FNS_ONLY=True, но нужно применить фильтр
        if os.path.exists(TSL_CRL_URLS_FILE):
            try:
                with open(TSL_CRL_URLS_FILE, 'r', encoding='utf-8') as f:
                    for line in f:
                        url = line.strip()
                        if url:
                            if FNS_ONLY:
                                # В режиме FNS_ONLY фильтруем URL из файла TSL
                                if any(domain in url.lower() for domain in FNS_DOMAINS):
                                    all_urls.add(url)
                                # else: URL не относится к ФНС, пропускаем
                            else:
                                # В режиме "все УЦ" добавляем все URL из файла TSL
                                all_urls.add(url)
                logger.info(f"Загружено URL CRL из {TSL_CRL_URLS_FILE}. Применен фильтр ФНС: {FNS_ONLY}.")
            except Exception as e:
                logger.error(f"Ошибка чтения URL CRL из {TSL_CRL_URLS_FILE}: {e}")
        else:
            logger.info(f"Файл {TSL_CRL_URLS_FILE} не найден.")

        mode_info = "ФНС" if FNS_ONLY else "Все УЦ"
        logger.info(f"Всего уникальных URL CRL ({mode_info}): {len(all_urls)}")
        return list(all_urls) # Возвращаем список URL

    def _parse_datetime_with_tz(self, dt_str):
        """
        Парсинг строки даты/времени с учетом часового пояса.
        Возвращает None в случае ошибки, а не текущее время.
        """
        if not dt_str:
            return None # <-- Возвращаем None вместо datetime.now()
        try:
            dt = datetime.fromisoformat(dt_str)
            return ensure_moscow_tz(dt)
        except (ValueError, TypeError):
            logger.warning(f"Не удалось распарсить дату: {dt_str}. Возвращено None.")
            return None # <-- Возвращаем None в случае ошибки

    def run_check(self):
        """Основная проверка (высокоуровневая логика)."""
        try:
            logger.info("Начало проверки CRL...")
            self.metric_checks_total.inc()
            crl_urls = self.get_all_crl_urls()

            # Группировка URL по имени файла
            url_groups = defaultdict(list)
            for url in crl_urls:
                filename = os.path.basename(url)
                url_groups[filename].append(url)

            logger.info(f"Найдено {len(url_groups)} уникальных CRL для проверки.")
            self.metric_unique_urls.set(len(url_groups))

            # Обработка каждой группы URL
            for filename, urls_in_group in url_groups.items():
                self.process_crl_group(filename, urls_in_group)

            # Проверка неопубликованных CRL после всех попыток загрузки
            self.check_missed_crl()
            
            # Сохранение состояния после полного цикла проверок
            self.save_state()
            logger.info("Проверка CRL завершена.")

        except Exception as e:
            logger.error(f"Критическая ошибка во время проверки CRL: {e}", exc_info=True)

    def process_crl_group(self, filename, urls):
        """Обрабатывает группу URL-адресов, ведущих к одному и тому же файлу CRL."""
        logger.debug(f"Обработка группы CRL '{filename}' по {len(urls)} URL.")
        crl_processed = False
        last_error = "Неизвестная ошибка"
        last_url_tried = ""

        for url in urls:
            last_url_tried = url
            try:
                # 1. Загрузка CRL
                crl_data = self.parser.download_crl(url)
                if not crl_data:
                    last_error = f"Не удалось загрузить CRL с {url}"
                    continue

                # 2. Парсинг CRL (может вернуть объект cryptography или dict)
                parsed_object = self.parser.parse_crl(crl_data, crl_name=filename)
                if not parsed_object:
                    last_error = f"Не удалось распарсить CRL '{filename}' с {url}"
                    continue

                # 3. Преобразование результата в стандартизированный словарь (crl_info)
                crl_info = None
                if isinstance(parsed_object, dict):
                    crl_info = parsed_object
                    logger.info(f"Информация о CRL '{filename}' получена через резервный парсинг OpenSSL.")
                else:
                    crl_info = self.parser.get_crl_info(parsed_object)
                
                if not crl_info:
                    last_error = f"Не удалось извлечь информацию из CRL '{filename}'"
                    continue
                
                # 4. Проверка на пустой CRL с длительным сроком действия
                if self.should_skip_empty_crl(crl_info, filename):
                    self.metric_skipped_empty.inc()
                    crl_processed = True  # Помечаем как обработанный, чтобы не пробовать другие URL
                    break
                
                # 5. Проверка на Delta CRL
                if crl_info.get('is_delta', False):
                    last_error = f"CRL с {url} является Delta CRL и игнорируется."
                    logger.debug(last_error)
                    continue

                # 6. Обработка, обновление состояния и отправка уведомлений
                self.handle_crl_info(filename, crl_info, url)
                
                crl_processed = True
                self.metric_processed_total.labels(result='success').inc()
                logger.info(f"Успешно обработан CRL '{filename}' с {url}")
                break # Успех, выходим из цикла по зеркалам
                
            except Exception as e:
                last_error = f"Ошибка обработки CRL '{filename}' с {url}: {e}"
                logger.error(last_error, exc_info=True)
                self.metric_processed_total.labels(result='error').inc()
                continue

        if not crl_processed:
            error_msg = f"Не удалось обработать CRL '{filename}' ни с одного из {len(urls)} URL. Последняя ошибка: {last_error}"
            logger.error(error_msg)
            self.metric_processed_total.labels(result='failed_group').inc()

    def should_skip_empty_crl(self, crl_info, filename):
        """Проверяет, нужно ли пропустить пустой CRL с длительным сроком действия"""
        # Проверяем, что CRL пустой (нет отозванных сертификатов)
        if crl_info.get('revoked_count', 0) > 0:
            return False
        
        # Проверяем наличие даты следующего обновления
        next_update = crl_info.get('next_update')
        if not next_update:
            return False
        
        # Нормализуем дату
        if isinstance(next_update, str):
            try:
                next_update = datetime.fromisoformat(next_update)
            except ValueError:
                return False
        
        # Проверяем, что CRL действителен более 3 месяцев
        now = datetime.now(MOSCOW_TZ)
        three_months_later = now + timedelta(days=90)
        
        logger.debug(f"Проверка CRL '{filename}': next_update={next_update}, three_months_later={three_months_later}")
        
        if next_update > three_months_later:
            # Логируем только один раз для каждого CRL
            if filename not in self.logged_empty_crls:
                logger.info(f"Пропуск пустого CRL '{filename}' с длительным сроком действия: "
                           f"действителен до {next_update.strftime('%Y-%m-%d %H:%M:%S')} "
                           f"(более 3 месяцев)")
                self.logged_empty_crls.add(filename)
                self.save_logged_empty_crls()
            return True
        
        return False

    def handle_crl_info(self, filename, crl_info, url):
        """Обрабатывает извлеченную информацию о CRL: проверяет, обновляет состояние, отправляет уведомления."""
        # Нормализация дат
        this_update = ensure_moscow_tz(crl_info.get('this_update'))
        next_update = ensure_moscow_tz(crl_info.get('next_update'))
        
        # Проверка на истечение срока и отправка алертов
        self.check_crl_expiration(filename, next_update, url)

        # Проверка на новую версию и прирост
        self.check_for_new_version(filename, crl_info, url)

        # Обновление состояния
        now_msk = datetime.now(MOSCOW_TZ)
        self.state[filename] = {
            'last_check': now_msk.isoformat(),
            'this_update': this_update.isoformat() if this_update else None,
            'next_update': next_update.isoformat() if next_update else None,
            'revoked_count': crl_info['revoked_count'],
            'crl_number': crl_info.get('crl_number'),
            'last_alerts': self.state.get(filename, {}).get('last_alerts', {}),
            'url': url
        }

    def check_crl_expiration(self, crl_name, next_update_dt, crl_url):
        """Проверяет, истек ли срок действия CRL, и отправляет уведомление, если нужно."""
        if not next_update_dt:
            logger.debug(f"CRL {crl_name} не содержит даты следующего обновления (nextUpdate). Проверка истечения пропущена.")
            return

        now_msk = datetime.now(MOSCOW_TZ)
        time_diff = next_update_dt - now_msk

        # --- НОВАЯ ЛОГИКА: Проверка, не истек ли CRL слишком давно ---
        # Определим порог: если CRL истек более месяца назад, не уведомляем.
        one_month_ago = now_msk - timedelta(days=30)
        
        # next_update_dt - это дата истечения. Если она < one_month_ago,
        # значит CRL истек более месяца назад.
        if next_update_dt < one_month_ago:
            logger.debug(f"CRL '{crl_name}' истек более месяца назад ({next_update_dt}). Уведомление об истечении пропущено.")
            return
        # --- КОНЕЦ НОВОЙ ЛОГИКИ ---

        if time_diff.total_seconds() <= 0:
            # CRL истек. Проверяем, не истек ли он слишком давно (уже проверили выше).
            # Отправляем уведомление об истечении.
            self.notifier.send_expired_crl_alert(crl_name, next_update_dt, crl_url)
            logger.info(f"Отправлен алерт: CRL '{crl_name}' истек ({next_update_dt}).")
            
            # Сохраняем время отправки алерта об истечении, чтобы избежать повторных уведомлений
            # Используем ключ 'alert_expired' для алерта об истечении
            alert_key = 'alert_expired'
            self.state.setdefault(crl_name, {}).setdefault('last_alerts', {})[alert_key] = now_msk.isoformat()
            self.save_state()
            
        else: # CRL еще не истек, проверяем пороги "скоро истечет"
            # Проверка порогов "скоро истекает"
            time_left_seconds = time_diff.total_seconds()
            time_left_hours = time_left_seconds / 3600.0

            alert_sent = False
            # Проверяем каждый порог
            for threshold in sorted(ALERT_THRESHOLDS, reverse=True): # от большего к меньшему
                if time_left_hours <= threshold:
                    alert_key = f'alert_{threshold}h'
                    last_alert_str = self.state.get(crl_name, {}).get('last_alerts', {}).get(alert_key)
                    last_alert_dt = self._parse_datetime_with_tz(last_alert_str)

                    # Проверяем, нужно ли отправлять алерт (если он еще не отправлялся или прошло достаточно времени)
                    should_send_alert = True
                    if last_alert_dt:
                        # Предотвращение повторной отправки в течение короткого времени
                        # Например, если алерт уже был отправлен менее 0.5 часа (30 минут) назад для этого порога
                        time_since_last_alert = now_msk - last_alert_dt
                        if time_since_last_alert.total_seconds() < 1800: # 30 минут в секундах
                            should_send_alert = False
                            
                    if should_send_alert:
                        # ИСПРАВЛЕНО: Правильный порядок аргументов: crl_name, time_left_hours, next_update_dt, crl_url
                        self.notifier.send_expiring_crl_alert(crl_name, time_left_hours, next_update_dt, crl_url)
                        logger.info(f"Отправлен алерт: CRL '{crl_name}' истекает через {time_left_hours:.2f} часов (порог {threshold}h).")
                        # Сохраняем время отправки алерта
                        self.state.setdefault(crl_name, {}).setdefault('last_alerts', {})[alert_key] = now_msk.isoformat()
                        self.save_state() # Сохраняем состояние сразу после обновления
                        alert_sent = True # Отправили алерт для ближайшего порога, выходим
                        break # Выходим из цикла по порогам, так как уже отправили уведомление
            
            # if not alert_sent and time_left_hours > ALERT_THRESHOLDS[-1]:
            #     logger.debug(f"CRL '{crl_name}' в порядке. До истечения более {ALERT_THRESHOLDS[-1]} часов.")

    def check_for_new_version(self, crl_name, crl_info, url):
        """Проверяет, является ли CRL новой версией, и отправляет уведомление."""
        prev_info = self.state.get(crl_name, {})
        prev_crl_number = prev_info.get('crl_number')
        current_crl_number = crl_info.get('crl_number')

        is_new_version = (
            (prev_crl_number is None and current_crl_number is not None) or
            (prev_crl_number is not None and current_crl_number is not None and current_crl_number > prev_crl_number)
        )
        is_first_time = crl_name not in self.state

        if is_new_version or is_first_time:
            previous_count = prev_info.get('revoked_count', 0)
            current_count = crl_info['revoked_count']
            increase = current_count - previous_count

            # Категоризация отозванных сертификатов
            for cert in crl_info.get('revoked_certificates', []):
                if 'revocation_date' in cert and cert['revocation_date']:
                    cert['revocation_date'] = ensure_moscow_tz(cert['revocation_date'])
            categories = self.categorize_revoked_certificates(crl_info.get('revoked_certificates', []))

            self.notifier.send_new_crl_info(
                crl_name,
                current_count,
                increase,
                categories,
                ensure_moscow_tz(crl_info['this_update']),
                current_crl_number,
                url,
                current_count,
                ensure_moscow_tz(crl_info['next_update'])
            )

            # Обновление недельной статистики
            for category, count in categories.items():
                self.weekly_stats[category] = self.weekly_stats.get(category, 0) + count
            self.save_weekly_stats()

    def categorize_revoked_certificates(self, revoked_certs):
        """Категоризация отозванных сертификатов по причине (регистронезависимая, устойчивая к формату)"""
        categories = defaultdict(int)
        
        # Маппинг: ключ - каноническое имя причины (нижний регистр, с подчеркиваниями),
        # значение - отображаемое имя
        # Используем формат с подчеркиваниями, так как он появляется в уведомлениях
        reason_mapping = {
            'unspecified': 'Причина не указана',
            'key_compromise': 'Скомпрометированный закрытый ключ',
            'ca_compromise': 'Компрометация закрытого ключа центра сертификации',
            'affiliation_changed': 'Изменение информации о сертификате',
            'superseded': 'Заменён новым сертификатом',
            'cessation_of_operation': 'Прекращение деятельности',
            'certificate_hold': 'Временная приостановка действия сертификата',
            'remove_from_crl': 'Исключение из списка отозванных сертификатов (CRL)',
            'privilege_withdrawn': 'Ошибочный выпуск',
            'aa_compromise': 'Компрометация удостоверяющего центра'
        }
        
        for cert in revoked_certs:
            reason = cert.get('reason')
            category_key = 'Причина не указана' # Значение по умолчанию
            
            if reason:
                try:
                    # Нормализуем причину к строке и приводим к нижнему регистру
                    if hasattr(reason, 'name'):
                        # Если это Enum из cryptography, например, ReasonFlags.affiliationChanged
                        # Его name будет 'affiliationChanged'. Приводим к 'affiliation_changed'
                        reason_str = reason.name.lower()
                        # ВАЖНО: cryptography использует CamelCase, преобразуем в snake_case
                        # Простой способ (может не подойти для всех случаев, но для ReasonFlags работает):
                        import re
                        reason_str = re.sub(r'(?<!^)(?=[A-Z])', '_', reason_str).lower()
                    elif isinstance(reason, str):
                        reason_str = reason.lower().strip()
                    else:
                        # Если это другой объект, преобразуем в строку
                        reason_str = str(reason).lower().strip()
                except (AttributeError, TypeError) as e:
                    logger.debug(f"Не удалось нормализовать причину {reason}: {e}")
                    reason_str = str(reason).lower().strip() # fallback

                # Проверяем точное совпадение с ключами reason_mapping
                if reason_str in reason_mapping:
                    category_key = reason_mapping[reason_str]
                else:
                    # --- Гибкое сравнение: удаляем подчеркивания и снова сравниваем ---
                    # Это поможет, если reason_str='affiliationchanged',
                    # а ключ в mapping='affiliation_changed'
                    reason_str_no_underscores = reason_str.replace('_', '')
                    matched_key = None
                    for map_key in reason_mapping:
                        if map_key.replace('_', '') == reason_str_no_underscores:
                            matched_key = map_key
                            break
                    
                    if matched_key:
                        category_key = reason_mapping[matched_key]
                    else:
                        # Если не нашли, используем оригинальную причину
                        # Ограничиваем длину ключа для читаемости
                        category_key = reason_str[:50] if len(reason_str) > 50 else reason_str

            categories[category_key] += 1 # Используем category_key как ключ в счетчике
        
        return dict(categories)

    def check_missed_crl(self):
        """Проверка неопубликованных CRL"""
        now_msk = datetime.now(MOSCOW_TZ)
        for crl_name, crl_state in self.state.items():
            # --- НОВАЯ ЛОГИКА ФИЛЬТРАЦИИ ---
            # Получаем URL из состояния для проверки принадлежности к ФНС
            crl_url = crl_state.get('url', '')
            # Если включен режим FNS_ONLY, проверяем принадлежность CRL к ФНС
            if FNS_ONLY and crl_url:
                # Проверяем, принадлежит ли URL доменам ФНС
                if not any(domain in crl_url.lower() for domain in FNS_DOMAINS):
                    # URL не принадлежит ФНС, пропускаем проверку в режиме FNS_ONLY
                    logger.debug(f"Пропущена проверка неопубликованного CRL '{crl_name}' ({crl_url}) в режиме FNS_ONLY.")
                    continue
            # --- КОНЕЦ НОВОЙ ЛОГИКИ ---
            next_update_str = crl_state.get('next_update')
            # crl_url уже получен выше
            if next_update_str:
                try:
                    # Используем _parse_datetime_with_tz для парсинга времени из состояния
                    next_update_dt = self._parse_datetime_with_tz(next_update_str)
                    # --- НОВАЯ ЛОГИКА: Проверка, не слишком ли старое ожидание ---
                    # Определим порог: если CRL ожидался больше месяца назад, не уведомляем.
                    one_month_ago = now_msk - timedelta(days=30)
                    # next_update_dt - это дата ожидаемого обновления. Если она < one_month_ago,
                    # значит CRL ожидался более месяца назад.
                    if next_update_dt < one_month_ago:
                        logger.debug(f"CRL '{crl_name}' ожидался более месяца назад ({next_update_dt}). Уведомление о пропущенном CRL пропущено.")
                        continue # Пропускаем уведомление
                    # --- КОНЕЦ НОВОЙ ЛОГИКИ ---
                    # Вычисляем time_left внутри try
                    time_left = next_update_dt - now_msk
                    if time_left.total_seconds() < -3600: # Если прошло больше часа после ожидаемого обновления
                        # Проверяем, не было ли уже уведомления об этом пропуске
                        last_missed_alert = crl_state.get('last_alerts', {}).get('missed')
                        if not last_missed_alert or (now_msk - self._parse_datetime_with_tz(last_missed_alert)).total_seconds() > 86400: # 24 часа
                            # Передаем crl_url в уведомление
                            self.notifier.send_missed_crl_alert(crl_name, next_update_dt, crl_url)
                            if 'last_alerts' not in crl_state:
                                crl_state['last_alerts'] = {}
                            crl_state['last_alerts']['missed'] = now_msk.isoformat()
                except Exception as e:
                    logger.error(f"Ошибка обработки времени для CRL {crl_name} ({crl_url}): {e}")
            # else: next_update_str отсутствует, пропускаем проверку для этой записи
            
    def send_weekly_stats(self):
        """Отправка недельной статистики"""
        if self.weekly_stats:
            self.notifier.send_weekly_stats(self.weekly_stats)
            # Сброс статистики
            self.weekly_stats = {}
            self.save_weekly_stats()

    def run_check(self):
        """Основная проверка (высокоуровневая логика)."""
        try:
            logger.info("Начало проверки CRL...")
            crl_urls = self.get_all_crl_urls()

            # Группировка URL по имени файла
            url_groups = defaultdict(list)
            for url in crl_urls:
                filename = os.path.basename(url)
                url_groups[filename].append(url)

            logger.info(f"Найдено {len(url_groups)} уникальных CRL для проверки.")

            # Обработка каждой группы URL
            for filename, urls_in_group in url_groups.items():
                self.process_crl_group(filename, urls_in_group)

            # Проверка неопубликованных CRL после всех попыток загрузки
            self.check_missed_crl()
            
            # Сохранение состояния после полного цикла проверок
            self.save_state()
            logger.info("Проверка CRL завершена.")

        except Exception as e:
            logger.error(f"Критическая ошибка во время проверки CRL: {e}", exc_info=True)

    def process_crl_group(self, filename, urls):
        """Обрабатывает группу URL-адресов, ведущих к одному и тому же файлу CRL."""
        logger.debug(f"Обработка группы CRL '{filename}' по {len(urls)} URL.")
        crl_processed = False
        last_error = "Неизвестная ошибка"
        last_url_tried = ""

        for url in urls:
            last_url_tried = url
            try:
                # 1. Загрузка CRL
                crl_data = self.parser.download_crl(url)
                if not crl_data:
                    last_error = f"Не удалось загрузить CRL с {url}"
                    continue

                # 2. Парсинг CRL (может вернуть объект cryptography или dict)
                parsed_object = self.parser.parse_crl(crl_data, crl_name=filename)
                if not parsed_object:
                    last_error = f"Не удалось распарсить CRL '{filename}' с {url}"
                    continue

                # 3. Преобразование результата в стандартизированный словарь (crl_info)
                crl_info = None
                if isinstance(parsed_object, dict):
                    crl_info = parsed_object
                    logger.info(f"Информация о CRL '{filename}' получена через резервный парсинг OpenSSL.")
                else:
                    crl_info = self.parser.get_crl_info(parsed_object)
                
                if not crl_info:
                    last_error = f"Не удалось извлечь информацию из CRL '{filename}'"
                    continue
                
                # 4. Проверка на Delta CRL
                if crl_info.get('is_delta', False):
                    last_error = f"CRL с {url} является Delta CRL и игнорируется."
                    logger.debug(last_error)
                    continue

                # 5. Обработка, обновление состояния и отправка уведомлений
                self.handle_crl_info(filename, crl_info, url)
                
                crl_processed = True
                logger.info(f"Успешно обработан CRL '{filename}' с {url}")
                break # Успех, выходим из цикла по зеркалам
                
            except Exception as e:
                last_error = f"Ошибка обработки CRL '{filename}' с {url}: {e}"
                logger.error(last_error, exc_info=True)
                continue

        if not crl_processed:
            error_msg = f"Не удалось обработать CRL '{filename}' ни с одного из {len(urls)} URL. Последняя ошибка: {last_error}"
            logger.error(error_msg)

    def handle_crl_info(self, filename, crl_info, url):
        """Обрабатывает извлеченную информацию о CRL: проверяет, обновляет состояние, отправляет уведомления."""
        # Нормализация дат
        this_update = ensure_moscow_tz(crl_info.get('this_update'))
        next_update = ensure_moscow_tz(crl_info.get('next_update'))
        
        # Проверка на истечение срока и отправка алертов
        self.check_crl_expiration(filename, next_update, url)

        # Проверка на новую версию и прирост
        self.check_for_new_version(filename, crl_info, url)

        # Обновление состояния
        now_msk = datetime.now(MOSCOW_TZ)
        self.state[filename] = {
            'last_check': now_msk.isoformat(),
            'this_update': this_update.isoformat() if this_update else None,
            'next_update': next_update.isoformat() if next_update else None,
            'revoked_count': crl_info['revoked_count'],
            'crl_number': crl_info.get('crl_number'),
            'last_alerts': self.state.get(filename, {}).get('last_alerts', {}),
            'url': url
        }

    def check_for_new_version(self, crl_name, crl_info, url):
        """Проверяет, является ли CRL новой версией, и отправляет уведомление."""
        prev_info = self.state.get(crl_name, {})
        prev_crl_number = prev_info.get('crl_number')
        current_crl_number = crl_info.get('crl_number')

        is_new_version = (
            (prev_crl_number is None and current_crl_number is not None) or
            (prev_crl_number is not None and current_crl_number is not None and current_crl_number > prev_crl_number)
        )
        is_first_time = crl_name not in self.state

        if is_new_version or is_first_time:
            previous_count = prev_info.get('revoked_count', 0)
            current_count = crl_info['revoked_count']
            increase = current_count - previous_count

            # Категоризация отозванных сертификатов
            for cert in crl_info.get('revoked_certificates', []):
                if 'revocation_date' in cert and cert['revocation_date']:
                    cert['revocation_date'] = ensure_moscow_tz(cert['revocation_date'])
            categories = self.categorize_revoked_certificates(crl_info.get('revoked_certificates', []))

            self.notifier.send_new_crl_info(
                crl_name,
                current_count,
                increase,
                categories,
                ensure_moscow_tz(crl_info['this_update']),
                current_crl_number,
                url,
                current_count,
                ensure_moscow_tz(crl_info['next_update'])
            )

            # Обновление недельной статистики
            for category, count in categories.items():
                self.weekly_stats[category] = self.weekly_stats.get(category, 0) + count
            self.save_weekly_stats()

    def setup_schedule(self):
        """Настройка расписания"""
        # Основная проверка
        schedule.every(CHECK_INTERVAL).minutes.do(self.run_check)
        # Недельная статистика по воскресеньям в 23:59
        schedule.every().sunday.at("23:59").do(self.send_weekly_stats)

    def run(self):
        """Запуск монитора"""
        logger.info("Запуск CRL Monitor")
        # Первая проверка
        self.run_check()
        # Настройка расписания
        self.setup_schedule()
        # Основной цикл
        while True:
            try:
                schedule.run_pending()
                time.sleep(60)
            except KeyboardInterrupt:
                logger.info("Получен сигнал завершения")
                break
            except Exception as e:
                logger.error(f"Ошибка в основном цикле: {e}")
                time.sleep(60)

if __name__ == "__main__":
    monitor = CRLMonitor()
    monitor.run()
