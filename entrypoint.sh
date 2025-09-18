#!/bin/bash

# Создаем директорию для данных
mkdir -p /app/data/crl_cache
mkdir -p /app/data/logs

# Устанавливаем права доступа (опционально, если требуется)
# chown -R 1000:1000 /app/data

echo "Starting metrics server on port ${METRICS_PORT:-8000}..."
python -c "
from metrics_server import start_metrics_server, MetricsRegistry
from config import METRICS_PORT
from prometheus_client import Counter, Gauge

# Создаем метрики в основном процессе
metric_checks_total = Counter('crl_checks_total', 'Total CRL check runs', registry=MetricsRegistry.registry)
metric_processed_total = Counter('crl_processed_total', 'Processed CRL files', ['result'], registry=MetricsRegistry.registry)
metric_unique_urls = Gauge('crl_unique_urls', 'Unique CRL URLs per run', registry=MetricsRegistry.registry)
metric_skipped_empty = Counter('crl_skipped_empty', 'Skipped empty CRLs with long validity', registry=MetricsRegistry.registry)

start_metrics_server(port=METRICS_PORT)
import time
time.sleep(1e9)
" &
METRICS_PID=$!
echo "Metrics server started with PID: $METRICS_PID"

echo "Starting monitors..."
python /app/run_all_monitors.py &
MON_PID=$!
echo "Monitors started with PID: $MON_PID"

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
