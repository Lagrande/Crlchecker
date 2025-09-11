## CRLChecker

CRLChecker — система мониторинга списков отозванных сертификатов (CRL) и TSL для инфраструктуры открытых ключей (PKI). Поддерживает режим мониторинга только ФНС или всех УЦ, отправляет уведомления в Telegram, экспортирует Prometheus-метрики и предоставляет health-эндпоинт.

### Ключевые возможности
- Мониторинг CRL из CDP + CRL URL из TSL
- Режимы: только ФНС (`FNS_ONLY=true`) или все УЦ (`FNS_ONLY=false`)
- Уведомления в Telegram с антифлудом
- Резервный парсинг CRL через OpenSSL при неудаче cryptography
- Кэширование CRL и хранение состояния на диске
- Prometheus-метрики на `:8000/metrics`, health на `:8000/healthz`

### Переменные окружения
- `TELEGRAM_BOT_TOKEN`: токен Telegram-бота
- `TELEGRAM_CHAT_ID`: ID чата для уведомлений
- `FNS_ONLY`: `true` — только ФНС; `false` — все УЦ
- `VERIFY_TLS`: `true|false` — проверка TLS цепочек при HTTP-запросах (по умолчанию `true`)
- `TSL_CHECK_INTERVAL_HOURS`: период проверки TSL (по умолчанию 3 ч)
- `CHECK_INTERVAL`: период проверки CRL в минутах (см. `config.py`)
- `ALERT_THRESHOLDS`: пороги (часы) для «скоро истекает» (см. `config.py`)
- `METRICS_PORT`: порт метрик/здоровья (по умолчанию `8000`)

Уведомления TSL:
- `NOTIFY_NEW_CAS`, `NOTIFY_DATE_CHANGES`, `NOTIFY_CRL_CHANGES`, `NOTIFY_STATUS_CHANGES`

Уведомления CRL:
- `NOTIFY_EXPIRING_CRL`, `NOTIFY_EXPIRED_CRL`, `NOTIFY_NEW_CRL`, `NOTIFY_MISSED_CRL`, `NOTIFY_WEEKLY_STATS`

### Рекомендованные пресеты

Версия для ФНС
```yaml
environment:
  - TZ=Europe/Moscow
  - TELEGRAM_BOT_TOKEN=
  - TELEGRAM_CHAT_ID=
  - FNS_ONLY=true

  # Уведомления TSL
  - NOTIFY_NEW_CAS=true
  - NOTIFY_DATE_CHANGES=true
  - NOTIFY_CRL_CHANGES=true
  - NOTIFY_STATUS_CHANGES=true
    
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

  # Уведомления TSL
  - NOTIFY_NEW_CAS=true
  - NOTIFY_DATE_CHANGES=true
  - NOTIFY_CRL_CHANGES=true
  - NOTIFY_STATUS_CHANGES=true

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
      - METRICS_PORT=8000
      # Уведомления TSL
      - NOTIFY_NEW_CAS=true
      - NOTIFY_DATE_CHANGES=true
      - NOTIFY_CRL_CHANGES=true
      - NOTIFY_STATUS_CHANGES=true
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

### Структура данных
- Данные/состояние/логи в `/app/data` (маппьте volume для сохранности между рестартами)

### Триаж проблем
- Нет уведомлений в Telegram: проверьте `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, сетевой доступ.
- Ошибки TLS при TSL: добавьте корневой сертификат в `certs/` и пересоберите образ либо временно `VERIFY_TLS=false`.
- Метрики/health: проверьте проброс порта `8000` и `METRICS_PORT`.


