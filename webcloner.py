from urllib.parse import urljoin, urlparse, quote
from bs4 import BeautifulSoup
import requests
import os
import re
import sys
import hashlib
import time
from collections import deque
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk
import io
import urllib.request
import threading
import shutil

def safe_filename(url):
    parsed = urlparse(url)
    base = os.path.basename(parsed.path)
    if not base:
        base = "index"
    ext = os.path.splitext(base)[1]
    unique = base
    if parsed.query:
        h = hashlib.md5(parsed.query.encode()).hexdigest()[:8]
        unique = f"{os.path.splitext(base)[0]}_{h}{ext}"
    if len(unique) > 100 or re.search(r'[^A-Za-z0-9._-]', unique):
        unique = hashlib.md5(url.encode()).hexdigest() + ext
    return unique

def download_with_retries(file_url, local_path, max_retries=3, timeout=10):
    for attempt in range(max_retries):
        try:
            r = requests.get(file_url, stream=True, timeout=timeout)
            r.raise_for_status()
            with open(local_path, "wb") as f:
                for chunk in r.iter_content(1024):
                    f.write(chunk)
            return True
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(1)
            else:
                print(f"Failed to download/Nie udalo sie pobrac {file_url}: {e}")
    return False

def download_and_replace(tag, attr, base_url, assets_dir, log_callback=None):
    url = tag.get(attr)
    if not url or url.startswith('data:') or url.startswith('mailto:') or url.startswith('javascript:'):
        return
    file_url = urljoin(base_url, url)
    filename = safe_filename(file_url)
    local_path = os.path.join(assets_dir, filename)
    rel_path = os.path.join('assets', filename)
    if not os.path.isfile(local_path):
        msg = f"Downloading: {file_url} -> {rel_path.replace(os.sep, '/')}"

        if log_callback:
            log_callback(msg)
        else:
            print(msg)
        download_with_retries(file_url, local_path)
    tag[attr] = rel_path.replace("\\", "/")

def download_srcset(tag, attr, base_url, assets_dir, log_callback=None):
    srcset = tag.get(attr)
    if not srcset:
        return
    new_srcset = []
    for item in srcset.split(','):
        url = item.strip().split(' ')[0]
        if url:
            file_url = urljoin(base_url, url)
            filename = safe_filename(file_url)
            local_path = os.path.join(assets_dir, filename)
            rel_path = os.path.join('assets', filename)
            if not os.path.isfile(local_path):
                msg = f"Downloading (srcset): {file_url} -> {rel_path.replace(os.sep, '/')}"

                if log_callback:
                    log_callback(msg)
                else:
                    print(msg)
                download_with_retries(file_url, local_path)
            new_srcset.append(item.replace(url, rel_path.replace("\\", "/")))
    tag[attr] = ', '.join(new_srcset)

def is_internal_link(href, domain):
    if not href:
        return False
    parsed = urlparse(href)
    return (not parsed.netloc or parsed.netloc == domain) and not href.startswith('mailto:') and not href.startswith('javascript:')

def normalize_url(href, base_url):
    return urljoin(base_url, href.split('#')[0])

def get_html_filename_from_url(url):
    parsed = urlparse(url)
    path = parsed.path
    if path.endswith('.html'):
        return os.path.basename(path)
    elif path == '' or path == '/':
        return 'index.html'
    else:
        # Remove leading/trailing slashes and replace / with _
        clean = path.strip('/').replace('/', '_')
        if not clean:
            clean = 'index'
        if not clean.endswith('.html'):
            clean += '.html'
        return clean

