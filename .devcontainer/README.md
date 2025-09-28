# CRLChecker Development Container

Этот devcontainer предоставляет полную среду разработки для CRLChecker с предустановленными инструментами и настройками.

## 🚀 Быстрый старт

### 1. Требования
- [VS Code](https://code.visualstudio.com/)
- [Dev Containers extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers)
- [Docker](https://www.docker.com/)

### 2. Запуск
1. Откройте проект в VS Code
2. Нажмите `Ctrl+Shift+P` (или `Cmd+Shift+P` на Mac)
3. Выберите "Dev Containers: Reopen in Container"
4. Дождитесь сборки контейнера

### 3. Настройка
После запуска контейнера:
```bash
# Скопируйте файл с переменными окружения
cp env.example .env

# Отредактируйте .env файл с вашими настройками
nano .env
```

## 🛠️ Включенные инструменты

### Python
- Python 3.11
- pip (последняя версия)
- setuptools (последняя версия)

### VS Code Extensions
- **Python** - поддержка Python
- **Pylint** - линтер для Python
- **Black Formatter** - форматирование кода
- **isort** - сортировка импортов
- **Jupyter** - поддержка Jupyter notebooks
- **YAML** - поддержка YAML файлов
- **Kubernetes** - поддержка Kubernetes
- **Remote Containers** - работа с контейнерами

### Системные утилиты
- curl, wget - для HTTP запросов
- sqlite3 - для работы с базой данных
- jq - для работы с JSON
- openssl - для работы с сертификатами

## 📁 Структура проекта

```
/app/
├── crl_monitor.py      # Основной монитор CRL
├── tsl_monitor.py      # Монитор TSL
├── crl_parser.py       # Парсер CRL
├── telegram_notifier.py # Уведомления в Telegram
├── db.py               # Работа с базой данных
├── config.py           # Конфигурация
├── data/               # Данные (монтируется)
│   ├── crlchecker.db   # База данных SQLite
│   ├── logs/           # Логи
│   └── stats/          # Статистика
└── .devcontainer/      # Настройки devcontainer
```

## 🎯 Команды разработки

### Запуск системы
```bash
# Полный мониторинг
python run_all_monitors.py

# Только CRL мониторинг
python crl_monitor.py

# Только TSL мониторинг
python tsl_monitor.py
```

### Отладка
```bash
# Отладка парсинга CRL
python debug_crl.py

# Проверка базы данных
sqlite3 data/crlchecker.db "SELECT COUNT(*) FROM crl_state;"
```

### Тестирование
```bash
# Запуск в режиме Dry-run (без отправки уведомлений)
export DRY_RUN=true
python run_all_monitors.py
```

## 🔧 Настройки разработки

### Переменные окружения
Скопируйте `env.example` в `.env` и настройте:

```bash
# Обязательные
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# Опциональные
CDP_SOURCES=http://pki.tax.gov.ru/cdp/,http://cdp.tax.gov.ru/cdp/
TSL_OGRN_LIST=1047702026701,1027700132195
TSL_REGISTRY_NUMBERS=81,72,10
```

### Настройки VS Code
- **Автоформатирование** включено (Black formatter)
- **Сортировка импортов** включена (isort)
- **Линтинг** включен (Pylint)
- **Исключения файлов**: `__pycache__`, `*.pyc`, `data/`, `logs/`

## 📊 Мониторинг

### Метрики
- **URL**: http://localhost:8000
- **Эндпоинты**:
  - `/metrics` - Prometheus метрики
  - `/health` - проверка здоровья

### Логи
```bash
# Просмотр логов
tail -f data/logs/crl_monitor.log
tail -f data/logs/tsl_monitor.log

# Логи контейнера
docker logs crlchecker-dev
```

## 🐛 Отладка

### Проблемы с запуском
```bash
# Проверка переменных окружения
env | grep TELEGRAM

# Проверка базы данных
sqlite3 data/crlchecker.db ".tables"

# Проверка сертификатов
openssl version
```

### Проблемы с сетью
```bash
# Тест подключения к CRL
curl -I http://pki.tax.gov.ru/cdp/

# Проверка DNS
nslookup pki.tax.gov.ru
```

## 📚 Полезные ссылки

- [VS Code Dev Containers](https://code.visualstudio.com/docs/remote/containers)
- [Python в VS Code](https://code.visualstudio.com/docs/languages/python)
- [Docker Compose](https://docs.docker.com/compose/)
- [SQLite документация](https://www.sqlite.org/docs.html)

## 🤝 Вклад в проект

1. Создайте feature branch
2. Внесите изменения
3. Протестируйте в devcontainer
4. Создайте Pull Request

Удачной разработки! 🎉
