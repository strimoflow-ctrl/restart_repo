# ╔══════════════════════════════════════════╗
# ║  CELL 1 — Libraries Install             ║
# ║  Sirf pehli baar run karo               ║
# ╚══════════════════════════════════════════╝

import subprocess, sys

def install(pkg):
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-q', pkg])

# Kaggle backend break fix: Force downgrade to stable crypto versions
subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-q', '--force-reinstall', 'cryptography==41.0.7', 'pyOpenSSL==23.2.0'])

install('telethon')
install('pyrebase4')
install('cryptg')
install('nest_asyncio')
install('requests')

print("✅ Sab libraries install ho gayi!")
