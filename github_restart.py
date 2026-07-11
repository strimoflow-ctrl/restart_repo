import os
import json
import base64
import requests
import re

def get_firebase_url():
    """Extracts the Firebase DB URL directly from cells/cell2.py configuration."""
    try:
        cell2_path = os.path.join("cells", "cell2.py")
        if os.path.exists(cell2_path):
            with open(cell2_path, "r", encoding="utf-8") as f:
                content = f.read()
            match = re.search(r'["\']databaseURL["\']:\s*["\'](.*?)["\']', content)
            if match:
                return match.group(1)
    except Exception as e:
        print(f"[!] Error parsing cells/cell2.py: {e}")
    # Fallback default
    return "https://secret-gpt-default-rtdb.asia-southeast1.firebasedatabase.app"

def compile_notebook_json(db_root):
    """Compiles cells 1-6 into a single Jupyter notebook JSON format, injecting active db_root."""
    cells = []
    for i in range(1, 7):
        cell_path = os.path.join("cells", f"cell{i}.py")
        if not os.path.exists(cell_path):
            continue
        with open(cell_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # Dynamically inject the active Firebase DB_ROOT in cell2.py
        if i == 2:
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

def push_to_kaggle(username, key, title, slug, db_root):
    """Pushes the compiled notebook directly to Kaggle REST API."""
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
    print(f"[*] Kaggle Push for {db_root} Response Status: {resp.status_code}")
    print(f"[*] Kaggle Push for {db_root} Response Body: {resp.text}")
    return resp.status_code == 200

def main():
    db_url = get_firebase_url()
    print(f"[*] Connecting to Firebase DB: {db_url}")
    
    # 1. Fetch shallow root keys to locate active bots
    url = f"{db_url.rstrip('/')}/.json?shallow=true"
    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code != 200:
            print(f"[!] Failed to connect to Firebase: {resp.status_code}")
            return
        roots = resp.json() or {}
    except Exception as e:
        print(f"[!] Error fetching roots: {e}")
        return

    # 2. Iterate through bot roots and check restart triggers
    for root_key in roots.keys():
        # Match standard database prefixes
        if root_key.startswith("cloner_") or root_key == "vip_pluse":
            trigger_url = f"{db_url.rstrip('/')}/{root_key}/control/trigger_restart.json"
            try:
                trigger_resp = requests.get(trigger_url, timeout=5)
                if trigger_resp.status_code == 200 and trigger_resp.json() is True:
                    print(f"\n[!] Active restart trigger detected for root node: '{root_key}'!")
                    
                    # Fetch Kaggle credentials from this root's config
                    config_url = f"{db_url.rstrip('/')}/{root_key}/config/kaggle.json"
                    config_resp = requests.get(config_url, timeout=5)
                    
                    username = "pankajmourrya"
                    key = "581360a6a230292364e96a0ec8db406c"
                    title = None
                    slug = None
                    
                    if config_resp.status_code == 200:
                        kgl = config_resp.json() or {}
                        username = kgl.get("username") or username
                        key = kgl.get("key") or key
                        title = kgl.get("title")
                        slug = kgl.get("slug")
                    else:
                        print(f"[!] Failed to get Kaggle config for '{root_key}': {config_resp.status_code}")
                    
                    # Fallback to DB root name if config is missing title/slug
                    if not title:
                        title = f"Cloner {root_key.replace('_', ' ').title()}"
                    if not slug:
                        slug = root_key.replace("_", "-") # Kaggle slugs must use dashes
                        
                    if username and key and title and slug:
                        # Reset trigger in Firebase first to prevent double runs
                        requests.put(trigger_url, json=False, timeout=5)
                        print(f"[*] Reset trigger_restart to False for '{root_key}'")
                        
                        # Push to Kaggle API
                        print(f"[*] Compiling and pushing code to Kaggle as '{username}/{slug}'...")
                        success = push_to_kaggle(username, key, title, slug, root_key)
                        if success:
                            print(f"[+] Successfully restarted bot '{root_key}' on Kaggle VM!")
                        else:
                            print(f"[-] Failed to push restart version for '{root_key}'!")
                    else:
                        print(f"[!] Missing Kaggle credentials/config keys for '{root_key}'")
            except Exception as e:
                print(f"[!] Error processing root '{root_key}': {e}")

if __name__ == "__main__":
    main()
