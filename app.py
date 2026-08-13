from flask import Flask, render_template, request, send_file, jsonify
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
import pandas as pd
import zipfile
import io
import os
import time
import json
from urllib.parse import urljoin, urlparse
import re

app = Flask(__name__)
CORS(app)

# Create downloads folder if not exists
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
            
            # Extract data - YOU CAN CUSTOMIZE THIS BASED ON YOUR NEEDS
            data = []
            
            # Example: Extract all links, text, and metadata
            for element in soup.find_all(['h1', 'h2', 'h3', 'p', 'a', 'img', 'div']):
                item = {}
                
                # Get element tag
                item['tag'] = element.name
                
                # Get text content
                item['text'] = element.get_text(strip=True)
                
                # Get attributes
                for attr in ['id', 'class', 'href', 'src', 'alt', 'title']:
                    if element.get(attr):
                        if attr in ['class']:
                            item[attr] = ' '.join(element.get(attr))
                        else:
                            item[attr] = element.get(attr)
                
                # Get link if it's an anchor
                if element.name == 'a' and element.get('href'):
                    item['url'] = urljoin(url, element.get('href'))
                
                # Get image source
                if element.name == 'img' and element.get('src'):
                    item['image_url'] = urljoin(url, element.get('src'))
                
                # Only add if there's at least one piece of data
                if item.get('text') or item.get('href') or item.get('src'):
                    data.append(item)
            
            return data, soup
            
        except Exception as e:
            raise Exception(f"Error scraping {url}: {str(e)}")
    
    def extract_load_more_url(self, soup, url):
        """Try to find 'Load More' or 'Next Page' button/link"""
        patterns = [
            # Common Load More patterns
            ('a', {'class': re.compile(r'load.*more|view.*more|show.*more', re.I)}),
            ('button', {'class': re.compile(r'load.*more|view.*more|show.*more', re.I)}),
            ('a', {'class': re.compile(r'next|pagination|page', re.I)}),
            ('a', {'rel': 'next'}),
            ('button', {'data-action': 'load-more'}),
            ('div', {'class': re.compile(r'load.*more|view.*more', re.I)}),
        ]
        
        for tag, attrs in patterns:
            elements = soup.find_all(tag, attrs=attrs)
            for el in elements:
                # Check for onclick or data-* attributes with URL
                if el.get('onclick'):
                    match = re.search(r"['\"]([^'\"]+\.(php|html|aspx|jsp|do))['\"]", el['onclick'])
                    if match:
                        return urljoin(url, match.group(1))
                
                # Check for data-url or data-href
                for attr in ['data-url', 'data-href', 'data-page', 'data-link']:
                    if el.get(attr):
                        return urljoin(url, el.get(attr))
                
                # Check if it's a link
                if el.name == 'a' and el.get('href'):
                    return urljoin(url, el.get('href'))
                
                # Check if it's a form with action
                if el.name == 'form' and el.get('action'):
                    return urljoin(url, el.get('action'))
        
        return None
    
    def scrape_with_pagination(self, base_url, max_pages=10, pagination_type='url', selector=None):
        """Scrape multiple pages with different pagination types"""
        all_data = []
        current_url = base_url
        page_count = 0
        
        while page_count < max_pages:
            try:
                # Scrape current page
                page_data, soup = self.scrape_page(current_url)
                if page_data:
                    all_data.extend(page_data)
                
                page_count += 1
                
                # Find next URL based on pagination type
                next_url = None
                
                if pagination_type == 'url':
                    # Look for standard pagination links
                    for link in soup.find_all('a'):
                        if link.get('href'):
                            text = link.get_text(strip=True).lower()
                            if text in ['next', 'next →', '→', '»', 'next page', 'load more']:
                                next_url = urljoin(current_url, link.get('href'))
                                break
                
                elif pagination_type == 'load_more':
                    # Look for load more button
                    next_url = self.extract_load_more_url(soup, current_url)
                    if not next_url:
                        # Try JavaScript onclick
                        for btn in soup.find_all(['button', 'a']):
                            onclick = btn.get('onclick', '')
                            if 'load' in onclick.lower() or 'more' in onclick.lower():
                                match = re.search(r"['\"]([^'\"]+)['\"]", onclick)
                                if match:
                                    next_url = urljoin(current_url, match.group(1))
                                    break
                
                elif pagination_type == 'infinite':
                    # For infinite scroll, try to find next page URL in data attributes
                    next_data = soup.find('div', {'data-next-page': True})
                    if next_data and next_data.get('data-next-page'):
                        next_url = urljoin(current_url, next_data.get('data-next-page'))
                    else:
                        # Check for JSON-LD or data attributes
                        script = soup.find('script', {'type': 'application/json'})
                        if script:
                            try:
                                data = json.loads(script.string)
                                if 'next' in data:
                                    next_url = urljoin(current_url, data['next'])
                            except:
                                pass
                
                # If no more pages, break
                if not next_url or next_url == current_url:
                    break
                
                current_url = next_url
                time.sleep(1)  # Be polite to the server
                
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
        max_pages = int(data.get('max_pages', 10))
        pagination_type = data.get('pagination_type', 'url')
        custom_selector = data.get('custom_selector', '')
        
        if not url:
            return jsonify({'error': 'URL is required'}), 400
        
        # Create scraper instance
        scraper = WebScraper()
        
        # Scrape data
        scraped_data = scraper.scrape_with_pagination(
            url, 
            max_pages, 
            pagination_type,
            custom_selector
        )
        
        if not scraped_data:
            return jsonify({'error': 'No data found'}), 404
        
        # Convert to DataFrame
        df = pd.DataFrame(scraped_data)
        
        # Create CSV in memory
        csv_buffer = io.StringIO()
        df.to_csv(csv_buffer, index=False)
        csv_data = csv_buffer.getvalue()
        
        # Create ZIP file in memory
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            # Add main CSV
            zip_file.writestr('scraped_data.csv', csv_data)
            
            # Add summary file
            summary = f"""
            Web Scraper Summary Report
            ============================
            Source URL: {url}
            Pagination Type: {pagination_type}
            Pages Scraped: {len(scraped_data) // 10 + 1 if scraped_data else 0}
            Total Items: {len(scraped_data)}
            Columns: {', '.join(df.columns)}
            Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}
            """
            zip_file.writestr('summary.txt', summary)
        
        zip_buffer.seek(0)
        
        # Save to file (optional, for download)
        timestamp = int(time.time())
        zip_filename = f'scraped_data_{timestamp}.zip'
        zip_path = os.path.join(DOWNLOAD_FOLDER, zip_filename)
        
        with open(zip_path, 'wb') as f:
            f.write(zip_buffer.getvalue())
        
        return jsonify({
            'success': True,
            'data_count': len(scraped_data),
            'columns': list(df.columns),
            'preview': df.head(10).to_dict('records'),
            'download_url': f'/download/{zip_filename}'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/download/<filename>')
def download(filename):
    try:
        return send_file(
            os.path.join(DOWNLOAD_FOLDER, filename),
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 404

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)