def update_internal_links(soup, domain, current_url):
    # Zamień href/src do podstron na odpowiednie .html
    for a in soup.find_all('a', href=True):
        href = a['href']
        if is_internal_link(href, domain):
            abs_url = normalize_url(href, current_url)
            a['href'] = get_html_filename_from_url(abs_url)
    # Zamień <form action=...> jeśli jest wewnętrzny
    for form in soup.find_all('form', action=True):
        action = form['action']
        if is_internal_link(action, domain):
            abs_url = normalize_url(action, current_url)
            form['action'] = get_html_filename_from_url(abs_url)
    # Zamień <iframe src=...> jeśli jest wewnętrzny
    for iframe in soup.find_all('iframe', src=True):
        src = iframe['src']
        if is_internal_link(src, domain):
            abs_url = normalize_url(src, current_url)
            iframe['src'] = get_html_filename_from_url(abs_url)
    # Zamień <script src=...> jeśli jest wewnętrzny i nie jest assetem
    for script in soup.find_all('script', src=True):
        src = script['src']
        if is_internal_link(src, domain) and not src.startswith('assets/'):
            abs_url = normalize_url(src, current_url)
            script['src'] = get_html_filename_from_url(abs_url)
    # Zamień <link href=...> jeśli jest wewnętrzny i nie jest assetem
    for link in soup.find_all('link', href=True):
        href = link['href']
        if is_internal_link(href, domain) and not href.startswith('assets/'):
            abs_url = normalize_url(href, current_url)
            link['href'] = get_html_filename_from_url(abs_url)

def open_folder(path):
    if sys.platform == "win32":
        os.startfile(path)
    elif sys.platform == "darwin":
        os.system(f'open "{path}"')
    else:
        os.system(f'xdg-open "{path}"')

def clone_website(url, log_callback=None, clone_all=True, cancel_flag=None):
    start_time = time.time()
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
    except Exception as e:
        if log_callback:
            log_callback(f"Failed to fetch page/Nie udalo sie pobrac strony: {e}")
        return None
    base_dir = os.path.dirname(sys.argv[0])
    parsed_url = urlparse(url)
    domain = parsed_url.netloc
    if not domain:
        domain = "output"
    output_dir = os.path.join(base_dir, domain)
    os.makedirs(output_dir, exist_ok=True)
    assets_dir = os.path.join(output_dir, 'assets')
    os.makedirs(assets_dir, exist_ok=True)
    visited = set()
    queue = deque([url])
    while queue:
        if cancel_flag and cancel_flag['cancel']:
            if log_callback:
                log_callback("Cloning cancelled by user. Cleaning up...")
            try:
                shutil.rmtree(output_dir)
            except Exception as e:
                if log_callback:
                    log_callback(f"Failed to remove directory: {output_dir} ({e})")
            return None
        current_url = queue.popleft()
        if current_url in visited:
            continue
        visited.add(current_url)
        try:
            resp = requests.get(current_url, timeout=15)
            resp.raise_for_status()
        except Exception as e:
            if log_callback:
                log_callback(f"Failed to fetch page/Nie udalo sie pobrac strony: {current_url} {e}")
            continue
        soup = BeautifulSoup(resp.text, "html.parser")
        for link in soup.find_all('link', href=True):
            download_and_replace(link, 'href', current_url, assets_dir, log_callback)
        for script in soup.find_all('script', src=True):
            download_and_replace(script, 'src', current_url, assets_dir, log_callback)
        for img in soup.find_all('img'):
            if img.get('src'):
                download_and_replace(img, 'src', current_url, assets_dir, log_callback)
            if img.get('srcset'):
                download_srcset(img, 'srcset', current_url, assets_dir, log_callback)
        for source in soup.find_all('source'):
            if source.get('src'):
                download_and_replace(source, 'src', current_url, assets_dir, log_callback)
            if source.get('srcset'):
                download_srcset(source, 'srcset', current_url, assets_dir, log_callback)
        for tag in soup.find_all(['video', 'audio']):
            if tag.get('src'):
                download_and_replace(tag, 'src', current_url, assets_dir, log_callback)
        for tag in soup.find_all(['iframe', 'embed']):
            if tag.get('src'):
                download_and_replace(tag, 'src', current_url, assets_dir, log_callback)
        for tag in soup.find_all('object'):
            if tag.get('data'):
                download_and_replace(tag, 'data', current_url, assets_dir, log_callback)
        for meta in soup.find_all('meta', content=True):
            content = meta['content']
            if content.endswith('.webmanifest') or content.endswith('.xml') or content.endswith('.json') or content.endswith('.ico') or content.endswith('.svg'):
                download_and_replace(meta, 'content', current_url, assets_dir, log_callback)
        if clone_all:
            for a in soup.find_all('a', href=True):
                href = a['href']
                if is_internal_link(href, domain):
                    next_url = normalize_url(href, current_url)
                    if next_url not in visited:
                        queue.append(next_url)
        update_internal_links(soup, domain, current_url)
        html_filename = get_html_filename_from_url(current_url)
        html_path = os.path.join(output_dir, html_filename)
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(soup.prettify())
        if log_callback:
            log_callback(f"Saved HTML: {os.path.join(domain, html_filename)}")
        if not clone_all:
            break
    elapsed = time.time() - start_time
    if log_callback and not (cancel_flag and cancel_flag['cancel']):
        log_callback("--------------------------")
        log_callback("")
        log_callback(f"Cloning finished. Time taken: {elapsed:.2f} seconds / Czas wykonania: {elapsed:.2f} sekund.")
        log_callback("")
        log_callback("--------------------------")
    return output_dir

