# 🚀 CRLChecker DevContainer - Быстрый старт

## 1. Подготовка

### Требования
- [VS Code](https://code.visualstudio.com/)
- [Dev Containers extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers)
- [Docker](https://www.docker.com/)

### Установка расширения
1. Откройте VS Code
2. Перейдите в Extensions (`Ctrl+Shift+X`)
3. Найдите "Dev Containers"
4. Установите расширение от Microsoft

## 2. Запуск проекта

### Шаг 1: Открытие проекта
```bash
# Клонируйте репозиторий
git clone <repository-url>
cd crlchecker

# Откройте в VS Code
code .
```

### Шаг 2: Запуск в контейнере
1. В VS Code нажмите `Ctrl+Shift+P` (или `Cmd+Shift+P` на Mac)
2. Введите "Dev Containers: Reopen in Container"
3. Выберите эту команду
4. Дождитесь сборки контейнера (2-3 минуты)

### Шаг 3: Настройка
После запуска контейнера выполните:
```bash
# Скопируйте файл с переменными
cp .devcontainer/env.example .env

# Отредактируйте настройки
nano .env
```

Заполните обязательные поля:
```bash
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
```

## 3. Тестирование

### Проверка работоспособности
```bash
# Запустите тестовый скрипт
python test-dev.py
```

### Отладка CRL
```bash
# Тест парсинга конкретного CRL
python debug_crl.py "http://pki.tax.gov.ru/cdp/d156fb382c4c55ad7eb3ae0ac66749577f87e116.crl"
```

### Запуск мониторинга
```bash
# Полный мониторинг (в режиме Dry-run)
python run_all_monitors.py

# Только CRL мониторинг
python crl_monitor.py

# Только TSL мониторинг
python tsl_monitor.py
```

## 4. Полезные команды

### Работа с базой данных
```bash
# Подключение к БД
sqlite3 data/crlchecker.db

# Просмотр таблиц
.tables

# Количество CRL
SELECT COUNT(*) FROM crl_state;

# Выход
.quit
```

### Просмотр логов
```bash
# Логи CRL монитора
tail -f data/logs/crl_monitor.log

# Логи TSL монитора
tail -f data/logs/tsl_monitor.log
```

### Метрики
- **URL**: http://localhost:8000
- **Prometheus**: http://localhost:8000/metrics
- **Health**: http://localhost:8000/healthz

## 5. Разработка

### Структура проекта
```
/app/
├── crl_monitor.py      # Основной монитор CRL
├── tsl_monitor.py      # Монитор TSL
├── crl_parser.py       # Парсер CRL
├── telegram_notifier.py # Уведомления
├── db.py               # База данных
├── config.py           # Конфигурация
├── data/               # Данные
│   ├── crlchecker.db   # SQLite БД
│   ├── logs/           # Логи
│   └── stats/          # Статистика
└── .devcontainer/      # Настройки devcontainer
```

### Настройки VS Code
- **Автоформатирование**: Black formatter
- **Линтинг**: Pylint
- **Сортировка импортов**: isort
- **Исключения**: `__pycache__`, `*.pyc`, `data/`, `logs/`

### Переменные окружения
```bash
# Основные
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# Режимы
FNS_ONLY=false                    # Все УЦ или только ФНС
DRY_RUN=true                     # Режим без отправки уведомлений
DB_ENABLED=true                  # Использование БД
VERIFY_TLS=false                 # Проверка TLS

# Фильтрация TSL
TSL_OGRN_LIST=1047702026701,1027700132195
TSL_REGISTRY_NUMBERS=81,72,10

# Кастомные источники CRL
CDP_SOURCES=http://pki.tax.gov.ru/cdp/,http://cdp.tax.gov.ru/cdp/
```

## 6. Решение проблем

### Контейнер не запускается
```bash
# Проверьте Docker
docker --version
docker ps

# Пересоберите контейнер
# В VS Code: Ctrl+Shift+P → "Dev Containers: Rebuild Container"
```

### Ошибки импорта
```bash
# Установите зависимости
pip install -r requirements.txt

# Проверьте Python путь
python -c "import sys; print(sys.path)"
```

### Проблемы с базой данных
```bash
# Инициализируйте БД
python -c "from db import init_db; init_db()"

# Проверьте права доступа
ls -la data/
```

### Проблемы с сетью
```bash
# Тест подключения
curl -I http://pki.tax.gov.ru/cdp/

# Проверка DNS
nslookup pki.tax.gov.ru
```

## 7. Полезные ссылки

- [VS Code Dev Containers](https://code.visualstudio.com/docs/remote/containers)
- [Python в VS Code](https://code.visualstudio.com/docs/languages/python)
- [Docker Compose](https://docs.docker.com/compose/)
- [SQLite документация](https://www.sqlite.org/docs.html)

---

**Готово!** 🎉 Теперь вы можете разрабатывать CRLChecker в удобной среде с предустановленными инструментами.

