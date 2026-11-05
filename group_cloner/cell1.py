# ╔══════════════════════════════════════════╗
# ║  CELL 1 — Libraries Install             ║
# ║  Sirf pehli baar run karo               ║
# ╚══════════════════════════════════════════╝

import subprocess, sys

def install(*pkgs):
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-q', *pkgs])

# Main essential libraries (cryptg excluded because Python 3.13 lacks prebuilt wheels)
install('telethon', 'pyrebase4', 'nest_asyncio', 'requests')

# Optional cryptg accelerator (safely ignored if build fails on Python 3.13)
try:
    install('cryptg')
except Exception:
    pass

# Ensure pyOpenSSL is upgraded to match Kaggle's cryptography version
try:
    install('--upgrade', 'pyOpenSSL')
except Exception:
    pass

print("✅ Sab libraries install ho gayi!")
