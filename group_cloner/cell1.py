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

# Kaggle backend break fix: Downgrade cryptography to fix pyOpenSSL compatibility
install('cryptography==41.0.7')
install('pyOpenSSL==23.2.0')

print("✅ Sab libraries install ho gayi!")
