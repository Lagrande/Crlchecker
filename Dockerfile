# ./Dockerfile
FROM python:3.11-slim

# --- НАЧАЛО: Установка сертификата ---
# Устанавливаем необходимые утилиты для работы с сертификатами и обновляем систему
RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get install -y curl wget sqlite3 jq openssl ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Создаем директорию для локальных сертификатов (если еще не существует)
RUN mkdir -p /usr/local/share/ca-certificates/extra

# Копируем ваш пользовательский сертификат в контейнер
COPY certs/uc_kadastr_ru_cert.pem /usr/local/share/ca-certificates/extra/

# Обновляем хранилище сертификатов операционной системы
RUN update-ca-certificates
# --- КОНЕЦ: Установка сертификата ---

WORKDIR /app

# Обновляем pip и setuptools до последних версий
RUN pip install --upgrade pip setuptools

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod +x entrypoint.sh

ENTRYPOINT ["./entrypoint.sh"]