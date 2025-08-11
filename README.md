# CRLChecker

## Описание

CRLChecker - это система мониторинга списков отозванных сертификатов (CRL) для обеспечения безопасности инфраструктуры открытых ключей (PKI). Система предоставляет возможность мониторинга CRL как для ФНС, так и для всех УЦ.

## Версии

### Версия для ФНС
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

### Версия для всех УЦ
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

## Типы уведомлений и их сопоставления

### 1. Уведомления TSL (Удостоверяющие Центры)

| Переменная | Значение | Тип уведомления | Описание |
|------------|----------|-----------------|----------|
| `NOTIFY_NEW_CAS` | false/true | Новые УЦ | Уведомления о новых действующих УЦ в TSL |
| `NOTIFY_DATE_CHANGES` | false/true | Изменения дат | Уведомления об изменениях дат аккредитации УЦ |
| `NOTIFY_CRL_CHANGES` | false/true | Изменения CRL | Уведомления о новых или измененных CRL у действующих УЦ |
| `NOTIFY_STATUS_CHANGES` | false/true | Изменения статуса | Уведомления об изменении статуса УЦ |

### 2. Уведомления CRL (Списки Отозванных Сертификатов)

| Переменная | Значение | Тип уведомления | Описание |
|------------|----------|-----------------|----------|
| `NOTIFY_EXPIRING_CRL` | false/true | Скоро истекает | Уведомления об истекающих CRL (по пороговым значениям) |
| `NOTIFY_EXPIRED_CRL` | false/true | Истекший | Уведомления об истекших CRL |
| `NOTIFY_NEW_CRL` | false/true | Новый CRL | Уведомления о новых версиях CRL |
| `NOTIFY_MISSED_CRL` | false/true | Пропущенный | Уведомления о неопубликованных CRL |
| `NOTIFY_WEEKLY_STATS` | false/true | Недельная статистика | Уведомления о недельной статистике отозванных сертификатов |

## Особенности

- **Фильтрация по ФНС**: Возможность включить/отключить мониторинг только УЦ ФНС (`FNS_ONLY=true`)
- **Гибкое управление уведомлениями**: Каждый тип уведомлений может быть включен/отключен отдельно
- **Поддержка нескольких источников**: Поддерживает CDP источники и известные пути к CRL файлам
- **Уведомления через Telegram**: Интеграция с Telegram для мгновенного уведомления о событиях
- **Резервные методы парсинга**: Использование OpenSSL в качестве резервного метода при ошибке парсинга cryptography

## Конфигурация

### Переменные окружения

- `TELEGRAM_BOT_TOKEN` - Токен Telegram бота
- `TELEGRAM_CHAT_ID` - ID чата для отправки уведомлений
- `FNS_ONLY` - Режим работы: только ФНС (`true`) или все УЦ (`false`)
- `NOTIFY_*` - Переключатели уведомлений по каждому типу

### Пороговые значения уведомлений

- `ALERT_THRESHOLDS` - Пороговые значения для уведомлений об истечении CRL (в часах)

## Режимы работы

### Режим ФНС (`FNS_ONLY=true`)
- Мониторит только УЦ принадлежащие ФНС
- Включены все типы уведомлений
- Подходит для мониторинга только официальных УЦ

### Режим всех УЦ (`FNS_ONLY=false`)
- Мониторит все доступные УЦ
- Отключены не критичные уведомления (`NOTIFY_EXPIRED_CRL=false`, `NOTIFY_WEEKLY_STATS=false`)
- Подходит для комплексного мониторинга PKI

## Установка и запуск

1. Настройте переменные окружения в `docker-compose.yml`
2. Запустите через Docker Compose
3. Получите уведомления в Telegram при возникновении событий

## Поддерживаемые события

- Новые действующие УЦ в TSL
- Изменения дат аккредитации УЦ
- Новые или измененные CRL у действующих УЦ
- Изменения статуса УЦ
- Скоро истекающие CRL
- Истекшие CRL
- Новые версии CRL
- Неопубликованные CRL
- Недельная статистика отозванных сертификатов

## Пример docker-compose
```yaml
  crl-monitor:
    build: 
      context: ./crlchecker/
    container_name: crl-monitor
    environment:
      - TZ=Europe/Moscow
      - TELEGRAM_BOT_TOKEN=
      - TELEGRAM_CHAT_ID=-
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
    volumes:
      - ./crlchecker/data:/app/data
    restart: unless-stopped
```