import os
import logging
import requests
import re
from flask import Flask
from bs4 import BeautifulSoup
from datetime import datetime
import threading
import time

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Конфигурация
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')

# Глобальные переменные
found_items = {}
monitoring_active = False

def debug_parse_funpay():
    """Простой дебаг-парсинг для анализа структуры"""
    try:
        url = "https://funpay.com/chips/186/"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        logger.info("🔍 Дебаг-парсинг FunPay...")
        response = requests.get(url, headers=headers, timeout=15)
        
        if response.status_code != 200:
            logger.error(f"❌ HTTP ошибка: {response.status_code}")
            return []
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Анализируем структуру
        logger.info("📊 Анализ структуры страницы:")
        
        # 1. Считаем все div
        all_divs = soup.find_all('div')
        logger.info(f"   Всего div элементов: {len(all_divs)}")
        
        # 2. Ищем по классам
        for class_name in ['tc-item', 'item', 'product', 'offer', 'listing', 'card']:
            elements = soup.find_all(class_=class_name)
            if elements:
                logger.info(f"   Элементы с классом '{class_name}': {len(elements)}")
                if elements:
                    # Покажем HTML первого элемента
                    first_elem = elements[0]
                    logger.info(f"   Пример HTML ({class_name}): {str(first_elem)[:200]}...")
        
        # 3. Ищем текст Black Russia
        all_text = soup.get_text().lower()
        if 'black russia' in all_text or 'блек раша' in all_text:
            logger.info("   ✅ На странице есть упоминания Black Russia")
        else:
            logger.info("   ❌ На странице НЕТ упоминаний Black Russia")
        
        # 4. Ищем цены
        price_elements = soup.find_all(text=re.compile(r'\d+\s*руб|\d+\s*₽'))
        if price_elements:
            logger.info(f"   Найдено элементов с ценами: {len(price_elements)}")
            for i, price in enumerate(price_elements[:3]):
                logger.info(f"   Цена {i+1}: {price.strip()}")
        
        return []
        
    except Exception as e:
        logger.error(f"💥 Ошибка дебаг-парсинга: {e}")
        return []

def simple_parse_black_russia():
    """Самый простой парсинг - ищем ВСЕ товары"""
    try:
        url = "https://funpay.com/chips/186/"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        }
        
        logger.info("🔄 Простой парсинг FunPay...")
        response = requests.get(url, headers=headers, timeout=15)
        
        if response.status_code != 200:
            logger.error(f"❌ HTTP {response.status_code}")
            return []
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        items = []
        
        # Метод 1: Ищем по структуре FunPay
        # На FunPay товары обычно в div с определенными классами
        product_divs = []
        
        # Попробуем разные варианты
        for selector in ['div[class*="item"]', 'div[class*="product"]', 'div[class*="offer"]', 
                        'a[class*="item"]', 'a[class*="product"]', 'div.tc-item']:
            found = soup.select(selector)
            if found:
                product_divs.extend(found[:10])  # Берем первые 10
        
        logger.info(f"📦 Найдено потенциальных товаров: {len(product_divs)}")
        
        # Если не нашли, берем все div с текстом
        if not product_divs:
            all_divs = soup.find_all('div')
            for div in all_divs[:50]:  # Первые 50 div
                text = div.get_text(strip=True)
                if text and len(text) > 20 and any(word in text.lower() for word in ['руб', '₽', 'цена']):
                    product_divs.append(div)
        
        for div in product_divs[:20]:  # Анализируем первые 20
            try:
                # Получаем весь текст блока
                block_text = div.get_text(strip=True)
                if not block_text or len(block_text) < 10:
                    continue
                
                # Ищем Black Russia
                if not any(keyword in block_text.lower() for keyword in 
                          ['black russia', 'blackrussia', 'блек раша', 'блэк раша']):
                    continue
                
                # Ищем цену
                price_match = re.search(r'(\d+)\s*(руб|₽|р\.)', block_text)
                if not price_match:
                    # Пробуем найти просто цифры
                    digits = re.findall(r'\d{2,}', block_text)
                    if not digits:
                        continue
                    price = int(digits[0])
                else:
                    price = int(price_match.group(1))
                
                # Фильтр цены
                if price < 10 or price > 50000:
                    continue
                
                # Ищем ссылку
                link = url
                link_elem = div.find('a')
                if link_elem and link_elem.get('href'):
                    href = link_elem['href']
                    if href.startswith('/'):
                        link = f"https://funpay.com{href}"
                    elif href.startswith('http'):
                        link = href
                
                # Создаем ID
                item_id = f"{hash(block_text)}_{price}"
                
                # Берем первые 100 символов как заголовок
                title = block_text[:100]
                
                items.append({
                    'id': item_id,
                    'title': title,
                    'price': price,
                    'link': link,
                    'full_text': block_text[:200]
                })
                
                logger.info(f"   ✅ Найден товар: '{title[:50]}...' - {price} руб.")
                
            except Exception as e:
                continue
        
        logger.info(f"🎯 Итого найдено товаров: {len(items)}")
        return items
        
    except Exception as e:
        logger.error(f"💥 Ошибка парсинга: {e}")
        return []

