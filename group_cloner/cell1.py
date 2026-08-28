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

# Kaggle backend break fix: Force downgrade to stable crypto versions at the VERY END
# so pip dependency resolver doesn't accidentally upgrade it back while installing other packages!
subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-q', '--force-reinstall', '--no-deps', 'cryptography==41.0.7', 'pyOpenSSL==23.2.0'])

print("✅ Sab libraries install ho gayi!")
