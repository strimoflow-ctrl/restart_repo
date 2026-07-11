# ╔══════════════════════════════════════════╗
# ║  CELL 4 — Helper Functions              ║
# ║  Bas run karo, kuch edit nahi karna     ║
# ╚══════════════════════════════════════════╝

import os, re, time, shutil, asyncio, math
from telethon import types
from telethon.errors import FloodWaitError
from telethon.tl.functions.upload import SaveBigFilePartRequest, SaveFilePartRequest
from telethon.tl.types import InputFileBig, InputFile

os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# ── Disk Guard ────────────────────────────────────────────────────────────────
def get_free_gb():
    return shutil.disk_usage(DOWNLOAD_DIR).free / (1024 ** 3)

def get_file_size_gb(msg):
    try:
        if msg.file and msg.file.size:
            return msg.file.size / (1024 ** 3)
    except:
        pass
    return 0.5

def calc_safe_slots(avg_file_gb: float) -> int:
    global MAX_WORKERS
    free_gb = get_free_gb()
    usable  = max(0, free_gb - DISK_BUFFER_GB)
    slots   = int(usable / max(avg_file_gb, 0.1))
    
    # Scale concurrency limits dynamically based on worker configuration
    if avg_file_gb >= 2.0:
        limit = min(MAX_WORKERS, 1)
    elif avg_file_gb >= 0.5:
        limit = min(MAX_WORKERS, 3)
    else:
        limit = MAX_WORKERS
        
    slots = min(slots, limit)
    return max(1, slots)

async def wait_for_disk_space(needed_gb: float, stats: dict):
    while True:
        free     = get_free_gb()
        required = needed_gb + DISK_BUFFER_GB
        if free >= required:
            return
        stats['current_action'] = f"⏳ Disk full — wait ({free:.1f}GB free)"
        await asyncio.sleep(15)

# ── Caption Cleaner ───────────────────────────────────────────────────────────
def clean_caption(text):
    global CAPTION_TEMPLATE, REPLACEMENTS
    
    original_text = text if text else ""
    
    # Apply word/username replacements if defined, otherwise apply default cleanup
    if REPLACEMENTS:
        for old_word, new_word in REPLACEMENTS:
            original_text = original_text.replace(old_word, new_word)
    else:
        # Fallback to default cleanup (removing links/usernames)
        original_text = re.sub(r'@\w+', '', original_text)
        original_text = re.sub(r'https?://\S+|t\.me/\S+', '', original_text)
        original_text = original_text.strip()
        
    # Render with the custom template
    if CAPTION_TEMPLATE:
        formatted = CAPTION_TEMPLATE.replace("{caption}", original_text)
        # Support literal "\n" in settings text
        formatted = formatted.replace("\\n", "\n")
        return formatted.strip()
        
    return original_text

# ── File Filter ───────────────────────────────────────────────────────────────
def is_valid_media(msg) -> bool:
    if not msg.media:
        return False
    if isinstance(msg.media, types.MessageMediaPhoto):
        return False
    if hasattr(msg.media, 'document'):
        doc = msg.media.document
        if getattr(doc, 'mime_type', '') == 'image/webp':
            return False
        fname = ''
        if msg.file and msg.file.name:
            fname = msg.file.name.lower()
        if fname:
            return fname.endswith(TARGET_EXTS)
        if msg.video:
            return True
        return False
    if msg.video:
        return True
    return False

# ── Speed Tracker ─────────────────────────────────────────────────────────────
class SpeedTracker:
    def __init__(self):
        self.bytes_in_window = 0
        self.window_start    = time.time()
        self.speed_mbps      = 0.0

    async def add(self, current_bytes: int):
        now   = time.time()
        delta = now - self.window_start
        if delta >= 2.0:
            self.speed_mbps      = (self.bytes_in_window * 8) / (delta * 1_000_000)
            self.bytes_in_window = 0
            self.window_start    = now
        self.bytes_in_window += current_bytes

speed_tracker = SpeedTracker()

# ── Progress Callback ─────────────────────────────────────────────────────────
def make_progress_cb(stats: dict, action: str, slot_idx: int = 0):
    last_bytes = [0]
    async def cb(current, total):
        pct = int((current / total) * 100) if total else 0
        
        # Update dynamic slot progress
        if 'slots' in stats and 0 <= slot_idx < len(stats['slots']):
            stats['slots'][slot_idx]['file_progress']  = pct
            stats['slots'][slot_idx]['current_action'] = f"{action} {pct}%"
            
        stats['file_progress']  = pct
        stats['current_action'] = f"{action} {pct}%"
        diff = current - last_bytes[0]
        if diff > 0:
            await speed_tracker.add(diff)
            last_bytes[0] = current
    return cb

# ── Fast Upload ───────────────────────────────────────────────────────────────
async def fast_upload(client, file_path, progress_callback=None, workers=3):
    file_size  = os.path.getsize(file_path)
    file_name  = os.path.basename(file_path)
    part_size  = 512 * 1024
    part_count = math.ceil(file_size / part_size)
    is_big     = file_size > 10 * 1024 * 1024
    file_id    = int.from_bytes(os.urandom(8), "big", signed=True)
    
    uploaded_bytes = 0
    queue = asyncio.Queue()
    for i in range(part_count):
        queue.put_nowait(i)
        
    async def upload_worker():
        nonlocal uploaded_bytes
        with open(file_path, "rb") as f:
            while True:
                try:
                    part_idx = queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                
                f.seek(part_idx * part_size)
                chunk = f.read(part_size)
                
                for attempt in range(10):
                    try:
                        if is_big:
                            await client(SaveBigFilePartRequest(
                                file_id=file_id, file_part=part_idx,
                                file_total_parts=part_count, bytes=chunk))
                        else:
                            await client(SaveFilePartRequest(
                                file_id=file_id, file_part=part_idx, bytes=chunk))
                        break
                    except Exception as e:
                        if attempt == 9: raise e
                        await asyncio.sleep(3)
                
                uploaded_bytes += len(chunk)
                if progress_callback:
                    if asyncio.iscoroutinefunction(progress_callback):
                        await progress_callback(uploaded_bytes, file_size)
                    else:
                        progress_callback(uploaded_bytes, file_size)
                queue.task_done()
                
    tasks = [asyncio.create_task(upload_worker()) for _ in range(workers)]
    await asyncio.gather(*tasks)
    
    if is_big:
        return InputFileBig(id=file_id, parts=part_count, name=file_name)
    else:
        return InputFile(id=file_id, parts=part_count, name=file_name, md5_checksum="")

# ── Fast Download ─────────────────────────────────────────────────────────────
async def fast_download(client, msg, file_path, progress_callback=None, workers=3):
    if not msg.document:
        return await client.download_media(msg, file_path, progress_callback=progress_callback)
        
    file_size        = msg.document.size
    downloaded_bytes = 0
    
    with open(file_path, "wb") as f:
        async for chunk in client.iter_download(msg.document, request_size=1024 * 1024):
            f.write(chunk)
            downloaded_bytes += len(chunk)
            if progress_callback:
                if asyncio.iscoroutinefunction(progress_callback):
                    await progress_callback(downloaded_bytes, file_size)
                else:
                    progress_callback(downloaded_bytes, file_size)
                    
    return file_path

# Auto-restart triggered externally via Firebase control flag

print("✅ Helper functions ready!")
print(f"   Disk free: {get_free_gb():.1f} GB")
