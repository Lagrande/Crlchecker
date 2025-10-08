import threading
import json
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
from prometheus_client import CollectorRegistry, CONTENT_TYPE_LATEST, generate_latest


class MetricsRegistry:
    registry = CollectorRegistry()


def check_system_health():
    """Проверяет состояние системы и возвращает информацию о здоровье"""
    issues = []
    
    # Проверяем доступность директорий
    data_dir = '/app/data'
    if not os.path.exists(data_dir):
        issues.append("Data directory not found")
    elif not os.access(data_dir, os.W_OK):
        issues.append("Data directory not writable")
    
    # Проверяем доступность логов
    log_dir = '/app/data/logs'
    if not os.path.exists(log_dir):
        issues.append("Log directory not found")
    elif not os.access(log_dir, os.W_OK):
        issues.append("Log directory not writable")
    
    # Проверяем доступность кэша CRL
    cache_dir = '/app/data/crl_cache'
    if not os.path.exists(cache_dir):
        issues.append("CRL cache directory not found")
    elif not os.access(cache_dir, os.W_OK):
        issues.append("CRL cache directory not writable")
    
    # Проверяем файлы состояния
    state_file = '/app/data/crl_state.json'
    if os.path.exists(state_file) and not os.access(state_file, os.R_OK):
        issues.append("State file not readable")
    
    # Проверяем метрики
    try:
        metrics_output = generate_latest(MetricsRegistry.registry)
        if not metrics_output:
            issues.append("No metrics available")
    except Exception as e:
        issues.append(f"Metrics error: {str(e)}")
    
    if issues:
        return {
            "is_healthy": False,
            "issues": issues,
            "status": "unhealthy"
        }
    else:
        return {
            "is_healthy": True,
            "status": "healthy",
            "checks": {
                "data_directory": "ok",
                "log_directory": "ok", 
                "cache_directory": "ok",
                "state_file": "ok",
                "metrics": "ok"
            }
        }


class MetricsHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/healthz' or self.path == '/health':
            health_status = check_system_health()
            
            if health_status['is_healthy']:
                self.send_response(200)
            else:
                self.send_response(503)  # Service Unavailable
            
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            
            response = json.dumps(health_status, ensure_ascii=False, indent=2)
            self.wfile.write(response.encode('utf-8'))
            return
        if self.path == '/metrics':
            output = generate_latest(MetricsRegistry.registry)
            self.send_response(200)
            self.send_header('Content-Type', CONTENT_TYPE_LATEST)
            self.end_headers()
            self.wfile.write(output)
            return
        self.send_response(404)
        self.end_headers()


def start_metrics_server(host: str = '0.0.0.0', port: int = 8000):
    server = HTTPServer((host, port), MetricsHandler)
    thread = threading.Thread(target=server.serve_forever, name='MetricsHTTP', daemon=True)
    thread.start()
    return server


