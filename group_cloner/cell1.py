# ╔══════════════════════════════════════════╗
# ║  CELL 1 — Libraries Install             ║
# ║  Sirf pehli baar run karo               ║
# ╚══════════════════════════════════════════╝

import subprocess, sys

def install(pkg):
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-q', pkg])

install('telethon')
install('pyrebase4')
install('cryptg')
install('nest_asyncio')
install('requests')

# Kaggle backend break fix: Prevent pyrebase from crashing due to Kaggle's pre-loaded cryptography module
# by tricking oauth2client into thinking OpenSSL is not installed.
sys.modules['OpenSSL'] = None

print("✅ Sab libraries install ho gayi!")
