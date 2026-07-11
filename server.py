import os
import json
import base64
import requests
import asyncio
import threading
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError

# Mock pyrebase locally to avoid ModuleNotFoundError when importing cell2 config
from unittest.mock import MagicMock
sys.modules['pyrebase'] = MagicMock()

# Temporarily mock print to prevent Windows encoding errors during cell2 import
import builtins
orig_print = builtins.print
builtins.print = lambda *args, **kwargs: None

# Add current folder to sys.path to resolve cells.cell2 imports safely
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from cells.cell2 import FIREBASE_CONFIG, DB_ROOT

# Restore original print
builtins.print = orig_print

# Global variables for Telegram login caching
telegram_clients = {}  # session_id -> { 'client': client, 'phone': phone, 'phone_code_hash': phone_code_hash }

# Create a global background event loop for async Telethon actions
loop = asyncio.new_event_loop()

def start_background_loop():
    asyncio.set_event_loop(loop)
    loop.run_forever()

threading.Thread(target=start_background_loop, daemon=True).start()

def run_async(coro):
    """Helper to run coroutines in the background event loop and wait for result."""
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result()


async def send_code_async(client, phone):
    """Helper to connect and request OTP on the background loop."""
    await client.connect()
    return await client.send_code_request(phone)


async def verify_code_async(client, phone, code, phone_code_hash, password=None):
    """Helper to complete Telegram login and disconnect client safely on background loop."""
    try:
        await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
    except SessionPasswordNeededError:
        if not password:
            raise
        await client.sign_in(password=password)
    session_str = client.session.save()
    await client.disconnect()
    return session_str


def compile_notebook_json(db_root=None):
    """Reads cell1.py through cell6.py in cells/ and compiles them into a Jupyter notebook JSON string."""
    cells = []
    cells_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cells")
    for i in range(1, 7):
        cell_path = os.path.join(cells_dir, f"cell{i}.py")
        if not os.path.exists(cell_path):
            continue
        with open(cell_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # Dynamically inject the active Firebase DB_ROOT in cell2.py
        if i == 2 and db_root:
            import re
            content = re.sub(r'DB_ROOT\s*=\s*["\'].*?["\']', f'DB_ROOT        = "{db_root}"', content)
            
        lines = content.splitlines(keepends=True)
        cells.append({
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": lines
        })
    
    notebook = {
        "cells": cells,
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3"
            }
        },
        "nbformat": 4,
        "nbformat_minor": 2
    }
    return json.dumps(notebook)


def push_notebook_to_kaggle(username, key, title, slug, db_root=None):
    """Compiles the local cells into a Jupyter Notebook and pushes to Kaggle REST API."""
    notebook_code = compile_notebook_json(db_root)
    credentials = base64.b64encode(f"{username}:{key}".encode()).decode()
    headers = {
        "Authorization": f"Basic {credentials}",
        "Content-Type": "application/json"
    }
    payload = {
        "id": None,
        "slug": f"{username}/{slug}",
        "title": title,
        "text": notebook_code,
        "language": "python",
        "kernelType": "notebook",
        "isPrivate": True,
        "enableGpu": False,
        "enableInternet": True,
        "datasetSources": [],
        "competitionSources": [],
        "kernelSources": []
    }
    url = "https://www.kaggle.com/api/v1/kernels/push"
    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    print(f"[*] Kaggle Push Response Status: {resp.status_code}")
    print(f"[*] Kaggle Push Response Body: {resp.text}")
    return resp.status_code, resp.text


def start_firebase_polling():
    """Polls Firebase RTDB for auto-restart triggers using standard REST API (no pyrebase dependency)."""
    import time
    db_url = FIREBASE_CONFIG["databaseURL"].rstrip('/')
    trigger_url = f"{db_url}/{DB_ROOT}/control/trigger_restart.json"
    print("[*] Local server listening to Firebase RTDB for auto-restart triggers via REST...")
    
    while True:
        try:
            resp = requests.get(trigger_url, timeout=5)
            if resp.status_code == 200 and resp.json() is True:
                # Reset trigger first to prevent double runs
                requests.put(trigger_url, json=False, timeout=5)
                print("[*] Firebase Poller: Auto-restart requested. Waiting 10 minutes (600s) for safe VM shutdown...")
                time.sleep(600)
                print("[*] Waiting complete. Pushing to Kaggle...")
                
                # Fetch latest credentials from database
                config_url = f"{db_url}/{DB_ROOT}/config/kaggle.json"
                kgl_resp = requests.get(config_url, timeout=5)
                if kgl_resp.status_code == 200:
                    kgl = kgl_resp.json()
                    if kgl:
                        username = kgl.get("username")
                        key = kgl.get("key")
                        title = kgl.get("title")
                        slug = kgl.get("slug")
                        if username and key and title and slug:
                            try:
                                status_code, resp_text = push_notebook_to_kaggle(username, key, title, slug)
                                print(f"[*] Push auto-restart triggered with status: {status_code}")
                            except Exception as e:
                                print(f"[!] Push auto-restart failed: {e}")
                else:
                    print("[!] Auto-restart failed: Could not read credentials from Firebase config.")
        except Exception as e:
            # Silent catch or standard debug to prevent console flood
            pass
        time.sleep(5)


# Start background listener thread
threading.Thread(target=start_firebase_polling, daemon=True).start()


