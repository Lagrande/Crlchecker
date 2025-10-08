# ./tsl_monitor.py
import requests
import sys
import xml.etree.ElementTree as ET
import json
import os
import logging
from datetime import datetime, timezone
import schedule
import re
import time
from collections import defaultdict
import html # Для экранирования HTML
from config import *
from db import init_db, bulk_upsert_ca_mapping

# Отключаем предупреждения urllib3 при отключенной проверке TLS
if not VERIFY_TLS:
    try:
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    except Exception:
        pass
from prometheus_client import Counter, Gauge
from metrics_server import MetricsRegistry
from telegram_notifier import TelegramNotifier
from db import init_db, bulk_upsert_ca_mapping

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(DATA_DIR, 'logs', 'tsl_monitor.log')),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

TSL_URL = "https://e-trust.gosuslugi.ru/app/scc/portal/api/v1/portal/ca/getxml"
TSL_STATE_FILE = os.path.join(DATA_DIR, 'tsl_state.json')
TSL_CRL_URLS_FILE = os.path.join(DATA_DIR, 'crl_urls_from_tsl.txt') # Новый файл
# Используем значение из config.py: TSL_CHECK_INTERVAL_HOURS

class TSLMonitor:
    def __init__(self):
        self.notifier = TelegramNotifier()
        self.state = self.load_state()
        
        # Логируем режим работы
        if DRY_RUN:
            logger.info("🔍 TSL Monitor запущен в режиме DRY-RUN - уведомления НЕ будут отправляться в Telegram")
        else:
            logger.info("📱 TSL Monitor запущен в обычном режиме - уведомления будут отправляться в Telegram")
            
        # Метрики
        self.metric_tsl_checks_total = Counter('tsl_checks_total', 'Total TSL check runs', registry=MetricsRegistry.registry)
        self.metric_tsl_fetch_status = Counter('tsl_fetch_total', 'TSL fetch attempts', ['result'], registry=MetricsRegistry.registry)
        self.metric_active_cas = Gauge('tsl_active_cas', 'Active CAs parsed from TSL', registry=MetricsRegistry.registry)
        self.metric_crl_urls = Gauge('tsl_crl_urls', 'Unique CRL URLs extracted from TSL', registry=MetricsRegistry.registry)

    def load_state(self):
        """Загрузка состояния из файла"""
        if os.path.exists(TSL_STATE_FILE):
            try:
                with open(TSL_STATE_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data
            except Exception as e:
                logger.error(f"Ошибка загрузки состояния TSL: {e}")
        return {}

    def save_state(self, new_state):
        """Сохранение состояния в файл"""
        try:
            with open(TSL_STATE_FILE, 'w', encoding='utf-8') as f:
                json.dump(new_state, f, ensure_ascii=False, indent=2, default=str)
            self.state = new_state
        except Exception as e:
            logger.error(f"Ошибка сохранения состояния TSL: {e}")

    def save_crl_urls(self, crl_urls_set, ca_info_map=None):
        """Сохранение уникальных URL CRL в файл и карты URL -> УЦ"""
        try:
            sorted_urls = sorted(list(crl_urls_set)) # Сортируем для консистентности
            with open(TSL_CRL_URLS_FILE, 'w', encoding='utf-8') as f:
                for url in sorted_urls:
                    f.write(f"{url}\n")
            logger.info(f"Сохранено {len(sorted_urls)} уникальных URL CRL в {TSL_CRL_URLS_FILE}")
            
            # Сохраняем карту URL -> УЦ если предоставлена
            if ca_info_map:
                ca_mapping_file = os.path.join(DATA_DIR, 'crl_url_to_ca_mapping.json')
                with open(ca_mapping_file, 'w', encoding='utf-8') as f:
                    json.dump(ca_info_map, f, ensure_ascii=False, indent=2)
                logger.info(f"Сохранена карта URL -> УЦ в {ca_mapping_file}")
        except Exception as e:
            logger.error(f"Ошибка сохранения URL CRL: {e}")

    def download_tsl(self):
        """Скачивание TSL.xml с ретраями и бэкоффом"""
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        backoff = 2
        tries = 3
        for attempt in range(1, tries + 1):
            try:
                logger.info("Начало загрузки TSL.xml...")
                response = requests.get(TSL_URL, timeout=60, headers=headers, verify=VERIFY_TLS)
                response.raise_for_status()
                logger.info("TSL.xml успешно загружен")
                self.metric_tsl_fetch_status.labels(result='success').inc()
                return response.content
            except Exception as e:
                logger.error(f"Ошибка загрузки TSL.xml (попытка {attempt}/{tries}): {e}")
                self.metric_tsl_fetch_status.labels(result='error').inc()
                if attempt < tries:
                    import time
                    time.sleep(backoff)
                    backoff *= 2
        return None

    def _parse_datetime(self, date_str):
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

    def parse_tsl(self, xml_content):
        """Парсинг TSL.xml и извлечение действующих УЦ и их CRL"""
        if not xml_content:
            return {}, set()
        all_crl_urls = set() # Для хранения всех уникальных CRL URL
        active_cas = {}
        try:
            if isinstance(xml_content, bytes):
                xml_content = xml_content.decode('utf-8')
            root = ET.fromstring(xml_content)
            # Подготовим фильтры: приоритет — по ОГРН, иначе — по префиксам реестровых номеров
            ogrn_filters = None
            numeric_filters = None
            if TSL_OGRN_LIST:
                ogrn_filters = [re.sub(r'\D', '', n) for n in TSL_OGRN_LIST if n]
                ogrn_filters = [n for n in ogrn_filters if n]
            elif TSL_REGISTRY_NUMBERS:
                numeric_filters = [re.sub(r'\D', '', n) for n in TSL_REGISTRY_NUMBERS if n]
                numeric_filters = [n for n in numeric_filters if n]

            matched_count = 0
            total_active_seen = 0
            for ca_element in root.findall('.//УдостоверяющийЦентр'):
                status_element = ca_element.find('.//Статус')
                if status_element is not None and status_element.text == 'Действует':
                    total_active_seen += 1
                    reg_number_element = ca_element.find('.//РеестровыйНомер')
                    name_element = ca_element.find('.//Название')
                    # Фильтр по ОГРН (строгое совпадение цифр) имеет приоритет
                    if ogrn_filters is not None:
                        ogrn_element = ca_element.find('.//ОГРН')
                        ogrn_val = ogrn_element.text.strip() if (ogrn_element is not None and ogrn_element.text) else None
                        if not ogrn_val:
                            continue
                        ogrn_digits = re.sub(r'\D', '', ogrn_val)
                        if ogrn_digits not in ogrn_filters:
                            continue
                        else:
                            matched_count += 1
                    # Иначе — фильтр по реестровым номерам (по префиксу цифр)
                    elif numeric_filters is not None:
                        reg_val = reg_number_element.text.strip() if (reg_number_element is not None and reg_number_element.text) else None
                        if not reg_val:
                            continue
                        reg_digits = re.sub(r'\D', '', reg_val)
                        if not any(reg_digits.startswith(flt) for flt in numeric_filters):
                            continue
                        else:
                            matched_count += 1
                    effective_date_iso = None
                    history_statuses = ca_element.findall('.//ИсторияСтатусовАккредитации/СтатусАккредитации')
                    for status in reversed(history_statuses):
                        status_type_elem = status.find('Статус')
                        if status_type_elem is not None and status_type_elem.text == 'Действует':
                            date_elem = status.find('ДействуетС')
                            if date_elem is not None and date_elem.text:
                                dt_obj = self._parse_datetime(date_elem.text)
                                if dt_obj:
                                    effective_date_iso = dt_obj.isoformat()
                                    break
                    if not effective_date_iso:
                        main_status = ca_element.find('.//СтатусАккредитации')
                        if main_status is not None:
                            status_type_elem = main_status.find('Статус')
                            date_elem = main_status.find('ДействуетС')
                            if status_type_elem is not None and status_type_elem.text == 'Действует' and date_elem is not None and date_elem.text:
                                dt_obj = self._parse_datetime(date_elem.text)
                                if dt_obj:
                                    effective_date_iso = dt_obj.isoformat()
                    # Извлечение CRL - основное изменение здесь
                    ca_crl_urls = set()
                    for crl_addr in ca_element.findall('.//АдресаСписковОтзыва/Адрес'):
                        if crl_addr.text:
                            url = crl_addr.text.strip()
                            if url: # Проверяем, что URL не пустой
                                ca_crl_urls.add(url)
                                all_crl_urls.add(url) # Добавляем в общий набор
                    if reg_number_element is not None and reg_number_element.text:
                        reg_number = reg_number_element.text.strip()
                        # Попытка извлечь дополнительные поля из TSL (если присутствуют)
                        def _txt(elem, default=None):
                            return elem.text.strip() if (elem is not None and elem.text) else default

                        # Поля о средстве УЦ (возможные варианты имен тегов в TSL)
                        ca_tool = (
                            _txt(ca_element.find('.//СредстваУЦ')) or
                            _txt(ca_element.find('.//СредствоУЦ')) or
                            _txt(ca_element.find('.//Средство'))
                        )
                        ca_tool_class = (
                            _txt(ca_element.find('.//КлассСредствЭП')) or
                            _txt(ca_element.find('.//КлассСредстваУЦ')) or
                            _txt(ca_element.find('.//КлассСредства')) 
                        )

                        # Поля сертификата УЦ (наименования тегов в TSL могут отличаться в зависимости от версии)
                        cert_subject = _txt(ca_element.find('.//Субъект')) or _txt(ca_element.find('.//КомуВыдан'))
                        cert_issuer = _txt(ca_element.find('.//Издатель')) or _txt(ca_element.find('.//КемВыдан'))
                        cert_serial = _txt(ca_element.find('.//СерийныйНомер'))

                        # Период действия сертификата: пытаемся собрать строку
                        valid_from = _txt(ca_element.find('.//ДействителенС')) or _txt(ca_element.find('.//ДействуетС'))
                        valid_to = _txt(ca_element.find('.//ДействителенПо')) or _txt(ca_element.find('.//ДействуетПо'))
                        cert_validity = None
                        if valid_from or valid_to:
                            if valid_from and valid_to:
                                cert_validity = f"{valid_from} — {valid_to}"
                            else:
                                cert_validity = valid_from or valid_to

                        # Отпечаток сертификата (если публикуется в TSL)
                        cert_fingerprint = _txt(ca_element.find('.//Отпечаток')) or _txt(ca_element.find('.//ОтпечатокСертификата'))

                        # Номер CRL и идентификатор ключа издателя (если TSL их указывает на уровне УЦ)
                        crl_number = _txt(ca_element.find('.//СерийныйНомерCRL')) or _txt(ca_element.find('.//НомерCRL'))
                        issuer_key_id = _txt(ca_element.find('.//ИдентификаторКлючаИздателя')) or _txt(ca_element.find('.//ИдентификаторКлюча'))

                        active_cas[reg_number] = {
                            'name': name_element.text.strip() if name_element is not None and name_element.text else 'Не указано',
                            'effective_date': effective_date_iso,
                            'crl_urls': list(ca_crl_urls), # Сохраняем CRL для этого УЦ
                            # Доп. поля из TSL (best-effort)
                            'ca_tool': ca_tool,
                            'ca_tool_class': ca_tool_class,
                            'cert_subject': cert_subject,
                            'cert_issuer': cert_issuer,
                            'cert_serial': cert_serial,
                            'cert_validity': cert_validity,
                            'cert_fingerprint': cert_fingerprint,
                            'crl_number': crl_number,
                            'issuer_key_id': issuer_key_id,
                        }
            if ogrn_filters is not None:
                logger.info(f"Фильтр TSL по ОГРН: {ogrn_filters}")
                logger.info(f"Всего действующих УЦ в TSL: {total_active_seen}, прошло фильтр: {matched_count}")
            elif numeric_filters is not None:
                logger.info(f"Фильтр TSL по префиксам реестровых номеров: {numeric_filters}")
                logger.info(f"Всего действующих УЦ в TSL: {total_active_seen}, прошло фильтр: {matched_count}")
            # Создаем карту URL -> УЦ для передачи в CRL Monitor
            url_to_ca_map = {}
            for reg_number, ca_info in active_cas.items():
                for crl_url in ca_info.get('crl_urls', []):
                    url_to_ca_map[crl_url] = {
                        'name': ca_info['name'],
                        'reg_number': reg_number,
                        # Дополнительные поля для уведомлений об ошибках скачивания
                        'crl_number': ca_info.get('crl_number'),
                        'issuer_key_id': ca_info.get('issuer_key_id'),
                    }
            
            logger.info(f"Найдено {len(active_cas)} действующих УЦ")
            logger.info(f"Извлечено {len(all_crl_urls)} уникальных URL CRL из TSL")
            return active_cas, all_crl_urls, url_to_ca_map
        except ET.ParseError as e:
            logger.error(f"Ошибка парсинга XML TSL: {e}")
            return {}, set(), {}
        except Exception as e:
            logger.error(f"Неизвестная ошибка при парсинге TSL: {e}")
            return {}, set(), {}

    def compare_states(self, old_state, new_state):
        """Сравнение состояний и формирование отчета об изменениях"""
        changes = {
            'new_cas': [],
            'removed_cas': [],
            'date_changes': [],
            'crl_changes': [],
            'crl_url_changes': [],
            'status_changes': [],
            'name_changes': [],
            'short_name_changes': [],
            'ogrn_changes': [],
            'inn_changes': [],
            'email_changes': [],
            'website_changes': [],
            'registry_url_changes': [],
            'address_changes': [],
            'pak_changes': [],
            'certificate_changes': [],
            'other_changes': []
        }
        # Проверяем новые УЦ
        for reg_num, ca_data in new_state.items():
            if reg_num not in old_state:
                changes['new_cas'].append({
                    'reg_number': reg_num,
                    'name': ca_data['name'],
                    'effective_date': ca_data['effective_date'],
                    'ogrn': ca_data.get('ogrn'),
                    'crl_urls': ca_data.get('crl_urls', [])
                })
            else:
                old_ca = old_state[reg_num]
                
                # Проверяем изменения названия
                if old_ca.get('name') != ca_data.get('name'):
                    changes['name_changes'].append({
                        'reg_number': reg_num,
                        'old_name': old_ca.get('name'),
                        'new_name': ca_data.get('name')
                    })
                
                # Проверяем изменения краткого названия
                if old_ca.get('short_name') != ca_data.get('short_name'):
                    changes['short_name_changes'].append({
                        'reg_number': reg_num,
                        'name': ca_data.get('name'),
                        'old_short_name': old_ca.get('short_name'),
                        'new_short_name': ca_data.get('short_name')
                    })
                
                # Проверяем изменения ОГРН
                if old_ca.get('ogrn') != ca_data.get('ogrn'):
                    changes['ogrn_changes'].append({
                        'reg_number': reg_num,
                        'name': ca_data.get('name'),
                        'old_ogrn': old_ca.get('ogrn'),
                        'new_ogrn': ca_data.get('ogrn')
                    })
                
                # Проверяем изменения ИНН
                if old_ca.get('inn') != ca_data.get('inn'):
                    changes['inn_changes'].append({
                        'reg_number': reg_num,
                        'name': ca_data.get('name'),
                        'old_inn': old_ca.get('inn'),
                        'new_inn': ca_data.get('inn')
                    })
                
                # Проверяем изменения email
                if old_ca.get('email') != ca_data.get('email'):
                    changes['email_changes'].append({
                        'reg_number': reg_num,
                        'name': ca_data.get('name'),
                        'old_email': old_ca.get('email'),
                        'new_email': ca_data.get('email')
                    })
                
                # Проверяем изменения веб-сайта
                if old_ca.get('website') != ca_data.get('website'):
                    changes['website_changes'].append({
                        'reg_number': reg_num,
                        'name': ca_data.get('name'),
                        'old_website': old_ca.get('website'),
                        'new_website': ca_data.get('website')
                    })
                
                # Проверяем изменения URL реестра
                if old_ca.get('registry_url') != ca_data.get('registry_url'):
                    changes['registry_url_changes'].append({
                        'reg_number': reg_num,
                        'name': ca_data.get('name'),
                        'old_registry_url': old_ca.get('registry_url'),
                        'new_registry_url': ca_data.get('registry_url')
                    })
                
                # Проверяем изменения адреса
                if old_ca.get('address') != ca_data.get('address'):
                    changes['address_changes'].append({
                        'reg_number': reg_num,
                        'name': ca_data.get('name'),
                        'old_address': old_ca.get('address'),
                        'new_address': ca_data.get('address')
                    })
                
                # Проверяем изменения даты
                if old_ca.get('effective_date') != ca_data.get('effective_date'):
                    changes['date_changes'].append({
                        'reg_number': reg_num,
                        'name': ca_data.get('name'),
                        'old_date': old_ca.get('effective_date'),
                        'new_date': ca_data.get('effective_date')
                    })
                
                # Проверяем изменения CRL URL
                old_crls = set(old_ca.get('crl_urls', []))
                new_crls = set(ca_data.get('crl_urls', []))
                
                added_crls = new_crls - old_crls
                removed_crls = old_crls - new_crls
                
                if added_crls:
                    changes['crl_changes'].append({
                        'reg_number': reg_num,
                        'name': ca_data.get('name'),
                        'action': 'added',
                        'crls': list(added_crls),
                        # Прокидываем доп. поля из TSL, если есть
                        'crl_number': ca_data.get('crl_number'),
                        'issuer_key_id': ca_data.get('issuer_key_id'),
                        'ca_tool': ca_data.get('ca_tool'),
                        'ca_tool_class': ca_data.get('ca_tool_class'),
                        'cert_subject': ca_data.get('cert_subject'),
                        'cert_issuer': ca_data.get('cert_issuer'),
                        'cert_serial': ca_data.get('cert_serial'),
                        'cert_validity': ca_data.get('cert_validity'),
                        'cert_fingerprint': ca_data.get('cert_fingerprint'),
                    })
                
                if removed_crls:
                    changes['crl_changes'].append({
                        'reg_number': reg_num,
                        'name': ca_data.get('name'),
                        'action': 'removed',
                        'crls': list(removed_crls)
                    })
                
                # Проверяем изменения адресов CRL (если URL изменились)
                if old_crls != new_crls and not (added_crls or removed_crls):
                    # Это означает, что URL изменились, но количество осталось тем же
                    changes['crl_url_changes'].append({
                        'reg_number': reg_num,
                        'name': ca_data.get('name'),
                        'old_urls': list(old_crls),
                        'new_urls': list(new_crls)
                    })
                
                # Проверяем другие изменения (статус, прочие поля)
                for field in ['status', 'revocation_date', 'certificate_chain']:
                    if old_ca.get(field) != ca_data.get(field):
                        changes['other_changes'].append({
                            'reg_number': reg_num,
                            'name': ca_data.get('name'),
                            'field': field,
                            'old_value': old_ca.get(field),
                            'new_value': ca_data.get(field)
                        })
        
        # Проверяем удаленные УЦ
        for reg_num, ca_data in old_state.items():
            if reg_num not in new_state:
                changes['removed_cas'].append({
                    'reg_number': reg_num,
                    'name': ca_data.get('name'),
                    'ogrn': ca_data.get('ogrn'),
                    'reason': 'Удален из списка или стал недействующим'
                })
        
        return changes

    def format_datetime_for_message(self, dt_iso_str):
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

    def send_notifications(self, changes, no_changes=False):
        """Отправка уведомлений о изменениях с экранированием HTML"""
        now_msk = datetime.now(MOSCOW_TZ)
        if no_changes:
            # Уведомления о том, что изменений нет, можно отключить
            pass
        
        # --- Отправка уведомлений для TSL ---
        if changes['new_cas'] and NOTIFY_NEW_CAS:
            for ca in changes['new_cas']:
                self.notifier.send_tsl_new_ca(ca)
        
        if changes['removed_cas'] and NOTIFY_REMOVED_CAS:
            for ca in changes['removed_cas']:
                self.notifier.send_tsl_removed_ca(ca)
        
        if changes['name_changes'] and NOTIFY_NAME_CHANGES:
            for change in changes['name_changes']:
                self.notifier.send_tsl_name_change(change)
        
        if changes['short_name_changes'] and NOTIFY_SHORT_NAME_CHANGES:
            for change in changes['short_name_changes']:
                self.notifier.send_tsl_short_name_change(change)
        
        if changes['ogrn_changes'] and NOTIFY_OGRN_CHANGES:
            for change in changes['ogrn_changes']:
                self.notifier.send_tsl_ogrn_change(change)
        
        if changes['inn_changes'] and NOTIFY_INN_CHANGES:
            for change in changes['inn_changes']:
                self.notifier.send_tsl_inn_change(change)
        
        if changes['email_changes'] and NOTIFY_EMAIL_CHANGES:
            for change in changes['email_changes']:
                self.notifier.send_tsl_email_change(change)
        
        if changes['website_changes'] and NOTIFY_WEBSITE_CHANGES:
            for change in changes['website_changes']:
                self.notifier.send_tsl_website_change(change)
        
        if changes['registry_url_changes'] and NOTIFY_REGISTRY_URL_CHANGES:
            for change in changes['registry_url_changes']:
                self.notifier.send_tsl_registry_url_change(change)
        
        if changes['address_changes'] and NOTIFY_ADDRESS_CHANGES:
            for change in changes['address_changes']:
                self.notifier.send_tsl_address_change(change)
        
        if changes['date_changes'] and NOTIFY_DATE_CHANGES:
            for change in changes['date_changes']:
                self.notifier.send_tsl_date_change(change, change['old_date'], change['new_date'])
        
        if changes['crl_changes'] and NOTIFY_CRL_CHANGES:
            for change in changes['crl_changes']:
                if change['action'] == 'added':
                    self.notifier.send_tsl_crl_added(change)
                elif change['action'] == 'removed':
                    self.notifier.send_tsl_crl_removed(change)
        
        if changes['crl_url_changes'] and NOTIFY_CRL_CHANGES:
            for change in changes['crl_url_changes']:
                self.notifier.send_tsl_crl_url_change(change)
        
        if changes['status_changes'] and NOTIFY_STATUS_CHANGES:
            for change in changes['status_changes']:
                self.notifier.send_tsl_status_change(change, change['reason'])
        
        if changes['other_changes'] and NOTIFY_OTHER_CHANGES:
            for change in changes['other_changes']:
                self.notifier.send_tsl_other_change(change)

    def run_check(self):
        """Основная проверка TSL"""
        try:
            logger.info("Начало проверки TSL...")
            try:
                init_db()
            except Exception as e:
                logger.error(f"Не удалось инициализировать БД: {e}")
            self.metric_tsl_checks_total.inc()
            xml_content = self.download_tsl()
            if not xml_content:
                return
            current_state, all_crl_urls, url_to_ca_map = self.parse_tsl(xml_content)
            if not current_state:
                logger.warning("Не удалось извлечь данные об УЦ из TSL")
                return
            self.metric_active_cas.set(len(current_state))
            self.metric_crl_urls.set(len(all_crl_urls))
            # Сохраняем все найденные URL CRL и карту URL -> УЦ
            self.save_crl_urls(all_crl_urls, url_to_ca_map)
            # Также сохраняем в БД (идемпотентно)
            try:
                init_db()
                bulk_upsert_ca_mapping(url_to_ca_map)
                logger.info(f"В БД сохранено соответствий URL->УЦ: {len(url_to_ca_map)}")
            except Exception as e:
                logger.error(f"Ошибка записи карты URL->УЦ в БД: {e}")
            # Пишем соответствие URL->УЦ в БД
            try:
                bulk_upsert_ca_mapping(url_to_ca_map)
                logger.info(f"В БД сохранено соответствий URL->УЦ: {len(url_to_ca_map)}")
            except Exception as e:
                logger.error(f"Ошибка записи карты URL->УЦ в БД: {e}")
            changes = self.compare_states(self.state, current_state)
            if any(changes.values()):
                self.send_notifications(changes, no_changes=False)
            else:
                self.send_notifications(changes, no_changes=True)
            self.save_state(current_state)
            logger.info("Проверка TSL завершена")
        except Exception as e:
            logger.error(f"Ошибка во время проверки TSL: {e}")

    def setup_schedule(self):
        """Настройка расписания"""
        schedule.every(TSL_CHECK_INTERVAL_HOURS).hours.do(self.run_check)

    def run(self):
        """Запуск монитора TSL"""
        logger.info("Запуск TSL Monitor")
        self.run_check() # Первая проверка при запуске
        self.setup_schedule()
        while True:
            try:
                schedule.run_pending()
                time.sleep(60)
            except KeyboardInterrupt:
                logger.info("Получен сигнал завершения для TSL Monitor")
                break
            except Exception as e:
                logger.error(f"Ошибка в основном цикле TSL Monitor: {e}")
                time.sleep(60)

if __name__ == "__main__":
    monitor = TSLMonitor()
    # Проверяем наличие флага --once в аргументах командной строки
    if '--once' in sys.argv:
        # Если флаг есть, выполняем только одну проверку и выходим.
        # Это нужно для синхронного запуска в entrypoint.sh.
        logger.info("Running a single check due to --once flag.")
        monitor.run_check()
        logger.info("Single check finished.")
    else:
        # В противном случае запускаем монитор в стандартном режиме (бесконечный цикл)
        monitor.run()