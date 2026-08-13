import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
from urllib.parse import urljoin
import time
import re

st.set_page_config(page_title="Web Scraper", layout="wide")

st.title("🕷️ Web Scraper")
st.markdown("Scrape any website with pagination support")

# Inputs
col1, col2, col3 = st.columns([3, 1, 1])

with col1:
    url = st.text_input("Target URL", "https://example.com")

with col2:
    max_pages = st.number_input("Max Pages", min_value=1, max_value=20, value=5)

with col3:
    pagination_type = st.selectbox("Pagination", ["url", "load_more", "infinite"])

def scrape_page(session, url):
    try:
        response = session.get(url, timeout=30)
        soup = BeautifulSoup(response.content, 'html.parser')
        data = []
        
        for element in soup.find_all(['h1', 'h2', 'h3', 'p', 'a', 'img']):
            item = {'tag': element.name}
            text = element.get_text(strip=True)
            if text:
                item['text'] = text[:200]
            if element.name == 'a' and element.get('href'):
                item['href'] = urljoin(url, element.get('href'))
            if element.name == 'img' and element.get('src'):
                item['src'] = urljoin(url, element.get('src'))
            if item.get('text') or item.get('href'):
                data.append(item)
        return data, soup
    except Exception as e:
        st.error(f"Error: {str(e)}")
        return [], None

if st.button("🚀 Start Scraping"):
    if not url:
        st.warning("Please enter a URL")
    else:
        with st.spinner("Scraping in progress..."):
            session = requests.Session()
            session.headers.update({'User-Agent': 'Mozilla/5.0'})
            
            all_data = []
            current_url = url
            progress_bar = st.progress(0)
            
            for i in range(max_pages):
                progress_bar.progress((i + 1) / max_pages)
                page_data, soup = scrape_page(session, current_url)
                if page_data:
                    all_data.extend(page_data)
                
                # Find next URL
                next_url = None
                if pagination_type == 'url':
                    for link in soup.find_all('a'):
                        text = link.get_text(strip=True).lower()
                        if text in ['next', 'next →', '→', '»'] and link.get('href'):
                            next_url = urljoin(current_url, link.get('href'))
                            break
                elif pagination_type == 'load_more':
                    for btn in soup.find_all(['a', 'button']):
                        text = btn.get_text(strip=True).lower()
                        if ('load' in text or 'more' in text) and btn.get('href'):
                            next_url = urljoin(current_url, btn.get('href'))
                            break
                
                if not next_url or next_url == current_url:
                    break
                current_url = next_url
                time.sleep(0.5)
            
            if all_data:
                df = pd.DataFrame(all_data)
                st.success(f"✅ Scraped {len(all_data)} items!")
                
                # Stats
                col1, col2, col3 = st.columns(3)
                col1.metric("Total Items", len(all_data))
                col2.metric("Columns", len(df.columns))
                col3.metric("Preview", min(10, len(all_data)))
                
                # Show data
                st.subheader("📊 Data Preview")
                st.dataframe(df.head(10))
                
                # Download
                csv = df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📥 Download CSV",
                    data=csv,
                    file_name="scraped_data.csv",
                    mime="text/csv"
                )
            else:
                st.warning("No data found")

st.markdown("---")
st.caption("Built with Streamlit | Web Scraper Pro")