# ╔══════════════════════════════════════════╗
# ║  CELL 1 — Libraries Install             ║
# ║  Sirf pehli baar run karo               ║
# ╚══════════════════════════════════════════╝

import subprocess, sys

def install(pkg):
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-q', pkg])

install('telethon')
install('pyOpenSSL==23.3.0') # Fix Kaggle OpenSSL GEN_EMAIL bug
install('pyrebase4')
install('cryptg')
install('nest_asyncio')
install('requests')   # Kaggle API ke liye (already available on Kaggle but safe to add)

print("✅ Sab libraries install ho gayi!")
