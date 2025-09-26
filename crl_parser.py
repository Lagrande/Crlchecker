# ./crl_parser.py
import logging
from cryptography import x509
from cryptography.hazmat.backends import default_backend
import requests
import os
import tempfile
import subprocess
from urllib.parse import urljoin, urlparse
import re
from datetime import datetime
from config import VERIFY_TLS

# Отключаем предупреждения urllib3 при отключенной проверке TLS
if not VERIFY_TLS:
    try:
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    except Exception:
        pass

logger = logging.getLogger(__name__)

class CRLParser:
    def __init__(self, cache_dir):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        # Для хранения последних данных CRL при парсинге, если понадобится резервный метод
        self._last_crl_data = None 

    def download_crl(self, url):
            """Скачивание CRL по URL с использованием одного запроса с ретраями."""
            try:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
                backoff = 1
                tries = 3
                for attempt in range(1, tries + 1):
                    try:
                        with requests.get(url, timeout=30, headers=headers, stream=True, verify=VERIFY_TLS) as response:
                            response.raise_for_status()
                            full_content = response.content
                            if not full_content:
                                logger.warning(f"Файл по URL {url} пустой.")
                                return None
                            parsed_url = urlparse(url)
                            filename_safe_netloc = parsed_url.netloc.replace(':', '_')
                            filename_safe_path = parsed_url.path.replace('/', '_').replace('\\', '_')
                            filename = os.path.join(
                                self.cache_dir,
                                f"{filename_safe_netloc}_{filename_safe_path.lstrip('_')}"
                            )
                            with open(filename, 'wb') as f:
                                f.write(full_content)
                            logger.debug(f"Файл загружен и сохранен: {url} -> {filename}")
                            if self.is_crl_content(full_content):
                                logger.info(f"Успешно распознан CRL: {url}")
                            else:
                                logger.debug(f"Загруженный файл по URL {url} не распознан как CRL напрямую. Сохранен для анализа.")
                            return full_content
                    except requests.exceptions.RequestException as e:
                        logger.error(f"Ошибка загрузки CRL {url} (попытка {attempt}/{tries}): {e}")
                        if attempt < tries:
                            import time
                            time.sleep(backoff)
                            backoff *= 2
                            continue
                        return None

            except Exception as e:
                logger.error(f"Неизвестная ошибка загрузки CRL {url}: {e}")
                return None

    def is_crl_content(self, content):
        """Проверка, является ли содержимое CRL"""
        if not content:
            logger.debug("Содержимое пустое.")
            return False

        is_valid = False
        format_tried = []

        # Попробуем сначала PEM (более специфичный формат)
        if b'-----BEGIN X509 CRL-----' in content and b'-----END X509 CRL-----' in content:
            format_tried.append("PEM")
            try:
                logger.debug("Попытка парсинга как PEM...")
                x509.load_pem_x509_crl(content, default_backend())
                logger.debug("Файл успешно распознан как PEM CRL.")
                is_valid = True
            except Exception as e:
                logger.debug(f"Ошибка парсинга как PEM CRL: {type(e).__name__}: {e}")

        # Если PEM не сработал, пробуем DER
        if not is_valid:
            format_tried.append("DER")
            try:
                logger.debug("Попытка парсинга как DER...")
                x509.load_der_x509_crl(content, default_backend())
                logger.debug("Файл успешно распознан как DER CRL.")
                is_valid = True
            except Exception as e:
                logger.debug(f"Ошибка парсинга как DER CRL: {type(e).__name__}: {e}")

        if not is_valid:
            tried_str = ", ".join(format_tried) if format_tried else "никакой"
            logger.debug(f"Содержимое не распознано как CRL. Попытки: {tried_str}. Длина: {len(content)} байт.")
            # Для отладки можно залогировать первые 100 байт
            # logger.debug(f"Первые 100 байт: {content[:100]}")

        return is_valid

    # Измените сигнатуру метода, добавив параметр crl_name (можно сделать его необязательным)
    def parse_crl(self, crl_data, crl_name="Неизвестный CRL"):
        """Парсинг CRL данных"""
        if not crl_data:
            # logger.debug(f"CRL данные для '{crl_name}' пусты.")
            return None

        # Сохраняем данные для возможного резервного парсинга
        self._last_crl_data = crl_data

        crl = None  # Инициализируем переменную для хранения распарсенного CRL
        der_error = None  # Для хранения ошибки ValueError от DER
        pem_error = None  # Для хранения ошибки ValueError от PEM

        # --- Пробуем PEM формат (более специфичный) ---
        # Проверяем сигнатуры PEM до попытки парсинга, чтобы избежать лишних исключений
        # Используем одинарные дефисы, как в сигнатурах из файла combined_output.txt
        if b'-BEGIN X509 CRL-' in crl_data and b'-END X509 CRL-' in crl_data:
            logger.debug(f"Парсинг данных '{crl_name}' как PEM...")
            try:
                crl = x509.load_pem_x509_crl(crl_data, default_backend())
                logger.debug(f"Данные '{crl_name}' успешно распознаны как PEM CRL.")
                # Если PEM успешен, crl будет установлен, и мы пропустим DER и OpenSSL
            except ValueError as e: # Ошибка в данных PEM
                pem_error = e
                logger.error(f"Ошибка парсинга CRL '{crl_name}' (PEM, неверные данные): {type(e).__name__}: {e}")
                # Не возвращаем None, продолжаем, чтобы попробовать DER
            except Exception as e: # Другая ошибка при парсинге PEM
                logger.error(f"Ошибка парсинга CRL '{crl_name}' (PEM): {type(e).__name__}: {e}")
                # Не возвращаем None, продолжаем, чтобы попробовать DER
        # else: Сигнатуры PEM не найдены, пропускаем блок PEM

        # --- Пробуем DER формат ---
        # Выполняется, если PEM не сработал или сигнатуры PEM не найдены
        if crl is None: # Только если PEM ещё не дал результата
            logger.debug(f"Парсинг данных '{crl_name}' как DER...")
            try:
                crl = x509.load_der_x509_crl(crl_data, default_backend())
                logger.debug(f"Данные '{crl_name}' успешно распознаны как DER CRL.")
                # Если DER успешен, crl будет установлен, и мы пропустим OpenSSL
            except ValueError as e: # Ошибка в данных DER
                der_error = e
                logger.error(f"Ошибка парсинга CRL '{crl_name}' (DER, неверные данные): {type(e).__name__}: {e}")
                # Не возвращаем None, продолжаем к резервному методу
            except Exception as e: # Другая ошибка при парсинге DER
                logger.error(f"Ошибка парсинга CRL '{crl_name}' (DER): {type(e).__name__}: {e}")
                # Не возвращаем None, продолжаем к резервному методу

        # --- Общий блок проверки и резервного вызова ---
        # Проверяем, был ли успешно распарсен CRL (crl не None)
        if not crl:
            # Формируем сообщение об ошибках, если они были
            error_details = []
            if pem_error:
                error_details.append(f"PEM ValueError: {pem_error}")
            if der_error:
                error_details.append(f"DER ValueError: {der_error}")
            error_msg = "; ".join(error_details) if error_details else "Неизвестная ошибка парсинга DER/PEM"

            # Улучшенное сообщение с именем CRL
            logger.warning(f"Не удалось распарсить CRL '{crl_name}' с помощью библиотеки cryptography ({error_msg}). Пробуем резервный метод OpenSSL...")
            logger.debug(f"Пробуем резервный метод парсинга OpenSSL для '{crl_name}'...")
            # Вызываем резервный метод, передавая исходные данные
            # Можно также передать crl_name в _parse_crl_with_openssl, если нужно залогировать внутри
            return self._parse_crl_with_openssl(crl_data) 

        # Если дошли до этой точки, значит `crl` был успешно установлен через cryptography
        return crl


    def get_crl_info(self, crl):
        """Получение информации о CRL с использованием cryptography"""
        logger.debug(f"get_crl_info вызван с объектом типа: {type(crl)}")
        if not crl:
            logger.debug("get_crl_info: входной объект crl пустой или None")
            return None

        # Получаем номер CRL из расширений
        crl_number = None
        # Флаг для Delta CRL
        is_delta_crl = False
        try:
            extensions = crl.extensions
            for ext in extensions:
                if ext.oid == x509.ObjectIdentifier('2.5.29.20'):  # CRL Number
                    crl_number = ext.value.crl_number
                elif ext.oid == x509.ObjectIdentifier('2.5.29.27'): # Delta CRL Indicator
                    is_delta_crl = True
                    logger.debug(f"Обнаружен Delta CRL. Базовый CRL Number: {ext.value.crl_number}")
        except Exception as e:
            logger.debug(f"Не удалось получить расширения CRL: {e}")
            
        info = {
            'this_update': crl.last_update,
            'next_update': crl.next_update,
            'revoked_count': len(list(crl)),
            'crl_number': crl_number,
            'issuer': crl.issuer.rfc4514_string() if crl.issuer else None,
            'revoked_certificates': [],
            'is_delta': is_delta_crl # Добавляем флаг
        }
        # Если это Delta CRL, логируем
        if is_delta_crl:
             logger.info("Этот CRL является Delta CRL.")
        # Сбор информации об отозванных сертификатах
        try: # Обернем цикл в try, чтобы ошибки в обработке одного сертификата не останавливали весь процесс
            for revoked_cert in crl:
                cert_info = {
                    'serial_number': revoked_cert.serial_number,
                    'revocation_date': revoked_cert.revocation_date,
                    'reason': None
                }
                # Получение причины отзыва
                try:
                    extensions = revoked_cert.extensions
                    for ext in extensions:
                        if ext.oid == x509.ObjectIdentifier('2.5.29.21'):  # Reason code
                            reason_value = ext.value
                            # Преобразуем причину в читаемый формат
                            try:
                                if hasattr(reason_value.reason, 'name'):
                                    cert_info['reason'] = reason_value.reason
                                else:
                                    cert_info['reason'] = str(reason_value.reason)
                            except (AttributeError, TypeError):
                                cert_info['reason'] = reason_value.reason
                            break
                except x509.ExtensionNotFound:
                    # Это нормально, если расширение отсутствует
                    pass
                except Exception as e:
                    logger.debug(f"Не удалось получить причину отзыва для сертификата (S/N: {revoked_cert.serial_number}): {e}")
                info['revoked_certificates'].append(cert_info)
        except Exception as e:
             logger.error(f"Критическая ошибка при переборе отозванных сертификатов в CRL: {e}")

        # --- ГАРАНТИЯ ВОЗВРАТА DICT ---
        # Убедимся, что info - это словарь перед возвратом
        if isinstance(info, dict):
            logger.debug(f"get_crl_info: успешно извлечена информация, возвращаем dict. Отозвано: {info.get('revoked_count', 'N/A')}, Delta: {info.get('is_delta', False)}")
            return info
        else:
            logger.error(f"get_crl_info: ожидается dict, но возвращается {type(info)}. Возвращаю None.")
            return None # или просто return None

    def _parse_crl_with_openssl(self, crl_data, format_hint='auto'):
        """
        Резервный метод парсинга CRL с использованием OpenSSL CLI.
        Возвращает словарь с информацией о CRL или None в случае ошибки.
        """
        if not crl_data:
            return None

        # Определяем формат, если не указан
        if format_hint == 'auto':
            if crl_data.startswith(b'-----BEGIN X509 CRL-----'):
                format_hint = 'PEM'
            else:
                # Предполагаем DER по умолчанию для бинарных данных
                format_hint = 'DER' 

        info = {
            'this_update': None,
            'next_update': None,
            'revoked_count': 0,
            'crl_number': None,
            'issuer': None,
            'revoked_certificates': [],
            'is_delta': False # OpenSSL CLI не парсит Delta CRL напрямую
        }

        # Создаем временный файл для CRL данных
        with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.crl') as tmp_crl_file:
            tmp_crl_file.write(crl_data)
            tmp_crl_path = tmp_crl_file.name

        try:
            # Строим команду openssl
            cmd = [
                'openssl', 'crl',
                '-inform', format_hint,
                '-in', tmp_crl_path,
                '-noout',
                '-text'
            ]

            # logger.debug(f"Вызов OpenSSL: {' '.join(cmd)}") # Для отладки

            # Выполняем команду
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30 # Таймаут на всякий случай
            )

            if result.returncode != 0:
                logger.debug(f"OpenSSL не смог распарсить CRL: {result.stderr}")
                return None

            output_lines = result.stdout.splitlines()

            # Парсим вывод OpenSSL
            i = 0
            while i < len(output_lines):
                line = output_lines[i].strip()
                
                if line.startswith('Version:'):
                    # Версия CRL (не критично)
                    pass
                elif line.startswith('Signature Algorithm:'):
                    # Алгоритм подписи (не критично)
                    pass
                elif line.startswith('Issuer:'):
                    # Издатель
                    issuer_str = line.split(':', 1)[1].strip() if ':' in line else line
                    info['issuer'] = issuer_str
                elif line.startswith('Last Update:'):
                    # Дата последнего обновления
                    date_str = line.split(':', 1)[1].strip() if ':' in line else ""
                    if date_str:
                        try:
                            # OpenSSL обычно выводит в формате: Mon DD HH:MM:SS YYYY GMT
                            # Например: "Jul 30 13:20:37 2025 GMT"
                            dt_obj = datetime.strptime(date_str, "%b %d %H:%M:%S %Y %Z")
                            info['this_update'] = dt_obj # Возвращаем naive datetime, tz обработается позже
                        except ValueError as e:
                            logger.debug(f"Не удалось распарсить Last Update из OpenSSL вывода '{date_str}': {e}")
                elif line.startswith('Next Update:'):
                    # Дата следующего обновления
                    date_str = line.split(':', 1)[1].strip() if ':' in line else ""
                    if date_str:
                        try:
                            dt_obj = datetime.strptime(date_str, "%b %d %H:%M:%S %Y %Z")
                            info['next_update'] = dt_obj
                        except ValueError as e:
                            logger.debug(f"Не удалось распарсить Next Update из OpenSSL вывода '{date_str}': {e}")
                elif line.startswith('Revoked Certificates:'):
                    # Начинаем парсить список отозванных
                    i += 1
                    revoked_count = 0
                    while i < len(output_lines) and not output_lines[i].startswith('Signature Algorithm:'):
                        sub_line = output_lines[i].strip()
                        if sub_line.startswith('Serial Number:'):
                            revoked_count += 1
                            # TODO: Расширенный парсинг отозванных сертификатов (серийный номер, дата, причина)
                        i += 1
                    info['revoked_count'] = revoked_count
                    continue # Не увеличиваем i снова в конце цикла
                elif 'X509v3 CRL Number:' in line:
                    # Номер CRL (обычно на следующей строке)
                    i += 1
                    if i < len(output_lines):
                        number_line = output_lines[i].strip()
                        try:
                            # Номер обычно просто число
                            info['crl_number'] = int(number_line)
                        except ValueError:
                            # Может быть в hex, например, "0x15A3"
                            try:
                                if number_line.startswith('0x'):
                                    info['crl_number'] = int(number_line, 16)
                                else:
                                    logger.debug(f"Не удалось преобразовать номер CRL '{number_line}' в int")
                            except ValueError:
                                logger.debug(f"Не удалось преобразовать номер CRL '{number_line}' в int (hex)")
                
                i += 1

            logger.debug(f"OpenSSL успешно распарсил CRL. Извлечено: {info}")
            return info

        except subprocess.TimeoutExpired:
            logger.error("Таймаут при вызове OpenSSL для парсинга CRL.")
            return None
        except FileNotFoundError:
            logger.error("Утилита 'openssl' не найдена в системе. Резервный парсинг невозможен.")
            return None
        except Exception as e:
            logger.error(f"Неожиданная ошибка при вызове OpenSSL для парсинга CRL: {e}")
            return None
        finally:
            # Удаляем временный файл
            try:
                os.unlink(tmp_crl_path)
            except OSError:
                pass # Игнорируем ошибки удаления

    def get_crl_urls_from_cdp(self, cdp_url):
        """Получение списка CRL URL из CDP каталога"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(cdp_url, timeout=30, headers=headers, verify=VERIFY_TLS)
            response.raise_for_status()
            
            # Ищем все ссылки на .crl файлы
            # Расширяем паттерн для поиска различных форматов URL
            crl_patterns = [
                r'href=["\']([^"\']*\.crl)["\']',
                r'(https?://[^\s"\'<>]*\.crl)',
                r'<a\s+href=["\']?([^"\'>\s]*\.crl)["\']?[^>]*>',
            ]
            
            all_urls = set() # Используем set для удаления дубликатов сразу
            text_content = response.text
            
            for pattern in crl_patterns:
                urls = re.findall(pattern, text_content, re.IGNORECASE)
                all_urls.update(urls)
            
            # Преобразуем относительные URL в абсолютные
            full_urls = []
            for url in all_urls:
                if url.startswith('http'):
                    full_urls.append(url)
                else:
                    # Обрабатываем относительные пути
                    full_urls.append(urljoin(cdp_url, url))
                    
            logger.debug(f"Найдено {len(full_urls)} потенциальных CRL URL из {cdp_url}")
            
            # Проверяем каждый URL на существование и содержимое (предварительная проверка)
            valid_urls = []
            for url in full_urls:
                try:
                    # Сначала пробуем HEAD запрос
                    head_response = requests.head(url, timeout=10, headers=headers, allow_redirects=True, verify=VERIFY_TLS)
                    if head_response.status_code == 200:
                        content_type = head_response.headers.get('content-type', '').lower()
                        content_length = head_response.headers.get('content-length')
                        # Проверяем тип контента
                        if ('application/pkix-crl' in content_type or
                            'application/x-pkcs7-crl' in content_type or
                            'application/octet-stream' in content_type or
                            url.endswith('.crl')):
                            # Проверяем размер (CRL обычно не пустые)
                            # Убираем строгую проверку размера
                            # if content_length is None or int(content_length) > 50:
                            valid_urls.append(url)
                            logger.debug(f"Найден потенциально действительный CRL: {url}")
                            continue
                    # Если HEAD не дал результата, просто добавляем URL в список для дальнейшей проверки
                    # Полная проверка будет в download_crl
                    logger.debug(f"URL {url} требует дальнейшей проверки (HEAD: {head_response.status_code})")
                    valid_urls.append(url)
                except Exception as e:
                    logger.debug(f"Ошибка проверки URL {url} (HEAD): {e}")
                    # Добавляем URL, ошибка будет при попытке загрузки
                    valid_urls.append(url)
                    
            final_valid_urls = list(set(valid_urls)) # Убираем дубликаты
            logger.info(f"Найдено {len(final_valid_urls)} потенциальных CRL URL из {cdp_url} (после проверки)")
            return final_valid_urls
        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка получения CRL URL из {cdp_url}: {e}")
            return []
        except Exception as e:
            logger.error(f"Неизвестная ошибка получения CRL URL из {cdp_url}: {e}")
            return []

            return final_valid_urls
        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка получения CRL URL из {cdp_url}: {e}")
            return []
        except Exception as e:
            logger.error(f"Неизвестная ошибка получения CRL URL из {cdp_url}: {e}")
            return []
