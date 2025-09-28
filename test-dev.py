#!/usr/bin/env python3
"""
CRLChecker Development Test Script
Быстрое тестирование функциональности в devcontainer
"""

import sys
import os
import time
from datetime import datetime

# Добавляем путь к модулям
sys.path.insert(0, '/app')

def test_imports():
    """Тест импорта модулей"""
    print("🔍 Тестирование импорта модулей...")
    
    try:
        import config
        print("✅ config.py - OK")
    except Exception as e:
        print(f"❌ config.py - Ошибка: {e}")
        return False
    
    try:
        from db import init_db
        print("✅ db.py - OK")
    except Exception as e:
        print(f"❌ db.py - Ошибка: {e}")
        return False
    
    try:
        from crl_parser import CRLParser
        print("✅ crl_parser.py - OK")
    except Exception as e:
        print(f"❌ crl_parser.py - Ошибка: {e}")
        return False
    
    try:
        from telegram_notifier import TelegramNotifier
        print("✅ telegram_notifier.py - OK")
    except Exception as e:
        print(f"❌ telegram_notifier.py - Ошибка: {e}")
        return False
    
    return True

def test_database():
    """Тест базы данных"""
    print("\n🗄️ Тестирование базы данных...")
    
    try:
        from db import init_db, get_connection
        
        # Инициализация БД
        init_db()
        print("✅ База данных инициализирована")
        
        # Проверка подключения
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        print(f"✅ Таблицы в БД: {[table[0] for table in tables]}")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Ошибка БД: {e}")
        return False

def test_crl_parser():
    """Тест парсера CRL"""
    print("\n📄 Тестирование парсера CRL...")
    
    try:
        from crl_parser import CRLParser
        
        parser = CRLParser()
        print("✅ CRLParser создан")
        
        # Тест с простым URL (может не работать без интернета)
        test_url = "http://pki.tax.gov.ru/cdp/d156fb382c4c55ad7eb3ae0ac66749577f87e116.crl"
        print(f"🔍 Тестирование URL: {test_url}")
        
        # Небольшой таймаут для теста
        info = parser.get_crl_info(test_url)
        if info:
            print("✅ CRL успешно распарсен")
            print(f"   • Отозвано сертификатов: {info.get('revoked_count', 0)}")
            print(f"   • Номер CRL: {info.get('crl_number', 'N/A')}")
        else:
            print("⚠️ CRL не удалось распарсить (возможно, нет интернета)")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка парсера: {e}")
        return False

def test_telegram():
    """Тест Telegram уведомлений"""
    print("\n📱 Тестирование Telegram...")
    
    try:
        from telegram_notifier import TelegramNotifier
        from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, DRY_RUN
        
        if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "YOUR_BOT_TOKEN":
            print("⚠️ TELEGRAM_BOT_TOKEN не настроен")
            return True
        
        if not TELEGRAM_CHAT_ID or TELEGRAM_CHAT_ID == "YOUR_CHAT_ID":
            print("⚠️ TELEGRAM_CHAT_ID не настроен")
            return True
        
        notifier = TelegramNotifier()
        print("✅ TelegramNotifier создан")
        
        if DRY_RUN:
            print("🔧 Режим DRY_RUN включен - уведомления не отправляются")
        else:
            print("⚠️ DRY_RUN отключен - уведомления будут отправлены!")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка Telegram: {e}")
        return False

def test_config():
    """Тест конфигурации"""
    print("\n⚙️ Тестирование конфигурации...")
    
    try:
        import config
        
        print(f"   • FNS_ONLY: {config.FNS_ONLY}")
        print(f"   • VERIFY_TLS: {config.VERIFY_TLS}")
        print(f"   • DRY_RUN: {config.DRY_RUN}")
        print(f"   • DB_ENABLED: {config.DB_ENABLED}")
        print(f"   • METRICS_PORT: {config.METRICS_PORT}")
        print(f"   • SHOW_CRL_SIZE_MB: {config.SHOW_CRL_SIZE_MB}")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка конфигурации: {e}")
        return False

def main():
    """Основная функция тестирования"""
    print("🧪 CRLChecker Development Test")
    print("=" * 50)
    print(f"⏰ Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🐍 Python: {sys.version}")
    print(f"📁 Рабочая директория: {os.getcwd()}")
    print()
    
    tests = [
        ("Импорт модулей", test_imports),
        ("Конфигурация", test_config),
        ("База данных", test_database),
        ("Парсер CRL", test_crl_parser),
        ("Telegram", test_telegram),
    ]
    
    results = []
    
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"❌ Критическая ошибка в {name}: {e}")
            results.append((name, False))
    
    # Итоги
    print("\n" + "=" * 50)
    print("📊 РЕЗУЛЬТАТЫ ТЕСТИРОВАНИЯ")
    print("=" * 50)
    
    passed = 0
    total = len(results)
    
    for name, result in results:
        status = "✅ ПРОЙДЕН" if result else "❌ ПРОВАЛЕН"
        print(f"{name:20} {status}")
        if result:
            passed += 1
    
    print(f"\nИтого: {passed}/{total} тестов пройдено")
    
    if passed == total:
        print("🎉 Все тесты пройдены! Система готова к работе.")
    else:
        print("⚠️ Некоторые тесты провалены. Проверьте настройки.")
    
    print("\n💡 Полезные команды:")
    print("   python debug_crl.py <URL>     - отладка CRL")
    print("   python run_all_monitors.py    - запуск мониторинга")
    print("   sqlite3 data/crlchecker.db    - работа с БД")

if __name__ == "__main__":
    main()
