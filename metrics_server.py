import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from prometheus_client import CollectorRegistry, CONTENT_TYPE_LATEST, generate_latest


class MetricsRegistry:
    registry = CollectorRegistry()


class MetricsHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/healthz' or self.path == '/health':
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'ok')
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


