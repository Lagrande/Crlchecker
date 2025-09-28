## CRLChecker

CRLChecker — система мониторинга списков отозванных сертификатов (CRL) и TSL для инфраструктуры открытых ключей (PKI). Поддерживает режим мониторинга только ФНС или всех УЦ, отправляет уведомления в Telegram, экспортирует Prometheus-метрики и предоставляет health-эндпоинт.

## 🚀 Быстрый старт для разработчиков

### DevContainer (рекомендуется)
Для удобной разработки используйте VS Code Dev Containers:

1. **Требования**: VS Code + Dev Containers extension + Docker
2. **Запуск**: Откройте проект в VS Code → `Ctrl+Shift+P` → "Dev Containers: Reopen in Container"
3. **Настройка**: Скопируйте `.devcontainer/env.example` в `.env` и заполните настройки
4. **Документация**: 
   - [.devcontainer/README.md](.devcontainer/README.md) - полная документация
   - [.devcontainer/QUICKSTART.md](.devcontainer/QUICKSTART.md) - быстрый старт
5. **Тестирование**: `python test-dev.py` - проверка работоспособности

### Обычный Docker
```bash
# Клонирование и запуск
git clone <repository>
cd crlchecker
docker compose up -d
```

### Ключевые возможности
- Мониторинг CRL из CDP + CRL URL из TSL
- Режимы: только ФНС (`FNS_ONLY=true`) или все УЦ (`FNS_ONLY=false`)
- Уведомления в Telegram с антифлудом
- Резервный парсинг CRL через OpenSSL при неудаче cryptography
- Кэширование CRL и хранение состояния на диске
- Prometheus-метрики на `:8000/metrics`, health на `:8000/healthz`
- **Новое**: Детальный мониторинг изменений TSL с уведомлениями о всех типах изменений
- **Новое**: Еженедельная статистика отзыва сертификатов по УЦ и причинам
- **Новое**: Отпечатки CRL и идентификаторы ключей издателей в уведомлениях
- **Новое**: Серийные номера CRL в уведомлениях
- **Новое**: Фильтрация TSL по ОГРН и реестровым номерам

### Переменные окружения
- `TELEGRAM_BOT_TOKEN`: токен Telegram-бота
- `TELEGRAM_CHAT_ID`: ID чата для уведомлений
- `FNS_ONLY`: `true` — только ФНС; `false` — все УЦ
- `VERIFY_TLS`: `true|false` — проверка TLS цепочек при HTTP-запросах (по умолчанию `true`)
- `TSL_CHECK_INTERVAL_HOURS`: период проверки TSL (по умолчанию 3 ч)
- `CHECK_INTERVAL`: период проверки CRL в минутах (см. `config.py`)
- `ALERT_THRESHOLDS`: пороги (часы) для «скоро истекает» (см. `config.py`)
- `METRICS_PORT`: порт метрик/здоровья (по умолчанию `8000`)
- `SHOW_CRL_SIZE_MB`: `true|false` — показывать размер CRL в МБ в уведомлениях (по умолчанию `false`)
- `DB_ENABLED`: `true|false` — использовать SQLite базу данных для хранения состояния (по умолчанию `true`)
- `DB_PATH`: путь к файлу SQLite базы данных (по умолчанию `/app/data/crlchecker.db`)
- `DRY_RUN`: `true|false` — режим Dry-run без отправки уведомлений в Telegram (по умолчанию `false`)
- `CDP_SOURCES`: кастомные источники CRL (CDP) через запятую. Пример: `CDP_SOURCES=http://pki.tax.gov.ru/cdp/,http://cdp.tax.gov.ru/cdp/`

Фильтрация TSL по УЦ:
- `TSL_OGRN_LIST`: список ОГРН для точного отбора УЦ из TSL (через запятую). Пример: `TSL_OGRN_LIST=1047702026701,1027700132195`
- `TSL_REGISTRY_NUMBERS`: список префиксов реестровых номеров для отбора УЦ (через запятую). Пример: `TSL_REGISTRY_NUMBERS=72,10,123`

Принципы фильтрации:
- Если задан `TSL_OGRN_LIST`, он имеет приоритет и используется вместо `TSL_REGISTRY_NUMBERS`.
- Для `TSL_REGISTRY_NUMBERS` используется сопоставление по префиксу числа (цифры из номера в TSL нормализуются, нецифровые символы игнорируются).