def run_gui():
    root = tk.Tk()
    root.title("Web Cloner by mavlex")
    root.geometry("500x470")
    root.resizable(False, False)
    style = ttk.Style()
    style.theme_use('clam')
    style.configure('TButton', font=('Segoe UI', 11), padding=6, background="#4F8EF7", foreground="#fff")
    style.configure('TLabel', font=('Segoe UI', 11))
    style.configure('TEntry', font=('Segoe UI', 11))

    # Minimalistic header with optional imgur image
    header_frame = tk.Frame(root, bg="#f7f7f7", height=80)
    header_frame.pack(fill='x')
    imgur_url = "https://imgur.com/koJojfl.png"  # Change to your imgur image
    try:
        with urllib.request.urlopen(imgur_url) as u:
            raw_data = u.read()
        im = Image.open(io.BytesIO(raw_data))
        im = im.resize((48, 48))
        photo = ImageTk.PhotoImage(im)
        img_label = tk.Label(header_frame, image=photo, bg="#f7f7f7")
        img_label.image = photo
        img_label.pack(side='left', padx=(18, 10), pady=16)
    except Exception:
        img_label = tk.Label(header_frame, text="🌐", bg="#f7f7f7", font=("Segoe UI Emoji", 24))
        img_label.pack(side='left', padx=(18, 10), pady=16)
    title_label = tk.Label(header_frame, text="Web Cloner", bg="#f7f7f7", fg="#222", font=("Segoe UI", 18, "bold"))
    title_label.pack(side='left', pady=18)
    subtitle_label = tk.Label(header_frame, text="by mavlex", bg="#f7f7f7", fg="#4F8EF7", font=("Segoe UI", 10))
    subtitle_label.pack(side='left', padx=(8,0), pady=18)

    main_frame = tk.Frame(root, bg="#ffffff")
    main_frame.pack(fill='both', expand=True)

    cancel_flag = {'cancel': False}
    clone_thread = [None]
    output_dir = [None]
    clone_all_var = tk.BooleanVar(value=True)
    url_var = tk.StringVar()

    url_label = tk.Label(main_frame, text="Enter URL", bg="#ffffff", fg="#222", font=("Segoe UI", 11, "bold"))
    url_label.pack(anchor='w', pady=(18, 5), padx=(24,0))
    url_entry = ttk.Entry(main_frame, textvariable=url_var, width=54)
    url_entry.pack(fill='x', padx=24, pady=(0, 12))

    # Placeholder for URL entry (grayed out)
    placeholder = "e.g. https://youtube.com"
    def on_entry_focus_in(event):
        if url_entry.get() == placeholder:
            url_entry.delete(0, tk.END)
            url_entry.config(foreground="#222")
    def on_entry_focus_out(event):
        if not url_entry.get():
            url_entry.insert(0, placeholder)
            url_entry.config(foreground="#888")
    url_entry.insert(0, placeholder)
    url_entry.config(foreground="#888")
    url_entry.bind("<FocusIn>", on_entry_focus_in)
    url_entry.bind("<FocusOut>", on_entry_focus_out)

    # Option to clone only main file or whole website
    clone_all_frame = tk.Frame(main_frame, bg="#ffffff")
    clone_all_frame.pack(anchor='w', padx=24, pady=(0, 10))
    clone_all_checkbox = ttk.Checkbutton(
        clone_all_frame,
        text="Clone whole website (all internal pages)",
        variable=clone_all_var
    )
    clone_all_checkbox.pack(side='left')

    button_frame = tk.Frame(main_frame, bg="#ffffff")
    button_frame.pack(fill='x', padx=24, pady=(0, 10))
    clone_button = ttk.Button(button_frame, text="Clone")
    clone_button.pack(side='left', padx=(0, 10))
    go_to_button = ttk.Button(button_frame, text="Go to", state='disabled')
    go_to_button.pack(side='left')
    cancel_button = ttk.Button(button_frame, text="Cancel", state='disabled')
    cancel_button.pack(side='left', padx=(10, 0))

    log_text = tk.Text(main_frame, height=9, width=60, state='disabled', font=('Consolas', 9), bg="#f7f7f7", fg="#222", relief='flat', highlightthickness=0)
    log_text.pack(fill='both', expand=True, padx=24, pady=(0, 8))

    footer = tk.Label(root, text="Made by mavlex | 2024", bg="#f7f7f7", fg="#4F8EF7", font=("Segoe UI", 9))
    footer.pack(side='bottom', fill='x', pady=(0, 2))

    def log_callback(msg):
        log_text.config(state='normal')
        log_text.insert('end', msg + '\n')
        log_text.see('end')
        log_text.config(state='disabled')
        root.update_idletasks()

    def show_disclaimer():
        disclaimer = (
            "This tool is provided for educational and archival purposes only. "
            "The developer does not condone or support the unauthorized cloning, redistribution, or commercial use of "
            "copyrighted or protected websites. Users are fully responsible for ensuring their use "
            "complies with local laws and the terms of service of the websites they access. Use at your own risk."
        )
        win = tk.Toplevel(root)
        win.title("Disclaimer")
        win.geometry("420x220")
        win.resizable(False, False)
        win.grab_set()
        label = tk.Label(win, text=disclaimer, wraplength=400, justify="left", font=("Segoe UI", 10), padx=16, pady=16)
        label.pack(fill='both', expand=True)
        btn_frame = tk.Frame(win)
        btn_frame.pack(pady=(0, 16))
        accepted = {'value': False}
        def accept():
            accepted['value'] = True
            win.destroy()
        def reject():
            accepted['value'] = False
            win.destroy()
            root.destroy()  # Close the main app as well
            sys.exit(0)
        accept_btn = ttk.Button(btn_frame, text="Accept", command=accept)
        accept_btn.pack(side='left', padx=10)
        reject_btn = ttk.Button(btn_frame, text="Reject", command=reject)
        reject_btn.pack(side='left', padx=10)
        win.wait_window()
        return accepted['value']

    def do_clone(url, clone_all):
        out_dir = clone_website(url, log_callback, clone_all=clone_all, cancel_flag=cancel_flag)
        root.config(cursor="")
        if cancel_flag['cancel']:
            log_callback("Cloning cancelled and files removed.")
            cancel_button.config(state='disabled')
            return
        if out_dir:
            output_dir[0] = out_dir
            go_to_button.config(state='normal')
            cancel_button.config(state='disabled')
            messagebox.showinfo("Done", "Cloning finished!\n\nClick 'Go to' to open the folder.")
        else:
            go_to_button.config(state='disabled')
            cancel_button.config(state='disabled')

    def start_clone():
        log_text.config(state='normal')
        log_text.delete('1.0', 'end')
        log_text.config(state='disabled')
        go_to_button.config(state='disabled')
        cancel_button.config(state='normal')
        cancel_flag['cancel'] = False
        url = url_var.get().strip()
        if not url:
            messagebox.showerror("Error", "Please enter a URL.")
            cancel_button.config(state='disabled')
            return
        if not show_disclaimer():
            log_callback("Cloning cancelled. You must accept the disclaimer to proceed.")
            cancel_button.config(state='disabled')
            return
        log_callback("Web Cloner v2.0 | Skrypt do klonowania stron HTML - Made by mavlex")
        log_callback("Cloning HTML page/Skopiuj strone HTML")
        log_callback("")
        root.config(cursor="watch")
        root.update()
        clone_thread[0] = threading.Thread(target=do_clone, args=(url, clone_all_var.get()))
        clone_thread[0].start()

    def cancel_clone():
        cancel_flag['cancel'] = True
        cancel_button.config(state='disabled')
        log_callback("Cancelling...")

    def go_to_folder():
        if output_dir[0]:
            open_folder(output_dir[0])

    clone_button.config(command=start_clone)
    go_to_button.config(command=go_to_folder)
    cancel_button.config(command=cancel_clone)
    url_entry.bind('<Return>', lambda e: start_clone())

    root.mainloop()

if __name__ == "__main__":
    run_gui()