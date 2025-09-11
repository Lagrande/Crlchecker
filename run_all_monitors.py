# ./run_all_monitors.py
import threading
import time
import logging
from crl_monitor import CRLMonitor
from tsl_monitor import TSLMonitor

def run_crl_monitor():
    monitor = CRLMonitor()
    monitor.run()

def run_tsl_monitor():
    monitor = TSLMonitor()
    monitor.run()

if __name__ == "__main__":
    # Настройка логирования
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Создаем потоки для каждого монитора
    crl_thread = threading.Thread(target=run_crl_monitor, name="CRLMonitorThread")
    tsl_thread = threading.Thread(target=run_tsl_monitor, name="TSLMonitorThread")
    
    # Запускаем потоки
    crl_thread.start()
    tsl_thread.start()
    
    try:
        # Ждем завершения (на самом деле они работают бесконечно)
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Получен сигнал завершения, ожидание остановки потоков...")
        # В реальном приложении здесь должна быть логика корректной остановки
        # Для простоты просто выходим
        exit(0)