Уведомления TSL:
- `NOTIFY_NEW_CAS` — новые УЦ в TSL (по умолчанию `true`)
- `NOTIFY_REMOVED_CAS` — удаленные УЦ из TSL (по умолчанию `true`)
- `NOTIFY_DATE_CHANGES` — изменения дат аккредитации (по умолчанию `true`)
- `NOTIFY_CRL_CHANGES` — изменения в списках CRL (по умолчанию `true`)
- `NOTIFY_STATUS_CHANGES` — изменения статуса УЦ (по умолчанию `true`)
- `NOTIFY_NAME_CHANGES` — изменения названий УЦ (по умолчанию `true`)
- `NOTIFY_SHORT_NAME_CHANGES` — изменения кратких названий (по умолчанию `true`)
- `NOTIFY_OGRN_CHANGES` — изменения ОГРН (по умолчанию `true`)
- `NOTIFY_INN_CHANGES` — изменения ИНН (по умолчанию `true`)
- `NOTIFY_EMAIL_CHANGES` — изменения email (по умолчанию `true`)
- `NOTIFY_WEBSITE_CHANGES` — изменения веб-сайтов (по умолчанию `true`)
- `NOTIFY_REGISTRY_URL_CHANGES` — изменения URL реестров (по умолчанию `true`)
- `NOTIFY_ADDRESS_CHANGES` — изменения адресов (по умолчанию `true`)
- `NOTIFY_PAK_CHANGES` — изменения ПАК (по умолчанию `true`)
- `NOTIFY_CERTIFICATE_CHANGES` — изменения сертификатов (по умолчанию `true`)
- `NOTIFY_OTHER_CHANGES` — прочие изменения (по умолчанию `true`)

Уведомления CRL:
- `NOTIFY_EXPIRING_CRL`, `NOTIFY_EXPIRED_CRL`, `NOTIFY_NEW_CRL`, `NOTIFY_MISSED_CRL`, `NOTIFY_WEEKLY_STATS`

### Типы уведомлений

#### Уведомления о новых CRL
```
🆕 Новая версия CRL опубликована
📁 Имя файла: example.crl
🏢 Удостоверяющий центр: Название УЦ
🔢 Реестровый номер: 123
🔗 URL: http://example.com/crl
🔢 Серийный номер CRL: 167e
🔑 Идентификатор ключа издателя: D156FB382C4C55AD7EB3AE0AC66749577F87E116
📄 Всего отозвано: 1000
📈 Прирост: +50
📅 Время публикации: 26.09.2025 20:00:00
📅 Следующее обновление: 27.09.2025 20:00:00
📦 Размер CRL: 0.15 МБ
📊 По категориям:
• Прекращение деятельности: +10
• Причина не указана: +40
```

#### Уведомления об истечении CRL
```
⚠️ ВНИМАНИЕ: CRL скоро истекает
📁 Имя файла: example.crl
🏢 Удостоверяющий центр: Название УЦ
🔢 Реестровый номер: 123
🔗 URL: http://example.com/crl
🔢 Серийный номер CRL: 167e
🔑 Идентификатор ключа издателя: D156FB382C4C55AD7EB3AE0AC66749577F87E116
⏰ Осталось: 2.5 часа
📅 Следующее обновление: 27.09.2025 10:00:00
🕐 Текущее время: 26.09.2025 21:48:57
```

#### Уведомления об истекших CRL
```
🚨 КРИТИЧНО: CRL истек
📁 Имя файла: example.crl
🏢 Удостоверяющий центр: Название УЦ
🔢 Реестровый номер: 123
🔗 URL: http://example.com/crl
🔢 Серийный номер CRL: 167e
🔑 Идентификатор ключа издателя: D156FB382C4C55AD7EB3AE0AC66749577F87E116
⏰ Истек: 26.09.2025 18:00:00
🕐 Текущее время: 26.09.2025 21:48:57
```

#### Уведомления об изменениях TSL
- **Новые УЦ**: Уведомления о добавлении новых удостоверяющих центров
- **Удаленные УЦ**: Уведомления об исключении УЦ из TSL
- **Изменения названий**: Уведомления об изменении названий УЦ
- **Изменения ОГРН/ИНН**: Уведомления об изменении регистрационных данных
- **Изменения контактной информации**: Email, веб-сайт, адрес
- **Изменения CRL**: Добавление/удаление CRL, изменение URL
- **Изменения статуса**: Изменения статуса аккредитации УЦ


