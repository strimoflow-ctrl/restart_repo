# ╔══════════════════════════════════════════╗
# ║  CELL 1 — Libraries Install             ║
# ║  Sirf pehli baar run karo               ║
# ╚══════════════════════════════════════════╝

import subprocess, sys

def install(*pkgs):
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-q', *pkgs])

install('telethon', 'pyrebase4', 'cryptg', 'nest_asyncio', 'requests')

# Ensure pyOpenSSL is upgraded to match Kaggle's cryptography version
try:
    install('--upgrade', 'pyOpenSSL')
except Exception:
    pass

print("✅ Sab libraries install ho gayi!")
