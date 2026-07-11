# ╔══════════════════════════════════════════╗
# ║  CELL 3 — Source Discovery Engine       ║
# ║  Scans and counts videos/PDFs/sizes     ║
# ╚══════════════════════════════════════════╝

import asyncio
import nest_asyncio
from telethon import TelegramClient, types
from telethon.sessions import StringSession
from telethon.tl.functions.messages import GetForumTopicsRequest
import pyrebase

nest_asyncio.apply()

# Initialize Firebase
firebase = pyrebase.initialize_app(FIREBASE_CONFIG)
db = firebase.database()

def classify_media(msg) -> tuple:
    """Returns (is_video, is_pdf, size_mb) for a message."""
    if not msg.media or isinstance(msg.media, types.MessageMediaPhoto):
        return False, False, 0.0
    
    if hasattr(msg.media, 'document') and msg.media.document:
        doc = msg.media.document
        if getattr(doc, 'mime_type', '') == 'image/webp':
            return False, False, 0.0
            
        fname = ''
        for attr in doc.attributes:
            if isinstance(attr, types.DocumentAttributeFilename):
                fname = attr.file_name.lower()
                
        # Check if valid media extension
        if fname.endswith(TARGET_EXTS) or msg.video:
            size_mb = doc.size / (1024 * 1024)
            if fname.endswith('.pdf'):
                return False, True, size_mb
            else:
                return True, False, size_mb
    return False, False, 0.0

async def discover_and_count():
    print("🔗 Connecting to Telegram to scan Source...")
    user = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
    await user.start()
    
    source_topics = {}

    # ── CASE 1: Topic-based Forum Group ──
    if SOURCE_TYPE == "group_topic":
        print("📥 Fetching ALL topics from Source Group...")
        try:
            result = await user(GetForumTopicsRequest(
                peer=SOURCE_GROUP_ID,
                q="",
                offset_date=0,
                offset_id=0,
                offset_topic=0,
                limit=100
            ))
            topics = result.topics
        except Exception as e:
            print(f"❌ Failed to fetch topics: {e}")
            await user.disconnect()
            return

        print(f"📊 Found {len(topics)} topics. Scanning files inside each topic (Please wait)...")
        
        for topic in topics:
            if topic.id == 1: # Skip general topic usually
                continue
            
            print(f"🔍 Scanning Topic: '{topic.title}' (ID: {topic.id})...")
            videos, pdfs, total_size = 0, 0, 0.0
            
            async for msg in user.iter_messages(SOURCE_GROUP_ID, reply_to=topic.id, limit=None):
                is_video, is_pdf, size_mb = classify_media(msg)
                if is_video:
                    videos += 1
                    total_size += size_mb
                elif is_pdf:
                    pdfs += 1
                    total_size += size_mb

            source_topics[str(topic.id)] = {
                "name": topic.title,
                "videos": videos,
                "pdfs": pdfs,
                "size_mb": total_size
            }
            print(f"   ↳ Result: {videos} Videos, {pdfs} PDFs, {total_size:.1f} MB")

    # ── CASE 2 & 3: Channels or Non-Topic Groups ──
    else:
        print(f"📥 Scanning entire feed of Source {SOURCE_TYPE.upper()}...")
        videos, pdfs, total_size = 0, 0, 0.0
        
        async for msg in user.iter_messages(SOURCE_GROUP_ID, limit=None):
            # For groups without topics, ignore thread replies to count them in general
            is_video, is_pdf, size_mb = classify_media(msg)
            if is_video:
                videos += 1
                total_size += size_mb
            elif is_pdf:
                pdfs += 1
                total_size += size_mb
                
        # Save as single virtual topic ID "0"
        source_topics["0"] = {
            "name": "Main Channel Feed" if SOURCE_TYPE == "channel" else "Main Group Feed",
            "videos": videos,
            "pdfs": pdfs,
            "size_mb": total_size
        }
        print(f"   ↳ Result: {videos} Videos, {pdfs} PDFs, {total_size:.1f} MB")

    # Save to Firebase RTDB
    db.child(DB_ROOT).child("source_topics").set(source_topics)
    
    # Also initialize the queue with these topics
    db.child(DB_ROOT).child("queue").set(list(source_topics.keys()))
    
    print(f"\n✅ Scan Complete! {len(source_topics)} topics saved to Firebase. Ready for cell 4/5.")
    await user.disconnect()

# Check if source_topics already exist in Firebase before running startup scan
try:
    firebase = pyrebase.initialize_app(FIREBASE_CONFIG)
    db = firebase.database()
    existing_topics = db.child(DB_ROOT).child("source_topics").get().val()
except Exception:
    existing_topics = None

if existing_topics:
    print("✅ Source topics already exist in Firebase. Skipping automatic startup scan to preserve custom queue/deletions.")
else:
    asyncio.get_event_loop().run_until_complete(discover_and_count())