### Рекомендованные пресеты

Версия для ФНС
```yaml
environment:
  - TZ=Europe/Moscow
  - TELEGRAM_BOT_TOKEN=
  - TELEGRAM_CHAT_ID=
  - FNS_ONLY=true
  - DRY_RUN=false

  # Уведомления TSL
  - NOTIFY_NEW_CAS=true
  - NOTIFY_REMOVED_CAS=true
  - NOTIFY_DATE_CHANGES=true
  - NOTIFY_CRL_CHANGES=true
  - NOTIFY_STATUS_CHANGES=true
  - NOTIFY_NAME_CHANGES=true
  - NOTIFY_SHORT_NAME_CHANGES=true
  - NOTIFY_OGRN_CHANGES=true
  - NOTIFY_INN_CHANGES=true
  - NOTIFY_EMAIL_CHANGES=true
  - NOTIFY_WEBSITE_CHANGES=true
  - NOTIFY_REGISTRY_URL_CHANGES=true
  - NOTIFY_ADDRESS_CHANGES=true
  - NOTIFY_PAK_CHANGES=true
  - NOTIFY_CERTIFICATE_CHANGES=true
  - NOTIFY_OTHER_CHANGES=true
    
  # Уведомления CRL
  - NOTIFY_EXPIRING_CRL=true
  - NOTIFY_EXPIRED_CRL=true
  - NOTIFY_NEW_CRL=true
  - NOTIFY_MISSED_CRL=true
  - NOTIFY_WEEKLY_STATS=true
```

Версия для всех УЦ
```yaml
environment:
  - TZ=Europe/Moscow
  - TELEGRAM_BOT_TOKEN=
  - TELEGRAM_CHAT_ID=
  - FNS_ONLY=false
  - DRY_RUN=false

  # Уведомления TSL
  - NOTIFY_NEW_CAS=true
  - NOTIFY_REMOVED_CAS=true
  - NOTIFY_DATE_CHANGES=true
  - NOTIFY_CRL_CHANGES=true
  - NOTIFY_STATUS_CHANGES=true
  - NOTIFY_NAME_CHANGES=true
  - NOTIFY_SHORT_NAME_CHANGES=true
  - NOTIFY_OGRN_CHANGES=true
  - NOTIFY_INN_CHANGES=true
  - NOTIFY_EMAIL_CHANGES=true
  - NOTIFY_WEBSITE_CHANGES=true
  - NOTIFY_REGISTRY_URL_CHANGES=true
  - NOTIFY_ADDRESS_CHANGES=true
  - NOTIFY_PAK_CHANGES=true
  - NOTIFY_CERTIFICATE_CHANGES=true
  - NOTIFY_OTHER_CHANGES=true

  # Уведомления CRL
  - NOTIFY_EXPIRING_CRL=true
  - NOTIFY_EXPIRED_CRL=false
  - NOTIFY_NEW_CRL=true
  - NOTIFY_MISSED_CRL=true
  - NOTIFY_WEEKLY_STATS=false
```

### Docker Compose
Создайте `docker-compose.yml` (пример ниже), задайте переменные окружения и запустите:
```bash
docker compose up -d --build
```

Проверка:
- Health: `curl http://localhost:8000/healthz` → ok
- Metrics: `curl http://localhost:8000/metrics`

