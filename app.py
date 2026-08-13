from flask import Flask, render_template, request, send_file, jsonify
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
import csv
import io
import os
import time
import re
from urllib.parse import urljoin, urlparse

app = Flask(__name__)
CORS(app)

# Create downloads folder
DOWNLOAD_FOLDER = 'downloads'
if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

class WebScraper:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
    
    def scrape_page(self, url):
        """Scrape a single page and extract data"""
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            data = []
            
            # Get all links with text
            for link in soup.find_all('a'):
                href = link.get('href')
                text = link.get_text(strip=True)
                if href and text:
                    data.append({
                        'type': 'link',
                        'text': text[:100],
                        'url': urljoin(url, href)
                    })
            
            # Get all headings
            for heading in soup.find_all(['h1', 'h2', 'h3']):
                text = heading.get_text(strip=True)
                if text:
                    data.append({
                        'type': 'heading',
                        'tag': heading.name,
                        'text': text[:200]
                    })
            
            # Get all paragraphs
            for para in soup.find_all('p'):
                text = para.get_text(strip=True)
                if text and len(text) > 20:
                    data.append({
                        'type': 'paragraph',
                        'text': text[:300]
                    })
            
            # Get all images
            for img in soup.find_all('img'):
                src = img.get('src')
                alt = img.get('alt', '')
                if src:
                    data.append({
                        'type': 'image',
                        'src': urljoin(url, src),
                        'alt': alt[:100]
                    })
            
            return data, soup
            
        except Exception as e:
            raise Exception(f"Error scraping {url}: {str(e)}")
    
    def scrape_with_pagination(self, base_url, max_pages=3, pagination_type='url'):
        """Scrape multiple pages"""
        all_data = []
        current_url = base_url
        page_count = 0
        
        while page_count < max_pages:
            try:
                page_data, soup = self.scrape_page(current_url)
                if page_data:
                    all_data.extend(page_data)
                
                page_count += 1
                
                # Find next URL
                next_url = None
                if pagination_type == 'url':
                    for link in soup.find_all('a'):
                        text = link.get_text(strip=True).lower()
                        if text in ['next', 'next →', '→', '»', 'next page']:
                            if link.get('href'):
                                next_url = urljoin(current_url, link.get('href'))
                                break
                
                if not next_url or next_url == current_url:
                    break
                
                current_url = next_url
                time.sleep(1)
                
            except Exception as e:
                print(f"Error on page {page_count}: {str(e)}")
                break
        
        return all_data

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/scrape', methods=['POST'])
def scrape():
    try:
        data = request.json
        url = data.get('url')
        max_pages = int(data.get('max_pages', 3))
        pagination_type = data.get('pagination_type', 'url')
        
        if not url:
            return jsonify({'error': 'URL is required'}), 400
        
        # Scrape data
        scraper = WebScraper()
        scraped_data = scraper.scrape_with_pagination(url, max_pages, pagination_type)
        
        if not scraped_data:
            return jsonify({'error': 'No data found on this page'}), 404
        
        # Create CSV
        csv_buffer = io.StringIO()
        if scraped_data:
            fieldnames = scraped_data[0].keys()
            writer = csv.DictWriter(csv_buffer, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(scraped_data)
        
        csv_data = csv_buffer.getvalue()
        
        # Create ZIP
        zip_buffer = io.BytesIO()
        import zipfile
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            zip_file.writestr('scraped_data.csv', csv_data)
            zip_file.writestr('summary.txt', f"""
Web Scraper Report
==================
URL: {url}
Items: {len(scraped_data)}
Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}
""")
        
        zip_buffer.seek(0)
        
        return send_file(
            zip_buffer,
            mimetype='application/zip',
            as_attachment=True,
            download_name=f'scraped_data_{int(time.time())}.zip'
        )
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