# Маршруты Flask
@app.route('/')
def index():
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>FunPay Hunter - Debug Version</title>
        <style>
            body { font-family: Arial; margin: 40px; }
            .btn { display: inline-block; padding: 10px 20px; margin: 5px; background: #007bff; color: white; text-decoration: none; border-radius: 5px; }
            .btn-green { background: #28a745; }
            .btn-orange { background: #fd7e14; }
        </style>
    </head>
    <body>
        <h1>🔧 FunPay Hunter - Debug Version</h1>
        <p><strong>Статус:</strong> ✅ Сервер работает</p>
        <p><strong>Время:</strong> ''' + datetime.now().strftime("%H:%M:%S") + '''</p>
        
        <h3>Тестирование:</h3>
        <a href="/debug" class="btn btn-orange">🛠️ Дебаг-анализ</a>
        <a href="/parse" class="btn">🔍 Простой парсинг</a>
        <a href="/raw" class="btn">📄 Посмотреть HTML</a>
        
        <h3>Инструкция:</h3>
        <ol>
            <li>Нажмите "Дебаг-анализ" для анализа структуры FunPay</li>
            <li>Нажмите "Простой парсинг" для поиска товаров</li>
            <li>Пришлите мне логи с Render</li>
        </ol>
    </body>
    </html>
    '''

@app.route('/debug')
def debug_page():
    """Страница дебаг-анализа"""
    debug_parse_funpay()
    return '''
    <!DOCTYPE html>
    <html>
    <body style="font-family: Arial; margin: 20px;">
        <a href="/">← Назад</a>
        <h2>✅ Дебаг-анализ выполнен</h2>
        <p>Проверьте логи в Render Dashboard (вкладка Logs).</p>
        <p>Там будет информация о структуре страницы FunPay.</p>
        <p><strong>Пришлите мне эти логи!</strong></p>
    </body>
    </html>
    '''

@app.route('/parse')
def parse_page():
    """Страница простого парсинга"""
    items = simple_parse_black_russia()
    
    if items:
        result = f"<h2>✅ Найдено {len(items)} товаров:</h2>"
        for item in items:
            result += f'''
            <div style="border:1px solid #ddd; padding:15px; margin:10px;">
                <h4>{item['title']}</h4>
                <p><strong>Цена:</strong> {item['price']} руб.</p>
                <p><strong>Текст:</strong> {item['full_text']}</p>
                <p><a href="{item['link']}" target="_blank">Ссылка</a></p>
            </div>
            '''
    else:
        result = '''
        <div style="background:#f8d7da; padding:20px; border-radius:5px;">
            <h2>❌ Товары не найдены</h2>
            <p>Парсер не смог найти товары Black Russia.</p>
            <p>Возможные причины:</p>
            <ul>
                <li>Изменена структура FunPay</li>
                <li>На странице нет товаров в данный момент</li>
                <li>FunPay блокирует запросы с Render</li>
            </ul>
            <p>Нажмите <a href="/raw">"Посмотреть HTML"</a> чтобы увидеть сырую страницу.</p>
        </div>
        '''
    
    return f'''
    <!DOCTYPE html>
    <html>
    <head><title>Парсинг</title></head>
    <body style="font-family:Arial; margin:20px;">
        <a href="/">← Назад</a>
        {result}
    </body>
    </html>
    '''

@app.route('/raw')
def raw_page():
    """Показать сырой HTML страницы"""
    try:
        url = "https://funpay.com/chips/186/"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        
        # Показываем только первые 5000 символов
        html_preview = response.text[:5000]
        
        return f'''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Raw HTML</title>
            <style>
                body {{ font-family: Arial; margin: 20px; }}
                pre {{ background: #f5f5f5; padding: 20px; overflow: auto; max-height: 500px; }}
            </style>
        </head>
        <body>
            <a href="/">← Назад</a>
            <h2>📄 Сырой HTML (первые 5000 символов):</h2>
            <pre>{html_preview}</pre>
            <p><strong>Полный размер:</strong> {len(response.text)} символов</p>
            <p><strong>Статус:</strong> {response.status_code}</p>
        </body>
        </html>
        '''
    except Exception as e:
        return f"<h2>❌ Ошибка: {e}</h2><a href='/'>Назад</a>"

@app.route('/health')
def health():
    return "OK"

# Запуск приложения
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
