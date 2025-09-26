#!/bin/bash

# Создаем директорию для данных
mkdir -p /app/data/crl_cache
mkdir -p /app/data/logs
mkdir -p /app/data/stats

# Init DB schema and optionally preload URL->CA mapping from JSON
python - <<'PY'
import os, json
from db import init_db, bulk_upsert_ca_mapping, bulk_upsert_crl_state

try:
    init_db()
    mapping_json = '/app/data/crl_url_to_ca_mapping.json'
    if os.path.exists(mapping_json):
        try:
            data = json.load(open(mapping_json, encoding='utf-8'))
            if isinstance(data, dict) and data:
                bulk_upsert_ca_mapping(data)
                print(f"Preloaded URL->CA mapping into DB: {len(data)} entries")
        except Exception as e:
            print(f"Failed to preload mapping JSON: {e}")

    # Migrate CRL state JSON into DB only if table is empty (first run)
    state_json = '/app/data/crl_state.json'
    try:
        import sqlite3
        from config import DB_PATH
        should_import = False
        with sqlite3.connect(DB_PATH) as conn:
            try:
                cur = conn.execute('SELECT COUNT(*) FROM crl_state')
                cnt = cur.fetchone()[0]
                should_import = (cnt == 0)
            except Exception:
                should_import = True
        if should_import and os.path.exists(state_json):
            try:
                st = json.load(open(state_json, encoding='utf-8'))
                if isinstance(st, dict) and st:
                    bulk_upsert_crl_state(st)
                    print(f"Preloaded CRL state into DB: {len(st)} entries")
            except Exception as e:
                print(f"Failed to preload CRL state JSON: {e}")
    except Exception as e:
        print(f"Failed to check DB state before preload: {e}")
except Exception as e:
    print(f"DB init failed: {e}")
PY

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
