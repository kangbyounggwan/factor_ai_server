"""
Brave Image Search API Test
3D 프린터 문제 진단 시 관련 이미지 검색 테스트
"""
import requests
import os
import sys
from dotenv import load_dotenv

# UTF-8 출력 설정
sys.stdout.reconfigure(encoding='utf-8')

load_dotenv()

BRAVE_API_KEY = os.getenv('BRAVE_API_KEY')
BRAVE_SEARCH_API_BASE = os.getenv('BRAVE_SEARCH_API_BASE')

print(f'API Key: {BRAVE_API_KEY[:10]}...' if BRAVE_API_KEY else 'API Key not found!')
print(f'API Base: {BRAVE_SEARCH_API_BASE}')

# 3D 프린터 문제 관련 이미지 검색 테스트
query = '3D printer stringing problem solution'

headers = {
    'Accept': 'application/json',
    'Accept-Encoding': 'gzip',
    'X-Subscription-Token': BRAVE_API_KEY
}

# 이미지 검색 엔드포인트
url = f'{BRAVE_SEARCH_API_BASE}/images/search'
params = {
    'q': query,
    'count': 10,
    'safesearch': 'off'
}

print(f'\n[SEARCH] Searching for: {query}')
print(f'[URL] {url}')

try:
    response = requests.get(url, headers=headers, params=params, timeout=10)
    print(f'[STATUS] {response.status_code}')

    if response.status_code == 200:
        data = response.json()
        results = data.get('results', [])
        print(f'\n[OK] Found {len(results)} images:\n')

        for i, img in enumerate(results[:10], 1):
            title = img.get('title', 'No title')[:60]
            thumb_url = img.get('thumbnail', {}).get('src', 'N/A')
            source_url = img.get('url', 'N/A')
            print(f'{i}. {title}')
            print(f'   [Thumbnail] {thumb_url[:80]}...' if len(thumb_url) > 80 else f'   [Thumbnail] {thumb_url}')
            print(f'   [Source] {source_url[:80]}...' if len(source_url) > 80 else f'   [Source] {source_url}')
            print()
    else:
        print(f'[ERROR] {response.text}')

except requests.exceptions.RequestException as e:
    print(f'[ERROR] Request failed: {e}')
