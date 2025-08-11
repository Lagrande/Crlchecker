#!/usr/bin/env python3

import requests
from bs4 import BeautifulSoup
import re

def debug_cdp_parsing(cdp_url):
    """Отладка парсинга CDP"""
    print(f"Анализ {cdp_url}")
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(cdp_url, timeout=30, headers=headers)
        print(f"Статус: {response.status_code}")
        print(f"Content-Type: {response.headers.get('content-type', 'не указан')}")
        
        # Ищем все ссылки
        links = re.findall(r'href=["\']([^"\']*)["\']', response.text, re.IGNORECASE)
        print(f"Найдено {len(links)} ссылок:")
        for link in links[:10]:  # Показываем первые 10
            print(f"  {link}")
        
        # Ищем .crl файлы
        crl_files = re.findall(r'(https?://[^\s"\'<>]*\.crl)', response.text, re.IGNORECASE)
        print(f"Найдено {len(crl_files)} .crl файлов:")
        for crl in crl_files:
            print(f"  {crl}")
            
    except Exception as e:
        print(f"Ошибка: {e}")

if __name__ == "__main__":
    debug_cdp_parsing("http://pki.tax.gov.ru/cdp/")
    debug_cdp_parsing("http://cdp.tax.gov.ru/cdp/")