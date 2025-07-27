from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
import requests
import os
import re
import sys

def download_and_replace(tag, attr, base_url, assets_dir):
    url = tag.get(attr)
    if not url or url.startswith('data:') or url.startswith('mailto:') or url.startswith('javascript:'):
        return
    file_url = urljoin(base_url, url)
    filename = os.path.basename(urlparse(file_url).path)
    if not filename:
        filename = "index"
    # Add extension if missing (for manifest, etc.)
    if '.' not in filename and '?' in file_url:
        filename += file_url[file_url.rfind('.'):]
    local_path = f'{assets_dir}/{filename}'
    try:
        r = requests.get(file_url, stream=True)
        r.raise_for_status()
        with open(local_path, "wb") as f:
            for chunk in r.iter_content(1024):
                f.write(chunk)
        tag[attr] = local_path
    except Exception as e:
        print(f"Failed to download/Nie udalo sie pobrac {file_url}: {e}")

def download_srcset(tag, attr, base_url, assets_dir):
    srcset = tag.get(attr)
    if not srcset:
        return
    new_srcset = []
    for item in srcset.split(','):
        url = item.strip().split(' ')[0]
        if url:
            file_url = urljoin(base_url, url)
            filename = os.path.basename(urlparse(file_url).path)
            local_path = f'{assets_dir}/{filename}'
            try:
                r = requests.get(file_url, stream=True)
                r.raise_for_status()
                with open(local_path, "wb") as f:
                    for chunk in r.iter_content(1024):
                        f.write(chunk)
                new_srcset.append(item.replace(url, local_path))
            except Exception as e:
                print(f"Failed to download/Nie udalo sie pobrac {file_url}: {e}")
    tag[attr] = ', '.join(new_srcset)

url = input("Enter URL/Wpisz URL: ")
response = requests.get(url)
soup = BeautifulSoup(response.text, "html.parser")

# Get the directory where the .exe or script is located
base_dir = os.path.dirname(sys.argv[0])

# Parse domain from URL and create a folder for it
parsed_url = urlparse(url)
domain = parsed_url.netloc
if not domain:
    domain = "output"
output_dir = os.path.join(base_dir, domain)
os.makedirs(output_dir, exist_ok=True)

# Assets directory inside the domain folder
assets_dir = os.path.join(output_dir, 'assets')
os.makedirs(assets_dir, exist_ok=True)

# Download all <link> hrefs (CSS, icons, manifest, etc.)
for link in soup.find_all('link', href=True):
    download_and_replace(link, 'href', url, assets_dir)

# Download all <script> srcs (JS, Vue, etc.)
for script in soup.find_all('script', src=True):
    download_and_replace(script, 'src', url, assets_dir)

# Download all <img> srcs and srcsets
for img in soup.find_all('img'):
    if img.get('src'):
        download_and_replace(img, 'src', url, assets_dir)
    if img.get('srcset'):
        download_srcset(img, 'srcset', url, assets_dir)

# Download all <source> src and srcset (for <picture>, <video>, <audio>)
for source in soup.find_all('source'):
    if source.get('src'):
        download_and_replace(source, 'src', url, assets_dir)
    if source.get('srcset'):
        download_srcset(source, 'srcset', url, assets_dir)

# Download <video> and <audio> src
for tag in soup.find_all(['video', 'audio']):
    if tag.get('src'):
        download_and_replace(tag, 'src', url, assets_dir)

# Download <iframe>, <embed>, <object> src/data
for tag in soup.find_all(['iframe', 'embed']):
    if tag.get('src'):
        download_and_replace(tag, 'src', url, assets_dir)
for tag in soup.find_all('object'):
    if tag.get('data'):
        download_and_replace(tag, 'data', url, assets_dir)

# Download manifest and msapplication-config from <meta content=...>
for meta in soup.find_all('meta', content=True):
    content = meta['content']
    if content.endswith('.webmanifest') or content.endswith('.xml') or content.endswith('.json') or content.endswith('.ico') or content.endswith('.svg'):
        download_and_replace(meta, 'content', url, assets_dir)

# Determine output HTML filename based on URL
path = parsed_url.path
if path.endswith('.html'):
    html_filename = os.path.basename(path)
elif path == '' or path == '/':
    html_filename = 'index.html'
else:
    base = os.path.basename(path.rstrip('/'))
    html_filename = base + '.html' if not base.endswith('.html') else base

# Save the updated HTML page in the domain folder
html_path = os.path.join(output_dir, html_filename)
with open(html_path, 'w', encoding='utf-8') as f:
    f.write(soup.prettify())

print("--------------------------")
print("")
print(f"Page cloned as/Strona skopiowana jako {os.path.join(domain, html_filename)}.")
print("")
print("--------------------------")