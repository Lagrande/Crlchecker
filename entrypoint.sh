#!/bin/bash

# Создаем директорию для данных
mkdir -p /app/data/crl_cache
mkdir -p /app/data/logs

# Устанавливаем права доступа (опционально, если требуется)
# chown -R 1000:1000 /app/data

echo "Starting TSL Monitor to fetch CRL URLs..."
# Запускаем TSL Monitor один раз в фоне, чтобы получить URL
python /app/tsl_monitor.py &
TSL_PID=$!
echo "TSL Monitor started with PID: $TSL_PID"

# Ждем несколько секунд, чтобы TSL Monitor успел выполнить первую проверку и создать файл
# Таймаут можно настроить в зависимости от скорости загрузки TSL
sleep 15

# Проверяем, завершился ли TSL Monitor успешно
if kill -0 $TSL_PID 2>/dev/null; then
    echo "TSL Monitor completed initial fetch or is still running."
    # Если он все еще работает, мы не останавливаем его, так как он по расписанию продолжит работу
else
    echo "TSL Monitor process finished (may have exited or completed initial task if it were non-looping)."
    # В текущей реализации TSL Monitor работает в цикле, поэтому это маловероятно
fi

echo "Starting CRL Monitor..."
# Теперь запускаем CRL Monitor, который будет использовать URL из файла
python /app/crl_monitor.py &
CRL_PID=$!
echo "CRL Monitor started with PID: $CRL_PID"

# Перезапускаем TSL Monitor в основном цикле (если он остановился после первой проверки)
# или просто продолжаем его работу, если он работает по расписанию
# Поскольку TSL Monitor уже запущен, нам нужно получить его PID заново или управлять им иначе
# Проще всего перезапустить его как демон, но нужно избежать дублирования.
# Лучше модифицировать TSL Monitor, чтобы он делал первую проверку и затем переходил в режим ожидания.

# Функция для корректного завершения
cleanup() {
    echo "Stopping monitors..."
    # Отправляем TERM всем дочерним процессам
    trap '' TERM # Игнорируем TERM внутри функции cleanup
    kill -TERM 0 # 0 означает все процессы в группе
    wait
    echo "Monitors stopped."
    exit 0
}

# Перехватываем сигналы завершения
trap cleanup SIGTERM SIGINT

echo "All monitors started. Waiting..."
# Ждем завершения фоновых процессов
wait