### Пример docker-compose.yml
```yaml
services:
  crlchecker:
    build:
      context: .
    container_name: crlchecker
    environment:
      - TZ=Europe/Moscow
      - TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}
      - TELEGRAM_CHAT_ID=${TELEGRAM_CHAT_ID}
      - FNS_ONLY=false
      - VERIFY_TLS=false
      - DRY_RUN=false
      # Кастомные источники CRL (опционально)
      # - CDP_SOURCES=http://pki.tax.gov.ru/cdp/,http://cdp.tax.gov.ru/cdp/
      # Фильтрация TSL
      - TSL_OGRN_LIST=
      - TSL_REGISTRY_NUMBERS=
      - METRICS_PORT=8000
      # Уведомления TSL
      - NOTIFY_NEW_CAS=true
      - NOTIFY_REMOVED_CAS=true
      - NOTIFY_DATE_CHANGES=true
      - NOTIFY_CRL_CHANGES=true
      - NOTIFY_STATUS_CHANGES=true
      - NOTIFY_NAME_CHANGES=true
      - NOTIFY_SHORT_NAME_CHANGES=true
      - NOTIFY_OGRN_CHANGES=true
      - NOTIFY_INN_CHANGES=true
      - NOTIFY_EMAIL_CHANGES=true
      - NOTIFY_WEBSITE_CHANGES=true
      - NOTIFY_REGISTRY_URL_CHANGES=true
      - NOTIFY_ADDRESS_CHANGES=true
      - NOTIFY_PAK_CHANGES=true
      - NOTIFY_CERTIFICATE_CHANGES=true
      - NOTIFY_OTHER_CHANGES=true
      # Уведомления CRL
      - NOTIFY_EXPIRING_CRL=true
      - NOTIFY_EXPIRED_CRL=false
      - NOTIFY_NEW_CRL=true
      - NOTIFY_MISSED_CRL=true
      - NOTIFY_WEEKLY_STATS=false
    volumes:
      - ./data:/app/data
    ports:
      - "8000:8000" # /metrics, /healthz
    restart: unless-stopped
```

Примечания:
- Для сред с кастомными корневыми сертификатами добавьте PEM в `certs/` и пересоберите образ — он будет добавлен в trust store контейнера.
- Если TLS к TSL хосту нестабилен, временно установите `VERIFY_TLS=false` (диагностика/байпас). Лучше добавить корректную CA-цепочку.

### Локальный запуск без Compose
```bash
pip install -r requirements.txt
export TELEGRAM_BOT_TOKEN=...
export TELEGRAM_CHAT_ID=...
python run_all_monitors.py
```

### Экспортируемые метрики (основные)
- `crl_checks_total` — количество запусков проверки CRL
- `crl_processed_total{result}` — обработка CRL (success/error/failed_group)
- `crl_unique_urls` — число уникальных CRL за прогон
- `tsl_checks_total` — количество запусков проверки TSL
- `tsl_fetch_total{result}` — попытки загрузки TSL (success/error)
- `tsl_active_cas` — число действующих УЦ (из TSL)
- `tsl_crl_urls` — число CRL URL, извлечённых из TSL
- **Новое**: `crl_revoked_certificates_total{ca_name,crl_name,reason}` — количество отозванных сертификатов по УЦ, CRL и причинам
- **Новое**: `crl_weekly_stats_total{ca_name,crl_name,reason}` — еженедельная статистика отзыва сертификатов
- **Новое**: `tsl_changes_total{change_type}` — количество изменений в TSL по типам

### Структура данных
- Данные/состояние/логи в `/app/data` (маппьте volume для сохранности между рестартами)
- **Новое**: SQLite база данных для хранения состояния CRL и еженедельной статистики
- **Новое**: Еженедельные отчеты в формате CSV/JSON в папке `/app/data/stats/`
- **Новое**: Детальная статистика отзыва сертификатов по УЦ, CRL и причинам

#### Файлы данных
- `crlchecker.db` — SQLite база данных с состоянием CRL и статистикой
- `crl_state.json` — резервное хранение состояния CRL (fallback)
- `crl_url_to_ca_mapping.json` — соответствие URL CRL и УЦ
- `crl_urls_from_tsl.txt` — список URL CRL из TSL
- `weekly_stats.json` — еженедельная статистика
- `stats/` — папка с еженедельными отчетами (создается автоматически)
- `crl_cache/` — кэш загруженных CRL
- `logs/` — логи приложения

