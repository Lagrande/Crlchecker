#!/usr/bin/env python3
"""
CRLChecker Debug Script
Позволяет отладить парсинг конкретного CRL файла
"""

import sys
import os
import argparse
from datetime import datetime

# Добавляем путь к модулям
sys.path.insert(0, '/app')

from crl_parser import CRLParser
from config import VERIFY_TLS, SHOW_CRL_SIZE_MB

def debug_crl(url, save_file=False):
    """Отладка парсинга CRL"""
    print(f"🔍 Отладка CRL: {url}")
    print("=" * 60)
    
    parser = CRLParser()
    
    try:
        # Получаем информацию о CRL
        info = parser.get_crl_info(url)
        
        if info:
            print("✅ CRL успешно распарсен!")
            print()
            
            # Основная информация
            print("📋 Основная информация:")
            print(f"  • Время публикации: {info.get('this_update', 'N/A')}")
            print(f"  • Следующее обновление: {info.get('next_update', 'N/A')}")
            print(f"  • Количество отозванных: {info.get('revoked_count', 0)}")
            print(f"  • Номер CRL: {info.get('crl_number', 'N/A')}")
            print(f"  • Издатель: {info.get('issuer', 'N/A')}")
            print(f"  • Отпечаток CRL: {info.get('crl_fingerprint', 'N/A')}")
            print(f"  • Идентификатор ключа: {info.get('crl_key_identifier', 'N/A')}")
            print(f"  • Delta CRL: {'Да' if info.get('is_delta', False) else 'Нет'}")
            
            # Информация о размере
            if SHOW_CRL_SIZE_MB and 'size_mb' in info:
                print(f"  • Размер: {info['size_mb']:.2f} МБ")
            
            # Отозванные сертификаты
            revoked_certs = info.get('revoked_certificates', [])
            if revoked_certs:
                print()
                print(f"📜 Отозванные сертификаты ({len(revoked_certs)}):")
                for i, cert in enumerate(revoked_certs[:10]):  # Показываем первые 10
                    print(f"  {i+1}. Серийный номер: {cert.get('serial_number', 'N/A')}")
                    print(f"     Дата отзыва: {cert.get('revocation_date', 'N/A')}")
                    print(f"     Причина: {cert.get('reason', 'Не указана')}")
                    print()
                
                if len(revoked_certs) > 10:
                    print(f"  ... и еще {len(revoked_certs) - 10} сертификатов")
            
            # Сохранение в файл для детального анализа
            if save_file:
                filename = f"debug_crl_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                import json
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(info, f, indent=2, ensure_ascii=False, default=str)
                print(f"💾 Детальная информация сохранена в {filename}")
            
        else:
            print("❌ Не удалось получить информацию о CRL")
            
    except Exception as e:
        print(f"❌ Ошибка при отладке CRL: {e}")
        import traceback
        traceback.print_exc()

def main():
    parser = argparse.ArgumentParser(description='Отладка парсинга CRL')
    parser.add_argument('url', help='URL CRL файла для отладки')
    parser.add_argument('--save', action='store_true', help='Сохранить детальную информацию в JSON файл')
    
    args = parser.parse_args()
    
    print("🔧 CRLChecker Debug Tool")
    print(f"🌐 URL: {args.url}")
    print(f"🔒 Проверка TLS: {'Включена' if VERIFY_TLS else 'Отключена'}")
    print(f"📏 Показ размера: {'Включен' if SHOW_CRL_SIZE_MB else 'Отключен'}")
    print()
    
    debug_crl(args.url, args.save)

if __name__ == "__main__":
    main()