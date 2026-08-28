# ╔══════════════════════════════════════════╗
# ║  CELL 2 — Configuration                 ║
# ║  Firebase aur Database configuration     ║
# ╚══════════════════════════════════════════╝

import pyrebase

# ── Firebase Setup ────────────────────────
# Apne Firebase Console se static config daalo
FIREBASE_CONFIG = {
    "apiKey": "AIzaSyBHG8jahQyjKMBBjB0Pfl5vO7_kouRrtDo",
    "authDomain": "secret-gpt.firebaseapp.com",
    "databaseURL": "https://secret-gpt-default-rtdb.asia-southeast1.firebasedatabase.app",
    "projectId": "secret-gpt",
    "storageBucket": "secret-gpt.firebasestorage.app",
    "messagingSenderId": "421414243386",
    "appId": "1:421414243386:web:a2b2e5a4173303d51b7903"
}

DB_ROOT        = "cloner_v6_mapping"
DOWNLOAD_DIR   = "/kaggle/working/downloads"
TARGET_EXTS    = ('.mp4', '.mkv', '.webm', '.avi', '.pdf', '.zip', '.rar')
DISK_BUFFER_GB = 5.0
RESTART_AFTER_SEC = 11.5 * 3600  # 11.5 ghante

# ── Local Configuration (Initialized as None/Empty) ──
# Note: Sabhi configurations Firebase RTDB se live load hongi.
API_ID             = None
API_HASH           = ""
SESSION_STRING     = ""
BOT_TOKEN          = ""
OWNER_CHAT_ID      = 0

SOURCE_GROUP_ID    = 0
SOURCE_TYPE        = "group_topic"  # Options: "group_topic", "group_no_topic", "channel"
TARGET_GROUP_ID    = 0
TARGET_TYPE        = "group_topic"  # Options: "group_topic", "group_no_topic", "channel"

KAGGLE_USERNAME    = ""
KAGGLE_KEY         = ""
KAGGLE_KERNEL_SLUG = ""
MAX_WORKERS        = 3
CAPTION_TEMPLATE   = ""
REPLACEMENTS       = []

# ── Dynamic Config Loader ─────────────────
print("🔥 Connecting to Firebase Realtime Database...")
try:
    firebase = pyrebase.initialize_app(FIREBASE_CONFIG)
    db = firebase.database()
    
    print(f"⏳ Waiting for configuration under root node '{DB_ROOT}'...")
    while True:
        fb_config = db.child(DB_ROOT).child("config").get().val()
        if fb_config:
            break
        print(f"⚠️ Configuration is empty! Please configure and click 'Save & Apply All Configurations' on the Admin Dashboard for root node: '{DB_ROOT}'")
        time.sleep(10)
        
    print("✅ Found dynamic configuration in Firebase. Overriding fallbacks...")
    
    # Override Telegram config
    tg = fb_config.get("telegram", {})
    if tg.get("api_id"): API_ID = int(tg.get("api_id"))
    if tg.get("api_hash"): API_HASH = tg.get("api_hash")
    if tg.get("session_string"): SESSION_STRING = tg.get("session_string")
    if tg.get("bot_token"): BOT_TOKEN = tg.get("bot_token")
    if tg.get("owner_chat_id"): OWNER_CHAT_ID = int(tg.get("owner_chat_id"))
    
    # Override groups config
    grp = fb_config.get("groups", {})
    if grp.get("source_group_id"): SOURCE_GROUP_ID = int(grp.get("source_group_id"))
    if grp.get("source_type"): SOURCE_TYPE = grp.get("source_type")
    if grp.get("target_group_id"): TARGET_GROUP_ID = int(grp.get("target_group_id"))
    if grp.get("target_type"): TARGET_TYPE = grp.get("target_type")
    
    # Override kaggle credentials and speed / branding settings
    kgl = fb_config.get("kaggle", {})
    if kgl.get("username"): KAGGLE_USERNAME = kgl.get("username")
    if kgl.get("key"): KAGGLE_KEY = kgl.get("key")
    if kgl.get("slug"): KAGGLE_KERNEL_SLUG = kgl.get("slug")
    if kgl.get("workers"): MAX_WORKERS = int(kgl.get("workers"))
    if kgl.get("caption_template") is not None: CAPTION_TEMPLATE = kgl.get("caption_template")
    if kgl.get("replacements"):
        raw_repls = kgl.get("replacements").strip().split('\n')
        REPLACEMENTS = []
        for line in raw_repls:
            if '|' in line:
                parts = line.split('|', 1)
                REPLACEMENTS.append((parts[0].strip(), parts[1].strip()))
    # Verify critical configuration parameters are loaded
    if not API_ID or not SESSION_STRING or not BOT_TOKEN or not SOURCE_GROUP_ID or not TARGET_GROUP_ID:
        raise ValueError(
            f"❌ CRITICAL CONFIGURATION ERROR:\n"
            f"   Active configuration under Firebase root path '{DB_ROOT}' is incomplete!\n"
            f"   Please configure and save credentials from the Admin Dashboard first."
        )
except Exception as e:
    print(f"❌ Failed to sync config with Firebase: {e}")
    # Force stop the execution on config failure to prevent cross-bot crashes!
    raise SystemExit("Terminating due to configuration error.")

print("\n⚙️ CURRENT CONFIGURATION:")
print(f"   Source: {SOURCE_GROUP_ID} (Type: {SOURCE_TYPE})")
print(f"   Target: {TARGET_GROUP_ID} (Type: {TARGET_TYPE})")
print(f"   Auto-restart: {RESTART_AFTER_SEC/3600:.1f} hours")
print(f"   Firebase DB: {FIREBASE_CONFIG.get('databaseURL', '❌ MISSING')}")
