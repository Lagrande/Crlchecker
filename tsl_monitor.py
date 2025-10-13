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
import urllib3
from config import *
from db import init_db, bulk_upsert_ca_mapping
from db import tsl_versions_get_last, tsl_versions_upsert, tsl_ca_snapshots_get, tsl_ca_snapshots_write, tsl_diffs_write
from metrics import tsl_checks_total, tsl_fetch_status, tsl_active_cas, tsl_crl_urls
from utils import parse_tsl_datetime, format_datetime_for_message, get_current_time_msk, setup_logging
from telegram_notifier import TelegramNotifier

# Отключаем предупреждения urllib3 при отключенной проверке TLS
if not VERIFY_TLS:
    try:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    except Exception:
        pass

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
    def __init__(self, tsl_file: str = None):
        self.notifier = TelegramNotifier()
        self.state = self.load_state()
        # Путь к локальному файлу TSL для тестов (если задан через CLI)
        self.tsl_file = tsl_file
        
        # Логируем режим работы
        if DRY_RUN:
            logger.info("🔍 TSL Monitor запущен в режиме DRY-RUN - уведомления НЕ будут отправляться в Telegram")
        else:
            logger.info("📱 TSL Monitor запущен в обычном режиме - уведомления будут отправляться в Telegram")
            
        # Метрики
        self.metric_tsl_checks_total = tsl_checks_total
        self.metric_tsl_fetch_status = tsl_fetch_status
        self.metric_active_cas = tsl_active_cas
        self.metric_crl_urls = tsl_crl_urls

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
                    time.sleep(backoff)
                    backoff *= 2
        return None

    def load_tsl_from_file(self, path):
        """Загрузка TSL.xml из локального файла (возвращает bytes или None)."""
        try:
            if not path:
                return None
            if not os.path.exists(path):
                logger.error(f"Локальный файл TSL не найден: {path}")
                return None
            with open(path, 'rb') as f:
                content = f.read()
                logger.info(f"TSL.xml загружен из локального файла: {path}, размер: {len(content)} байт")
                return content
        except Exception as e:
            logger.error(f"Ошибка чтения локального файла TSL '{path}': {e}")
            return None


    def parse_tsl(self, xml_content):
        """Парсинг TSL.xml и извлечение действующих УЦ и их CRL"""
        if not xml_content:
            return {}, set(), {}
        all_crl_urls = set() # Для хранения всех уникальных CRL URL
        active_cas = {}
        try:
            raw_bytes = xml_content if isinstance(xml_content, (bytes, bytearray)) else xml_content.encode('utf-8')
            xml_text = raw_bytes.decode('utf-8', errors='ignore')
            root = ET.fromstring(xml_text)
            # Извлекаем версию TSL: сначала как текст в элементах, затем fallback на атрибуты у корня
            tsl_version = None
            try:
                # Поиск текстового значения версии в узлах
                version_nodes = [
                    root.find('.//версия'),
                    root.find('.//Версия'),
                    root.find('.//ВЕРСИЯ'),
                ]
                for node in version_nodes:
                    if node is not None and node.text and node.text.strip():
                        tsl_version = node.text.strip()
                        break
                # Fallback: берем атрибуты корневого элемента, если текст не найден
                if not tsl_version:
                    tsl_version = (
                        root.attrib.get('Версия') or
                        root.attrib.get('версия') or
                        root.attrib.get('Version') or
                        root.attrib.get('version')
                    )
            except Exception:
                tsl_version = None
            self.current_tsl_version = tsl_version
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
                                dt_obj = parse_tsl_datetime(date_elem.text)
                                if dt_obj:
                                    effective_date_iso = dt_obj.isoformat()
                                    break
                    if not effective_date_iso:
                        main_status = ca_element.find('.//СтатусАккредитации')
                        if main_status is not None:
                            status_type_elem = main_status.find('Статус')
                            date_elem = main_status.find('ДействуетС')
                            if status_type_elem is not None and status_type_elem.text == 'Действует' and date_elem is not None and date_elem.text:
                                dt_obj = parse_tsl_datetime(date_elem.text)
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
                            'tsl_version': tsl_version,
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

            # --- Persist TSL version root/meta and CA snapshots + compute diffs ---
            try:
                import hashlib
                schema_loc = root.attrib.get('{http://www.w3.org/2001/XMLSchema-instance}noNamespaceSchemaLocation')
                xml_sha256 = hashlib.sha256(raw_bytes).hexdigest()
                current_version = tsl_version or 'unknown'
                current_date_node = root.find('.//Дата')
                current_date = current_date_node.text.strip() if (current_date_node is not None and current_date_node.text) else None
                tsl_versions_upsert(current_version, current_date, schema_loc, xml_sha256)
                logger.info(f"TSL version persisted: version={current_version}, date={current_date}, schema={schema_loc}")

                # Build CA snapshots as compact JSON per CA keyed by reg_number
                snapshots = {}
                for reg_number, ca in active_cas.items():
                    snapshots[reg_number] = {
                        'name': ca.get('name'),
                        'effective_date': ca.get('effective_date'),
                        'crl_urls': sorted(ca.get('crl_urls') or []),
                        'ca_tool': ca.get('ca_tool'),
                        'ca_tool_class': ca.get('ca_tool_class'),
                        'cert_subject': ca.get('cert_subject'),
                        'cert_issuer': ca.get('cert_issuer'),
                        'cert_serial': ca.get('cert_serial'),
                        'cert_validity': ca.get('cert_validity'),
                        'cert_fingerprint': ca.get('cert_fingerprint'),
                        'crl_number': ca.get('crl_number'),
                        'issuer_key_id': ca.get('issuer_key_id'),
                    }

                # Load previous version (if any) and compute diffs
                prev = tsl_versions_get_last()
                prev_version = None
                prev_snaps = {}
                logger.info(f"Previous version from DB: {prev}")
                if prev and prev[0] != current_version:
                    prev_version = prev[0]
                    prev_snaps = tsl_ca_snapshots_get(prev_version)
                    logger.info(f"Will compute diffs from {prev_version} to {current_version}")
                else:
                    logger.info(f"No diffs needed: prev={prev[0] if prev else None}, current={current_version}")

                # write current snapshots
                tsl_ca_snapshots_write(current_version, snapshots)
                logger.info(f"TSL CA snapshots persisted: version={current_version}, count={len(snapshots)}")

                diffs = []
                if prev_version:
                    # Root-level diffs: /Версия, /Дата, /@xsi:noNamespaceSchemaLocation
                    def _add_root(path, old_val, new_val):
                        if (old_val or new_val) and (old_val != new_val):
                            diffs.append((prev_version, current_version, 'root', 'root', path, old_val, new_val))
                    _add_root('/Версия', prev[0], current_version)
                    _add_root('/Дата', prev[1].get('date') if isinstance(prev, tuple) else None, current_date)
                    _add_root('/@xsi:noNamespaceSchemaLocation', prev[1].get('root_schema_location') if isinstance(prev, tuple) else None, schema_loc)

                    # CA-level diffs by reg_number key
                    all_keys = set(prev_snaps.keys()) | set(snapshots.keys())
                    for key in sorted(all_keys):
                        before = prev_snaps.get(key)
                        after = snapshots.get(key)
                        if before is None and after is not None:
                            diffs.append((prev_version, current_version, 'ca', key, '/#exists', None, '1'))
                        elif before is not None and after is None:
                            diffs.append((prev_version, current_version, 'ca', key, '/#exists', '1', None))
                        else:
                            # field-level diffs
                            for field, path in [
                                ('name', '/УдостоверяющийЦентр/Название'),
                                ('effective_date', '/УдостоверяющийЦентр/СтатусАккредитации/ДействуетС'),
                                ('ca_tool', '/УдостоверяющийЦентр/СредстваУЦ'),
                                ('ca_tool_class', '/УдостоверяющийЦентр/КлассСредствЭП'),
                                ('cert_subject', '/УдостоверяющийЦентр/Сертификат/КомуВыдан'),
                                ('cert_issuer', '/УдостоверяющийЦентр/Сертификат/КемВыдан'),
                                ('cert_serial', '/УдостоверяющийЦентр/Сертификат/СерийныйНомер'),
                                ('cert_validity', '/УдостоверяющийЦентр/Сертификат/ПериодДействия'),
                                ('cert_fingerprint', '/УдостоверяющийЦентр/Сертификат/Отпечаток'),
                                ('crl_number', '/УдостоверяющийЦентр/СерийныйНомерCRL'),
                                ('issuer_key_id', '/УдостоверяющийЦентр/ИдентификаторКлючаИздателя'),
                            ]:
                                old_val = before.get(field) if before else None
                                new_val = after.get(field) if after else None
                                if old_val != new_val:
                                    diffs.append((prev_version, current_version, 'ca', key, path, old_val, new_val))
                            # aggregate CRL URLs
                            old_urls = before.get('crl_urls') if before else []
                            new_urls = after.get('crl_urls') if after else []
                            if sorted(old_urls) != sorted(new_urls):
                                diffs.append((prev_version, current_version, 'ca', key, '/УдостоверяющийЦентр/АдресаСписковОтзыва/Адрес/#agg', json.dumps(old_urls, ensure_ascii=False), json.dumps(new_urls, ensure_ascii=False)))

                if diffs:
                    tsl_diffs_write(prev_version, current_version, diffs)
                    logger.info(f"TSL diffs persisted: from={prev_version}, to={current_version}, count={len(diffs)}")
                else:
                    logger.info(f"No TSL diffs to persist: prev_version={prev_version}, current_version={current_version}")

            except Exception as e:
                logger.error(f"Ошибка сохранения версий/диффов TSL: {e}")

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


    def send_notifications(self, changes, no_changes=False):
        """Отправка уведомлений о изменениях с экранированием HTML"""
        now_msk = get_current_time_msk()
        if no_changes:
            # Уведомления о том, что изменений нет, можно отключить
            pass
        
        # --- Отправка уведомлений для TSL ---
        if changes['new_cas'] and NOTIFY_NEW_CAS:
            for ca in changes['new_cas']:
                ca['tsl_version'] = getattr(self, 'current_tsl_version', None)
                self.notifier.send_tsl_new_ca(ca)
        
        if changes['removed_cas'] and NOTIFY_REMOVED_CAS:
            for ca in changes['removed_cas']:
                ca['tsl_version'] = getattr(self, 'current_tsl_version', None)
                self.notifier.send_tsl_removed_ca(ca)
        
        if changes['name_changes'] and NOTIFY_NAME_CHANGES:
            for change in changes['name_changes']:
                change['tsl_version'] = getattr(self, 'current_tsl_version', None)
                self.notifier.send_tsl_name_change(change)
        
        if changes['short_name_changes'] and NOTIFY_SHORT_NAME_CHANGES:
            for change in changes['short_name_changes']:
                change['tsl_version'] = getattr(self, 'current_tsl_version', None)
                self.notifier.send_tsl_short_name_change(change)
        
        if changes['ogrn_changes'] and NOTIFY_OGRN_CHANGES:
            for change in changes['ogrn_changes']:
                change['tsl_version'] = getattr(self, 'current_tsl_version', None)
                self.notifier.send_tsl_ogrn_change(change)
        
        if changes['inn_changes'] and NOTIFY_INN_CHANGES:
            for change in changes['inn_changes']:
                change['tsl_version'] = getattr(self, 'current_tsl_version', None)
                self.notifier.send_tsl_inn_change(change)
        
        if changes['email_changes'] and NOTIFY_EMAIL_CHANGES:
            for change in changes['email_changes']:
                change['tsl_version'] = getattr(self, 'current_tsl_version', None)
                self.notifier.send_tsl_email_change(change)
        
        if changes['website_changes'] and NOTIFY_WEBSITE_CHANGES:
            for change in changes['website_changes']:
                change['tsl_version'] = getattr(self, 'current_tsl_version', None)
                self.notifier.send_tsl_website_change(change)
        
        if changes['registry_url_changes'] and NOTIFY_REGISTRY_URL_CHANGES:
            for change in changes['registry_url_changes']:
                change['tsl_version'] = getattr(self, 'current_tsl_version', None)
                self.notifier.send_tsl_registry_url_change(change)
        
        if changes['address_changes'] and NOTIFY_ADDRESS_CHANGES:
            for change in changes['address_changes']:
                change['tsl_version'] = getattr(self, 'current_tsl_version', None)
                self.notifier.send_tsl_address_change(change)
        
        if changes['date_changes'] and NOTIFY_DATE_CHANGES:
            for change in changes['date_changes']:
                change['tsl_version'] = getattr(self, 'current_tsl_version', None)
                self.notifier.send_tsl_date_change(change, change['old_date'], change['new_date'])
        
        if changes['crl_changes'] and NOTIFY_CRL_CHANGES:
            for change in changes['crl_changes']:
                if change['action'] == 'added':
                    change['tsl_version'] = getattr(self, 'current_tsl_version', None)
                    self.notifier.send_tsl_crl_added(change)
                elif change['action'] == 'removed':
                    change['tsl_version'] = getattr(self, 'current_tsl_version', None)
                    self.notifier.send_tsl_crl_removed(change)
        
        if changes['crl_url_changes'] and NOTIFY_CRL_CHANGES:
            for change in changes['crl_url_changes']:
                change['tsl_version'] = getattr(self, 'current_tsl_version', None)
                self.notifier.send_tsl_crl_url_change(change)
        
        if changes['status_changes'] and NOTIFY_STATUS_CHANGES:
            for change in changes['status_changes']:
                change['tsl_version'] = getattr(self, 'current_tsl_version', None)
                self.notifier.send_tsl_status_change(change, change['reason'])
        
        if changes['other_changes'] and NOTIFY_OTHER_CHANGES:
            for change in changes['other_changes']:
                change['tsl_version'] = getattr(self, 'current_tsl_version', None)
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
            # Если передан локальный файл TSL, используем его, иначе скачиваем
            xml_content = None
            if self.tsl_file:
                # Разрешаем относительный путь в /app/data
                candidate = self.tsl_file
                if not os.path.isabs(candidate):
                    candidate = os.path.join(DATA_DIR, candidate)
                xml_content = self.load_tsl_from_file(candidate)
            if not xml_content:
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
    # Поддержка аргумента --tsl-file=<path>
    tsl_file_arg = None
    for arg in sys.argv:
        if arg.startswith('--tsl-file='):
            tsl_file_arg = arg.split('=', 1)[1].strip() or None
            break
    monitor = TSLMonitor(tsl_file=tsl_file_arg)
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