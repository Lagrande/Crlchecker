# ./metrics.py
"""
Общие метрики для проекта CRL Checker
"""
from prometheus_client import Counter, Gauge
from metrics_server import MetricsRegistry

# CRL Monitor метрики
crl_checks_total = Counter('crl_checks_total', 'Total CRL check runs', registry=MetricsRegistry.registry)
crl_processed_total = Counter('crl_processed_total', 'Processed CRL files', ['result'], registry=MetricsRegistry.registry)
crl_unique_urls = Gauge('crl_unique_urls', 'Unique CRL URLs per run', registry=MetricsRegistry.registry)
crl_skipped_empty = Counter('crl_skipped_empty', 'Skipped empty CRLs with long validity', registry=MetricsRegistry.registry)
crl_download_errors = Counter('crl_download_errors_total', 'CRL download errors', ['crl_name', 'error_type'], registry=MetricsRegistry.registry)
crl_parse_errors = Counter('crl_parse_errors_total', 'CRL parsing errors', ['crl_name', 'error_type'], registry=MetricsRegistry.registry)
crl_status = Gauge('crl_status', 'CRL processing status', ['crl_name', 'status'], registry=MetricsRegistry.registry)

# TSL Monitor метрики
tsl_checks_total = Counter('tsl_checks_total', 'Total TSL check runs', registry=MetricsRegistry.registry)
tsl_fetch_status = Counter('tsl_fetch_total', 'TSL fetch attempts', ['result'], registry=MetricsRegistry.registry)
tsl_active_cas = Gauge('tsl_active_cas', 'Active CAs parsed from TSL', registry=MetricsRegistry.registry)
tsl_crl_urls = Gauge('tsl_crl_urls', 'Unique CRL URLs extracted from TSL', registry=MetricsRegistry.registry)
