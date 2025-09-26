# ./config.py
import os
from datetime import timedelta, timezone

# --- Конфигурация Telegram бота ---
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', 'YOUR_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', 'YOUR_CHAT_ID')

# --- Настройки уведомлений ---
# Режим Dry-run (без отправки уведомлений в Telegram)
DRY_RUN = os.getenv('DRY_RUN', 'false').lower() == 'true'

# Включение/отключение различных типов уведомлений
NOTIFY_NEW_CAS = os.getenv('NOTIFY_NEW_CAS', 'true').lower() == 'true'  # Новые УЦ
NOTIFY_REMOVED_CAS = os.getenv('NOTIFY_REMOVED_CAS', 'true').lower() == 'true'  # Удаленные УЦ
NOTIFY_DATE_CHANGES = os.getenv('NOTIFY_DATE_CHANGES', 'true').lower() == 'true'  # Изменения дат
NOTIFY_CRL_CHANGES = os.getenv('NOTIFY_CRL_CHANGES', 'true').lower() == 'true'  # Изменения CRL
NOTIFY_STATUS_CHANGES = os.getenv('NOTIFY_STATUS_CHANGES', 'true').lower() == 'true'  # Изменения статуса УЦ
NOTIFY_NAME_CHANGES = os.getenv('NOTIFY_NAME_CHANGES', 'true').lower() == 'true'  # Изменения названий УЦ
NOTIFY_SHORT_NAME_CHANGES = os.getenv('NOTIFY_SHORT_NAME_CHANGES', 'true').lower() == 'true'  # Изменения кратких названий
NOTIFY_OGRN_CHANGES = os.getenv('NOTIFY_OGRN_CHANGES', 'true').lower() == 'true'  # Изменения ОГРН
NOTIFY_INN_CHANGES = os.getenv('NOTIFY_INN_CHANGES', 'true').lower() == 'true'  # Изменения ИНН
NOTIFY_EMAIL_CHANGES = os.getenv('NOTIFY_EMAIL_CHANGES', 'true').lower() == 'true'  # Изменения email
NOTIFY_WEBSITE_CHANGES = os.getenv('NOTIFY_WEBSITE_CHANGES', 'true').lower() == 'true'  # Изменения веб-сайтов
NOTIFY_REGISTRY_URL_CHANGES = os.getenv('NOTIFY_REGISTRY_URL_CHANGES', 'true').lower() == 'true'  # Изменения URL реестров
NOTIFY_ADDRESS_CHANGES = os.getenv('NOTIFY_ADDRESS_CHANGES', 'true').lower() == 'true'  # Изменения адресов
NOTIFY_PAK_CHANGES = os.getenv('NOTIFY_PAK_CHANGES', 'true').lower() == 'true'  # Изменения ПАК
NOTIFY_CERTIFICATE_CHANGES = os.getenv('NOTIFY_CERTIFICATE_CHANGES', 'true').lower() == 'true'  # Изменения сертификатов
NOTIFY_OTHER_CHANGES = os.getenv('NOTIFY_OTHER_CHANGES', 'true').lower() == 'true'  # Прочие изменения
NOTIFY_EXPIRING_CRL = os.getenv('NOTIFY_EXPIRING_CRL', 'true').lower() == 'true'  # Истекающие CRL
NOTIFY_EXPIRED_CRL = os.getenv('NOTIFY_EXPIRED_CRL', 'true').lower() == 'true'  # Истекшие CRL
NOTIFY_NEW_CRL = os.getenv('NOTIFY_NEW_CRL', 'true').lower() == 'true'  # Новые версии CRL
NOTIFY_MISSED_CRL = os.getenv('NOTIFY_MISSED_CRL', 'true').lower() == 'true'  # Пропущенные CRL
NOTIFY_WEEKLY_STATS = os.getenv('NOTIFY_WEEKLY_STATS', 'true').lower() == 'true'  # Недельная статистика

# --- Остальные настройки ---
# Список CDP источников
CDP_SOURCES = [
    # 'http://pki.tax.gov.ru/cdp/',
    #  'http://cdp.tax.gov.ru/cdp/',
    # Добавьте новые источники здесь
]

# Известные пути к CRL файлам (резервный метод)
KNOWN_CRL_PATHS = [
    # 'crl1.crl',
    # 'crl2.crl', 
    # 'gucrl.crl',
    # 'tcs.crl',
    # 'ca.crl',
    # 'guc_gost12.crl',
    # 'guc2021.crl',
    # 'guc2022.crl'
]

# Пороговые значения для уведомлений (в часах)
ALERT_THRESHOLDS = [4, 2]

# Интервалы проверки (в минутах)
CHECK_INTERVAL = 60  # Основная проверка CRL
AVAILABILITY_CHECK_INTERVAL = 60  # Проверка доступности URL

# Московский часовой пояс (UTC+3)
MOSCOW_TZ = timezone(timedelta(hours=3))

# --- Конфигурация для TSL Monitor ---
TSL_CHECK_INTERVAL_HOURS = 3

# --- Метрики и здоровье ---
METRICS_PORT = int(os.getenv('METRICS_PORT', '8000'))

# --- Конфигурация для CRL Monitor ---
# Режим работы: только ФНС (true) или все УЦ из TSL (false)
# Значение берется из переменной окружения FNS_ONLY, по умолчанию False
FNS_ONLY = os.getenv('FNS_ONLY', 'false').lower() == 'true'

# Домены ФНС для фильтрации в режиме FNS_ONLY
FNS_DOMAINS = ('tax.gov.ru', 'nalog.gov.ru', 'nalog.ru')

# Файлы данных
DATA_DIR = '/app/data'
CRL_CACHE_DIR = f'{DATA_DIR}/crl_cache'
LOG_FILE = f'{DATA_DIR}/logs/crl_monitor.log'
STATE_FILE = f'{DATA_DIR}/crl_state.json'
STATS_FILE = f'{DATA_DIR}/weekly_stats.json'
DB_PATH = f'{DATA_DIR}/crlchecker.db'

# Путь к файлу с URL CRL из TSL (используется в crl_monitor.py)
TSL_CRL_URLS_FILE = os.path.join(DATA_DIR, 'crl_urls_from_tsl.txt')

# Таймаут для проверки доступности (в секундах)
AVAILABILITY_TIMEOUT = 10

# Проверка TLS-сертификатов при HTTP-запросах (GET/HEAD)
# Можно отключить в средах с нестандартными цепочками: VERIFY_TLS=false
VERIFY_TLS = os.getenv('VERIFY_TLS', 'true').lower() == 'true'

# Настройки базы данных
DB_ENABLED = True

# Показывать размер CRL в уведомлениях
SHOW_CRL_SIZE_MB = True

# Фильтры TSL
TSL_OGRN_LIST = os.getenv('TSL_OGRN_LIST', '').split(',') if os.getenv('TSL_OGRN_LIST') else None
TSL_REGISTRY_NUMBERS = os.getenv('TSL_REGISTRY_NUMBERS', '').split(',') if os.getenv('TSL_REGISTRY_NUMBERS') else None