class DashboardHTTPHandler(BaseHTTPRequestHandler):
    def end_headers(self):
        # Enable CORS for local cross-origin API calls if needed
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        # Serve Dashboard Files
        if self.path == '/' or self.path == '/index.html':
            self.serve_file('admin.html', 'text/html')
        elif self.path == '/admin.css':
            self.serve_file('admin.css', 'text/css')
        elif self.path == '/admin.js':
            self.serve_file('admin.js', 'application/javascript')
        elif self.path == '/api/health':
            self.send_json_response({'status': 'ok'})
        else:
            self.send_error(404, "File Not Found")

    def do_POST(self):
        # Parse content length
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length).decode('utf-8')
        
        try:
            body = json.loads(post_data) if post_data else {}
        except Exception:
            body = {}

        # ── API Endpoint: Telegram Send Code ──
        if self.path == '/api/telegram/send_code':
            phone = body.get('phone')
            api_id = body.get('api_id')
            api_hash = body.get('api_hash')

            if not phone or not api_id or not api_hash:
                self.send_json_response({'success': False, 'error': 'Missing required fields (phone, api_id, api_hash)'}, 400)
                return

            try:
                # Create standard telethon client and bind to background event loop
                client = TelegramClient(StringSession(), api_id, api_hash, loop=loop)
                
                # Connect and send code request on background loop
                code_result = run_async(send_code_async(client, phone))
                
                # Save client in memory using phone number as index
                telegram_clients[phone] = {
                    'client': client,
                    'phone': phone,
                    'phone_code_hash': code_result.phone_code_hash
                }
                
                # Cache the current active phone in self for OTP verification step
                DashboardHTTPHandler.last_phone = phone

                self.send_json_response({'success': True})
            except Exception as e:
                self.send_json_response({'success': False, 'error': str(e)}, 500)

        # ── API Endpoint: Telegram Verify Code ──
        elif self.path == '/api/telegram/verify_code':
            code = body.get('code')
            password = body.get('password')
            phone = getattr(DashboardHTTPHandler, 'last_phone', None)

            if not code or not phone or phone not in telegram_clients:
                self.send_json_response({'success': False, 'error': 'No active login session found. Send OTP first.'}, 400)
                return

            client_data = telegram_clients[phone]
            client = client_data['client']
            phone_code_hash = client_data['phone_code_hash']

            try:
                # Verify code and disconnect on background loop
                session_str = run_async(verify_code_async(client, phone, code, phone_code_hash, password))
                
                # Clean memory cache
                del telegram_clients[phone]
                
                self.send_json_response({
                    'success': True,
                    'session_string': session_str
                })
            except SessionPasswordNeededError:
                self.send_json_response({
                    'success': False,
                    'requires_password': True,
                    'error': 'Two-steps verification is enabled. A password is required.'
                }, 401)
            except Exception as e:
                self.send_json_response({'success': False, 'error': str(e)}, 500)

        # ── API Endpoint: Remote Kaggle Trigger (runs the pushed notebook) ──
        elif self.path == '/api/kaggle/run':
            username = body.get('username')
            key = body.get('key')
            slug = body.get('slug')
            db_root = body.get('dbRoot') or body.get('db_root')
            # Fallback title if not provided
            title = body.get('title', slug.replace('-', ' ').title())

            if not username or not key or not slug:
                self.send_json_response({'success': False, 'error': 'Missing Kaggle settings'}, 400)
                return

            try:
                status_code, resp_text = push_notebook_to_kaggle(username, key, title, slug, db_root)
                if status_code in (200, 201):
                    self.send_json_response({'success': True})
                else:
                    self.send_json_response({'success': False, 'error': f"Kaggle response {status_code}: {resp_text}"}, 500)
            except Exception as e:
                self.send_json_response({'success': False, 'error': str(e)}, 500)

        # ── API Endpoint: Remote Notebook Upload (Create/Update) ──
        elif self.path == '/api/kaggle/push':
            username = body.get('username')
            key = body.get('key')
            title = body.get('title')
            slug = body.get('slug')
            db_root = body.get('dbRoot') or body.get('db_root')

            if not username or not key or not title or not slug:
                self.send_json_response({'success': False, 'error': 'Missing required fields (username, key, title, slug)'}, 400)
                return

            try:
                status_code, resp_text = push_notebook_to_kaggle(username, key, title, slug, db_root)
                if status_code in (200, 201):
                    self.send_json_response({'success': True})
                else:
                    self.send_json_response({'success': False, 'error': f"Kaggle response {status_code}: {resp_text}"}, 500)
            except Exception as e:
                self.send_json_response({'success': False, 'error': str(e)}, 500)

        else:
            self.send_error(404, "Endpoint Not Found")

    def serve_file(self, filename, content_type):
        if not os.path.exists(filename):
            self.send_error(404, f"{filename} Not Found")
            return
        
        self.send_response(200)
        self.send_header('Content-Type', content_type)
        
        # Read and serve the file
        with open(filename, 'rb') as f:
            content = f.read()
            self.send_header('Content-Length', len(content))
            self.end_headers()
            self.wfile.write(content)

    def send_json_response(self, data, status_code=200):
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        response_bytes = json.dumps(data).encode('utf-8')
        self.send_header('Content-Length', len(response_bytes))
        self.end_headers()
        self.wfile.write(response_bytes)


def run(port=8000):
    server_address = ('', port)
    httpd = HTTPServer(server_address, DashboardHTTPHandler)
    print(f"[*] Cloner Ultra Local Server running on http://localhost:{port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Local Server...")
        httpd.server_close()

if __name__ == '__main__':
    run()