### Триаж проблем
- Нет уведомлений в Telegram: проверьте `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, сетевой доступ.
- Ошибки TLS при TSL: добавьте корневой сертификат в `certs/` и пересоберите образ либо временно `VERIFY_TLS=false`.
- Метрики/health: проверьте проброс порта `8000` и `METRICS_PORT`.
- **Новое**: Проблемы с базой данных: проверьте права доступа к `/app/data/` и `DB_ENABLED=true`.
- **Новое**: Отсутствие еженедельной статистики: убедитесь, что `NOTIFY_WEEKLY_STATS=true` и папка `stats/` создана.
- **Новое**: Дублирование уведомлений после перезапуска: проверьте, что состояние корректно сохраняется в БД.
- **Новое**: Проблемы с фильтрацией TSL: проверьте корректность `TSL_OGRN_LIST` или `TSL_REGISTRY_NUMBERS`.
- **Новое**: Тестирование без отправки уведомлений: установите `DRY_RUN=true` для отладки.

### Новые возможности

#### Детальный мониторинг TSL
Система теперь отслеживает все изменения в TSL.xml и отправляет уведомления о:
- Добавлении/удалении УЦ
- Изменениях в названиях, ОГРН, ИНН
- Изменениях контактной информации
- Изменениях в списках CRL
- Изменениях статуса аккредитации

#### Еженедельная статистика
- Автоматический расчет статистики отзыва сертификатов по УЦ и причинам
- Создание отчетов в формате CSV/JSON каждый понедельник
- Детализация по категориям отзыва (прекращение деятельности, компрометация ключа и т.д.)
- Топ-списки УЦ по количеству отзывов

#### Улучшенные уведомления CRL
- Отпечатки CRL (SHA-1 хеш DER-кодированного CRL)
- Идентификаторы ключей издателей (Authority Key Identifier)
- Серийные номера CRL без ведущих нулей
- Размеры CRL в МБ (опционально)
- Детализация по причинам отзыва сертификатов

#### Фильтрация TSL
- Точная фильтрация по ОГРН (приоритетная)
- Фильтрация по префиксам реестровых номеров
- Гибкая настройка через переменные окружения

#### Надежное хранение состояния
- SQLite база данных для персистентного хранения
- Резервное хранение в JSON файлах
- Защита от дублирования уведомлений после перезапуска
- Автоматическая миграция данных при обновлении

#### Режим Dry-run
- Тестирование системы без отправки уведомлений в Telegram
- Все уведомления логируются в консоль с префиксом `[DRY-RUN]`
- Полезно для отладки и тестирования новых функций
- Включается переменной окружения `DRY_RUN=true`

### Запросы к базе данных

Система использует SQLite базу данных для хранения состояния CRL. Вот полезные запросы для анализа данных:

> **💡 Совет:** Все запросы выполняются внутри контейнера. Убедитесь, что контейнер запущен: `docker compose up -d`

#### 🔍 **Общая статистика**
```bash
# Общее количество CRL в базе
docker exec crlchecker sqlite3 /app/data/crlchecker.db "SELECT COUNT(*) as total_crls FROM crl_state;"

# Количество CRL по УЦ
docker exec crlchecker sqlite3 /app/data/crlchecker.db "SELECT ca_name, COUNT(*) as crl_count FROM crl_state GROUP BY ca_name ORDER BY crl_count DESC LIMIT 10;"
```

#### ⚠️ **Брошенные CRL (просроченные больше месяца)**
```bash
# ТОП самых старых брошенных CRL
docker exec crlchecker sqlite3 /app/data/crlchecker.db "SELECT crl_name, ca_name, ca_reg_number, url, next_update, revoked_count, last_check, ROUND((julianday('now') - julianday(next_update)), 1) as days_expired FROM crl_state WHERE next_update IS NOT NULL AND datetime(next_update) < datetime('now', '-1 month') ORDER BY days_expired DESC LIMIT 50;"

# Количество брошенных CRL
docker exec crlchecker sqlite3 /app/data/crlchecker.db "SELECT COUNT(*) as abandoned_crls FROM crl_state WHERE next_update IS NOT NULL AND datetime(next_update) < datetime('now', '-1 month');"

# Группировка брошенных CRL по УЦ
docker exec crlchecker sqlite3 /app/data/crlchecker.db "SELECT ca_name, ca_reg_number, COUNT(*) as abandoned_crls_count, GROUP_CONCAT(crl_name, ', ') as abandoned_crl_names FROM crl_state WHERE next_update IS NOT NULL AND datetime(next_update) < datetime('now', '-1 month') GROUP BY ca_name, ca_reg_number ORDER BY abandoned_crls_count DESC;"


```

#### 📊 **Статистика по отозванным сертификатам**
```bash
# Топ-10 CRL с наибольшим количеством отозванных сертификатов
docker exec crlchecker sqlite3 /app/data/crlchecker.db "SELECT crl_name, ca_name, revoked_count, last_check FROM crl_state WHERE revoked_count > 0 ORDER BY revoked_count DESC LIMIT 10;"

