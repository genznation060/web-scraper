from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
import csv
import io
import time
from urllib.parse import urljoin

app = Flask(__name__)
CORS(app)

class WebScraper:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
        })

    def scrape_page(self, url, custom_selector=None):
        """Scrape a single page"""
        try:
            response = self.session.get(url, timeout=25)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            data = []

            # ---------- Custom selector mode ----------
            if custom_selector and custom_selector.strip():
                elements = soup.select(custom_selector.strip())
                for el in elements:
                    item = {
                        'type': 'custom',
                        'text': el.get_text(strip=True)[:400],
                        'tag': el.name,
                    }
                    # Try to get useful attributes
                    if el.get('href'):
                        item['url'] = urljoin(url, el.get('href'))
                    if el.get('src'):
                        item['src'] = urljoin(url, el.get('src'))
                    if el.get('alt'):
                        item['alt'] = el.get('alt')[:150]
                    # Also grab first img inside if exists
                    img = el.find('img')
                    if img and img.get('src'):
                        item['image'] = urljoin(url, img.get('src'))
                    data.append(item)
                return data, soup

            # ---------- Default mode (original logic) ----------
            # Links
            for link in soup.find_all('a', href=True):
                text = link.get_text(strip=True)
                if text:
                    data.append({
                        'type': 'link',
                        'text': text[:150],
                        'url': urljoin(url, link['href'])
                    })

            # Headings
            for heading in soup.find_all(['h1', 'h2', 'h3', 'h4']):
                text = heading.get_text(strip=True)
                if text:
                    data.append({
                        'type': 'heading',
                        'tag': heading.name,
                        'text': text[:250]
                    })

            # Paragraphs
            for para in soup.find_all('p'):
                text = para.get_text(strip=True)
                if text and len(text) > 25:
                    data.append({
                        'type': 'paragraph',
                        'text': text[:400]
                    })

            # Images
            for img in soup.find_all('img', src=True):
                data.append({
                    'type': 'image',
                    'src': urljoin(url, img['src']),
                    'alt': (img.get('alt') or '')[:150]
                })

            return data, soup

        except Exception as e:
            raise Exception(f"Error scraping {url}: {str(e)}")

    def scrape_with_pagination(self, base_url, max_pages=3, pagination_type='url', custom_selector=None):
        all_data = []
        current_url = base_url
        page_count = 0

        while page_count < max_pages:
            try:
                page_data, soup = self.scrape_page(current_url, custom_selector)
                if page_data:
                    all_data.extend(page_data)

                page_count += 1

                # Only try to find next page for "url" type
                if pagination_type != 'url':
                    break

                next_url = None
                for link in soup.find_all('a', href=True):
                    text = link.get_text(strip=True).lower()
                    if text in ['next', 'next →', '→', '»', 'next page', 'older', 'load more']:
                        next_url = urljoin(current_url, link['href'])
                        break

                # Also try common patterns
                if not next_url:
                    next_link = soup.select_one('a[rel="next"], .next a, .pagination .next a, li.next a')
                    if next_link and next_link.get('href'):
                        next_url = urljoin(current_url, next_link['href'])

                if not next_url or next_url == current_url:
                    break

                current_url = next_url
                time.sleep(1.2)  # be polite

            except Exception as e:
                print(f"Error on page {page_count + 1}: {e}")
                break

        return all_data


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/scrape', methods=['POST'])
def scrape():
    try:
        data = request.get_json(force=True) or {}
        url = data.get('url', '').strip()
        max_pages = int(data.get('max_pages', 3))
        pagination_type = data.get('pagination_type', 'url')
        custom_selector = data.get('custom_selector', '').strip() or None

        if not url:
            return jsonify({'error': 'URL is required'}), 400

        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url

        scraper = WebScraper()
        scraped_data = scraper.scrape_with_pagination(
            url, max_pages, pagination_type, custom_selector
        )

        if not scraped_data:
            return jsonify({
                'error': 'No data found on this page. Try a different URL or Custom Selector (example: .product-item, article, .post)'
            }), 404

        # ---- Safe CSV creation (this fixes the 'tag' error) ----
        all_fields = set()
        for item in scraped_data:
            all_fields.update(item.keys())
        fieldnames = sorted(list(all_fields))

        csv_buffer = io.StringIO()
        writer = csv.DictWriter(
            csv_buffer,
            fieldnames=fieldnames,
            extrasaction='ignore',   # safety net
            restval=''               # empty cells for missing keys
        )
        writer.writeheader()
        writer.writerows(scraped_data)
        csv_data = csv_buffer.getvalue()

        # Preview (first 40 rows is enough)
        preview = scraped_data[:40]

        return jsonify({
            'success': True,
            'data_count': len(scraped_data),
            'columns': fieldnames,
            'preview': preview,
            'csv_data': csv_data,          # frontend will turn this into a download
            'message': f'Successfully scraped {len(scraped_data)} items'
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