# Общее количество отозванных сертификатов
docker exec crlchecker sqlite3 /app/data/crlchecker.db "SELECT SUM(revoked_count) as total_revoked FROM crl_state WHERE revoked_count > 0;"
```

#### 🏢 **Статистика по УЦ**
```bash
# УЦ с наибольшим количеством CRL
docker exec crlchecker sqlite3 /app/data/crlchecker.db "SELECT ca_name, ca_reg_number, COUNT(*) as crl_count, SUM(revoked_count) as total_revoked FROM crl_state GROUP BY ca_name, ca_reg_number ORDER BY crl_count DESC LIMIT 10;"

# УЦ с наибольшим количеством отозванных сертификатов
docker exec crlchecker sqlite3 /app/data/crlchecker.db "SELECT ca_name, ca_reg_number, SUM(revoked_count) as total_revoked, COUNT(*) as crl_count FROM crl_state WHERE revoked_count > 0 GROUP BY ca_name, ca_reg_number ORDER BY total_revoked DESC LIMIT 10;"
```

#### 📅 **Анализ по времени**
```bash
# CRL, обновленные за последние 24 часа
docker exec crlchecker sqlite3 /app/data/crlchecker.db "SELECT crl_name, ca_name, last_check FROM crl_state WHERE last_check > datetime('now', '-1 day') ORDER BY last_check DESC;"
```

#### 🔧 **Техническая информация**
```bash
# Структура таблицы crl_state
docker exec crlchecker sqlite3 /app/data/crlchecker.db ".schema crl_state"

# Размер базы данных
docker exec crlchecker sqlite3 /app/data/crlchecker.db "SELECT page_count * page_size as size_bytes FROM pragma_page_count(), pragma_page_size();"
```

#### 📈 **Еженедельная статистика**
```bash
# Статистика по недельным отчетам (если включена)
docker exec crlchecker sqlite3 /app/data/crlchecker.db "SELECT * FROM weekly_stats ORDER BY week_start DESC LIMIT 5;"

# Детальная статистика по категориям отзыва
docker exec crlchecker sqlite3 /app/data/crlchecker.db "SELECT week_start, ca_name, category, count FROM weekly_details ORDER BY week_start DESC, count DESC LIMIT 10;"
```

#### 🔍 **Поиск и фильтрация**
```bash
# Поиск CRL по имени УЦ
docker exec crlchecker sqlite3 /app/data/crlchecker.db "SELECT crl_name, ca_name, url, revoked_count FROM crl_state WHERE ca_name LIKE '%Сбербанк%' ORDER BY revoked_count DESC;"

# Поиск CRL по реестровому номеру
docker exec crlchecker sqlite3 /app/data/crlchecker.db "SELECT crl_name, ca_name, ca_reg_number, url FROM crl_state WHERE ca_reg_number = '81';"

# CRL с определенным доменом в URL
docker exec crlchecker sqlite3 /app/data/crlchecker.db "SELECT crl_name, ca_name, url FROM crl_state WHERE url LIKE '%tax.gov.ru%';"
```

#### 🛠️ **Управление данными**
```bash
# Очистка старых записей (старше 1 года)
docker exec crlchecker sqlite3 /app/data/crlchecker.db "DELETE FROM crl_state WHERE last_check < datetime('now', '-1 year');"

# Обновление информации об УЦ
docker exec crlchecker sqlite3 /app/data/crlchecker.db "UPDATE crl_state SET ca_name = 'Новое название УЦ' WHERE ca_reg_number = '123';"

# Экспорт данных в CSV
docker exec crlchecker sqlite3 /app/data/crlchecker.db -header -csv "SELECT * FROM crl_state;" > crl_export.csv
```

#### 📋 **Примеры для мониторинга**
```bash
# Еженедельный отчет о брошенных CRL
docker exec crlchecker sqlite3 /app/data/crlchecker.db "SELECT ca_name, COUNT(*) as abandoned_count FROM crl_state WHERE next_update IS NOT NULL AND datetime(next_update) < datetime('now', '-1 month') GROUP BY ca_name ORDER BY abandoned_count DESC;"






