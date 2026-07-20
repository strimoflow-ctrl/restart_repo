# ╔══════════════════════════════════════════╗
# ║  CELL 5 — Core Engine                   ║
# ║  Realtime control, stats & integrations  ║
# ╚══════════════════════════════════════════╝

import asyncio
import nest_asyncio
import json
import os
import time
import pyrebase
from telethon import TelegramClient, events, types
from telethon.sessions import StringSession
from telethon.errors import FloodWaitError
from telethon.tl.functions.messages import CreateForumTopicRequest

nest_asyncio.apply()

# ── Firebase Connection ───────────────────────────────────────────────────────
firebase = pyrebase.initialize_app(FIREBASE_CONFIG)
db       = firebase.database()
print("✅ Firebase connected in Core Engine!")

# ── Logging to Firebase ───────────────────────────────────────────────────────
def log_to_firebase(message):
    print(message)
    try:
        # Push message to /logs
        db.child(DB_ROOT).child("logs").push(message)
    except:
        pass

# ── Dynamic Control Command Checks ────────────────────────────────────────────
cached_command = "start"

# Thread-safe slot allocator
slot_lock = asyncio.Lock()
active_slots = [None] * MAX_WORKERS  # Dynamic slot count based on config

async def check_control_state(stats):
    """Checks the cached command state to pause or stop the engine without Firebase spam."""
    global cached_command
    while True:
        if cached_command == "pause":
            stats['current_action'] = '⏸ Paused'
            await asyncio.sleep(5)
        elif cached_command == "stop":
            log_to_firebase("🛑 Stop signal received. Terminating process...")
            stats['user_stopped'] = True
            raise asyncio.CancelledError("Stopped by user")
        elif cached_command == "restart":
            log_to_firebase("🔄 Restart signal received! Exiting gracefully...")
            import os
            os._exit(0)
        else:
            break

# ── Process Single File ───────────────────────────────────────────────────────
async def process_file(user, msg, target_topic_id, sem, stats, bot):
    await check_control_state(stats)
    
    file_gb  = get_file_size_gb(msg)
    file_mb  = file_gb * 1024
    fname    = (msg.file.name if msg.file and msg.file.name else f"file_{msg.id}.mp4")
    fsize    = f"{file_mb:.0f}MB" if file_gb < 1 else f"{file_gb:.2f}GB"
    path     = os.path.join(DOWNLOAD_DIR, f"{msg.id}_{fname}")

    async with sem:
        await wait_for_disk_space(file_gb, stats)
        

        
        # 1. Acquire slot index
        slot_idx = -1
        async with slot_lock:
            for idx in range(len(active_slots)):
                if active_slots[idx] is None:
                    active_slots[idx] = msg.id
                    slot_idx = idx
                    break
        
        if slot_idx == -1:
            slot_idx = 0  # Fallback

        # Update slot details in stats
        if 'slots' in stats and slot_idx < len(stats['slots']):
            stats['slots'][slot_idx] = {
                "current_file": fname[:45],
                "current_size": fsize,
                "file_progress": 0,
                "current_action": "Fetching fresh link..."
            }
        
        stats['current_file']   = fname[:40]
        stats['current_size']   = fsize
        stats['file_progress']  = 0
        stats['current_action'] = 'Fetching fresh link...'

        # ── Fetch Fresh Msg ──
        try:
            fresh_msgs = await user.get_messages(msg.chat_id, ids=[msg.id])
            fresh_msg  = fresh_msgs[0] if fresh_msgs and fresh_msgs[0] else msg
        except Exception:
            fresh_msg = msg

        for attempt in range(5):
            await check_control_state(stats)
            thumb_path = None
            try:
                # ── Thumbnails ──
                attributes = None
                if hasattr(fresh_msg, 'document') and fresh_msg.document:
                    attributes = fresh_msg.document.attributes
                    if fresh_msg.document.thumbs:
                        thumb_path = os.path.join(DOWNLOAD_DIR, f"thumb_{fresh_msg.id}.jpg")
                        await user.download_media(fresh_msg.document, thumb=-1, file=thumb_path)
                
                # ── Download ──
                if 'slots' in stats and slot_idx < len(stats['slots']):
                    stats['slots'][slot_idx]['current_action'] = 'Download 0%'
                    stats['slots'][slot_idx]['file_progress']  = 0
                stats['current_action'] = 'Download 0%'
                await fast_download(user, fresh_msg, path,
                                    progress_callback=make_progress_cb(stats, 'Download', slot_idx))

                # ── Upload ──
                if 'slots' in stats and slot_idx < len(stats['slots']):
                    stats['slots'][slot_idx]['current_action'] = 'Upload 0%'
                    stats['slots'][slot_idx]['file_progress']  = 0
                stats['current_action'] = 'Upload 0%'
                stats['file_progress']  = 0
                uploaded_file = await fast_upload(user, path,
                                                  progress_callback=make_progress_cb(stats, 'Upload', slot_idx))
                
                # ── Target Posting ──
                # Send to topic ID if target group supports topics, otherwise send directly
                reply_param = target_topic_id if TARGET_TYPE == "group_topic" else None
                
                await user.send_file(
                    TARGET_GROUP_ID,
                    uploaded_file,
                    caption=clean_caption(fresh_msg.message),
                    reply_to=reply_param,
                    supports_streaming=True,
                    attributes=attributes,
                    thumb=thumb_path if thumb_path and os.path.exists(thumb_path) else None
                )

                # Save complete status in Firebase
                db.child(DB_ROOT).child("done_ids").child(str(msg.id)).set(True)
                stats['success']            += 1
                stats['global_videos_done'] += 1
                
                if 'slots' in stats and slot_idx < len(stats['slots']):
                    stats['slots'][slot_idx]['current_action'] = '✅ Done'
                    stats['slots'][slot_idx]['file_progress']  = 100
                stats['current_action']      = '✅ Done'
                stats['file_progress']       = 100

                if os.path.exists(path): os.remove(path)
                if thumb_path and os.path.exists(thumb_path): os.remove(thumb_path)
                break

            except FloodWaitError as e:
                wait = e.seconds + 5
                if 'slots' in stats and slot_idx < len(stats['slots']):
                    stats['slots'][slot_idx]['current_action'] = f'⏳ FloodWait {wait}s'
                stats['current_action'] = f'⏳ FloodWait {wait}s'
                log_to_firebase(f"⚠️ Telegram FloodWait: Waiting {wait}s...")
                if os.path.exists(path): os.remove(path)
                if thumb_path and os.path.exists(thumb_path): os.remove(thumb_path)
                await asyncio.sleep(wait)

            except asyncio.CancelledError:
                if os.path.exists(path): os.remove(path)
                if thumb_path and os.path.exists(thumb_path): os.remove(thumb_path)
                raise

            except Exception as e:
                err = str(e)[:60]
                wait_time = getattr(e, 'seconds', None)
                if wait_time is None and "wait of" in str(e).lower():
                    import re
                    match = re.search(r'wait of (\d+)', str(e).lower())
                    if match: wait_time = int(match.group(1))
                
                if wait_time:
                    wait = wait_time + 5
                    if 'slots' in stats and slot_idx < len(stats['slots']):
                        stats['slots'][slot_idx]['current_action'] = f'⏳ FloodWait {wait}s'
                    stats['current_action'] = f'⏳ FloodWait {wait}s'
                    log_to_firebase(f"⚠️ Telegram FloodWait: Waiting {wait}s...")
                    if os.path.exists(path): os.remove(path)
                    if thumb_path and os.path.exists(thumb_path): os.remove(thumb_path)
                    await asyncio.sleep(wait)
                    continue
                
                if os.path.exists(path): os.remove(path)
                if thumb_path and os.path.exists(thumb_path): os.remove(thumb_path)
                
                if attempt == 4:
                    stats['errors']         += 1
                    stats['last_error']      = err
                    if 'slots' in stats and slot_idx < len(stats['slots']):
                        stats['slots'][slot_idx]['current_action'] = '❌ Failed'
                    stats['current_action']  = f'❌ Failed'
                    log_to_firebase(f"❌ Failed cloning message ID {msg.id}: {err}")
                else:
                    wait = 5 * (2 ** attempt)
                    if 'slots' in stats and slot_idx < len(stats['slots']):
                        stats['slots'][slot_idx]['current_action'] = f'Retry {attempt+1}/5 ({wait}s)'
                    stats['current_action']  = f'Retry {attempt+1}/5 ({wait}s)'
                    await asyncio.sleep(wait)
        
        # 2. Release slot index when done or failed
        async with slot_lock:
            active_slots[slot_idx] = None
            if 'slots' in stats and slot_idx < len(stats['slots']):
                stats['slots'][slot_idx] = {
                    "current_file": "Idle",
                    "current_size": "0.0 MB",
                    "file_progress": 0,
                    "current_action": "IDLE"
                }

# ── Auto-Restart Handler ──────────────────────────────────────────────────────
async def auto_restart_timer(user, bot, stats, all_tasks_ref):
    await asyncio.sleep(RESTART_AFTER_SEC)
    print("\n⏰ Auto-restart trigger time reached!")
    log_to_firebase("🔄 Auto-restart trigger initiated. Stopping active tasks gracefully...")
    stats['restarting'] = True

    try:
        await bot.send_message(
            OWNER_CHAT_ID,
            f"⏰ **AUTO-RESTART ENGINE TRIGGERED**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Files Cloned: `{stats['success']}`\n"
            f"Global Progress: `{stats['global_topics_done']}/{stats['global_topics_total']} Topics`"
        )
    except:
        pass

    # Cancel ongoing tasks
    tasks = all_tasks_ref.get('tasks', [])
    for t in tasks:
        if not t.done():
            t.cancel()
            
    # Cancel the main task
    main_task = all_tasks_ref.get('main_task')
    if main_task and not main_task.done():
        main_task.cancel()

# ── Triggers Listener Loop ────────────────────────────────────────────────────
async def triggers_listener_loop(user, bot):
    """Listens for Scan or Topic Mapping triggers from Web UI."""
    while True:
        try:
            # 1. Check Scan Trigger
            scan_trigger = db.child(DB_ROOT).child("control").child("trigger_scan").get().val()
            if scan_trigger:
                db.child(DB_ROOT).child("control").child("trigger_scan").set(False)
                log_to_firebase("🔍 Web Trigger: Scanning source...")
                # Run scanning logic directly in background
                await run_remote_scan(user)
            
            # 2. Check Topic Mapping Trigger
            map_trigger = db.child(DB_ROOT).child("control").child("trigger_map").get().val()
            if map_trigger:
                db.child(DB_ROOT).child("control").child("trigger_map").set(False)
                log_to_firebase("✨ Web Trigger: Mapping target topics...")
                await run_remote_mapping(user)
                
        except Exception as e:
            print(f"Triggers loop error: {e}")
        await asyncio.sleep(5)

# Helper: Run remote scan
async def run_remote_scan(user):
    source_topics = {}
    
    if SOURCE_TYPE == "group_topic":
        try:
            result = await user(GetForumTopicsRequest(
                peer=SOURCE_GROUP_ID, q="", offset_date=0, offset_id=0, offset_topic=0, limit=100
            ))
            topics = result.topics
        except Exception as e:
            log_to_firebase(f"❌ Scan failed: {e}")
            return

        for topic in topics:
            if topic.id == 1: continue
            videos, pdfs, total_size = 0, 0, 0.0
            async for msg in user.iter_messages(SOURCE_GROUP_ID, reply_to=topic.id, limit=None):
                is_video, is_pdf, size_mb = classify_media(msg)
                if is_video: videos += 1; total_size += size_mb
                elif is_pdf: pdfs += 1; total_size += size_mb

            source_topics[str(topic.id)] = {
                "name": topic.title, "videos": videos, "pdfs": pdfs, "size_mb": total_size
            }
    else:
        videos, pdfs, total_size = 0, 0, 0.0
        async for msg in user.iter_messages(SOURCE_GROUP_ID, limit=None):
            is_video, is_pdf, size_mb = classify_media(msg)
            if is_video: videos += 1; total_size += size_mb
            elif is_pdf: pdfs += 1; total_size += size_mb
            
        source_topics["0"] = {
            "name": "Main Channel Feed" if SOURCE_TYPE == "channel" else "Main Group Feed",
            "videos": videos, "pdfs": pdfs, "size_mb": total_size
        }

    db.child(DB_ROOT).child("source_topics").set(source_topics)
    db.child(DB_ROOT).child("queue").set(list(source_topics.keys()))
    db.child(DB_ROOT).child("finished_topics").remove()
    log_to_firebase(f"✅ Scanning Complete. Found {len(source_topics)} folders. Finished topics cleared for rescan.")

# Helper: Run remote topic mapping/creation
async def run_remote_mapping(user):
    source_topics = db.child(DB_ROOT).child("source_topics").get().val() or {}
    mapped_topics = db.child(DB_ROOT).child("mapped_topics").get().val() or {}
    
    if TARGET_TYPE != "group_topic":
        log_to_firebase("ℹ️ Target is a channel/normal group. Topic creation skipped.")
        return

    # 1. Fetch existing topics in the Target Group to avoid creating duplicate names
    target_name_to_id = {}
    try:
        log_to_firebase("🔍 Scanning Target Group for existing topics...")
        result = await user(GetForumTopicsRequest(
            peer=TARGET_GROUP_ID, q="", offset_date=0, offset_id=0, offset_topic=0, limit=100
        ))
        for t in result.topics:
            target_name_to_id[t.title.lower().strip()] = t.id
        log_to_firebase(f"✅ Found {len(target_name_to_id)} existing topics in Target Group.")
    except Exception as e:
        log_to_firebase(f"⚠️ Failed to scan target group topics: {e}")

    for old_id_str, topic_data in source_topics.items():
        title = topic_data.get("name") if isinstance(topic_data, dict) else topic_data
        title_clean = title.lower().strip()
        
        # Check if already mapped in Firebase
        if old_id_str in mapped_topics:
            continue
            
        if title_clean in target_name_to_id:
            mapped_id = target_name_to_id[title_clean]
            log_to_firebase(f"🔗 Mapped existing topic: '{title}' -> Target ID: {mapped_id}")
            mapped_topics[old_id_str] = mapped_id
        else:
            try:
                # Create a new topic in target group using user account (bypass bot restrictions)
                res = await user(CreateForumTopicRequest(
                    peer=TARGET_GROUP_ID,
                    title=title
                ))
                new_topic_id = None
                if hasattr(res, 'updates'):
                    for update in res.updates:
                        if hasattr(update, 'message') and hasattr(update.message, 'id'):
                            new_topic_id = update.message.id
                            break
                if not new_topic_id and hasattr(res, 'id'):
                    new_topic_id = res.id
                    
                if new_topic_id:
                    log_to_firebase(f"✨ Created Topic: '{title}' -> Target ID: {new_topic_id}")
                    mapped_topics[old_id_str] = new_topic_id
                else:
                    log_to_firebase(f"⚠️ Created topic '{title}', but could not extract new ID.")
            except Exception as e:
                log_to_firebase(f"❌ Failed to create topic '{title}': {e}")
                
    db.child(DB_ROOT).child("mapped_topics").set(mapped_topics)
    log_to_firebase("✅ Target topic mapping update finished.")
                # ── Dynamic ETA & Status Reporter ─────────────────────────────────────────────
async def monitor_and_reporter(bot, stats):
    global cached_command, MAX_WORKERS, CAPTION_TEMPLATE, REPLACEMENTS, active_slots
    while not stats.get('all_done') and not stats.get('restarting'):
        try:
            # 1. Read command and configurations from Firebase individually to save bandwidth
            control_data = db.child(DB_ROOT).child("control").get().val() or {}
            fb_config = db.child(DB_ROOT).child("config").get().val() or {}
            
            # Update cached command
            cached_command = control_data.get("command", "start")
            
            # Override Telegram config (for internal cell state)
            tg = fb_config.get("telegram", {})
            if tg.get("bot_token"):
                global BOT_TOKEN
                BOT_TOKEN = tg.get("bot_token")
            if tg.get("owner_chat_id"):
                global OWNER_CHAT_ID
                OWNER_CHAT_ID = int(tg.get("owner_chat_id"))
                
            # Override groups config
            grp = fb_config.get("groups", {})
            if grp.get("source_group_id"):
                global SOURCE_GROUP_ID, SOURCE_TYPE, TARGET_GROUP_ID, TARGET_TYPE
                SOURCE_GROUP_ID = int(grp.get("source_group_id"))
                if grp.get("source_type"): SOURCE_TYPE = grp.get("source_type")
                if grp.get("target_group_id"): TARGET_GROUP_ID = int(grp.get("target_group_id"))
                if grp.get("target_type"): TARGET_TYPE = grp.get("target_type")
                
            # Override kaggle credentials and speed / branding settings
            kgl = fb_config.get("kaggle", {})
            if kgl.get("workers"):
                new_workers = int(kgl.get("workers"))
                if new_workers != MAX_WORKERS:
                    log_to_firebase(f"⚙️ Concurrency workers count changed from {MAX_WORKERS} to {new_workers}")
                    MAX_WORKERS = new_workers
                    
                    # Resize stats slots list
                    current_slots = stats.get('slots', [])
                    if len(current_slots) < MAX_WORKERS:
                        for _ in range(MAX_WORKERS - len(current_slots)):
                            current_slots.append({
                                "current_file": "Idle",
                                "current_size": "0.0 MB",
                                "file_progress": 0,
                                "current_action": "IDLE"
                            })
                    elif len(current_slots) > MAX_WORKERS:
                        current_slots = current_slots[:MAX_WORKERS]
                    stats['slots'] = current_slots
                    
                    # Resize thread active slots list
                    async with slot_lock:
                        if len(active_slots) < MAX_WORKERS:
                            active_slots += [None] * (MAX_WORKERS - len(active_slots))
                        elif len(active_slots) > MAX_WORKERS:
                            active_slots = active_slots[:MAX_WORKERS]
                            
            if kgl.get("caption_template") is not None:
                CAPTION_TEMPLATE = kgl.get("caption_template")
                
            if kgl.get("replacements"):
                raw_repls = kgl.get("replacements").strip().split('\n')
                new_repls = []
                for line in raw_repls:
                    if '|' in line:
                        parts = line.split('|', 1)
                        new_repls.append((parts[0].strip(), parts[1].strip()))
                REPLACEMENTS = new_repls

            # Uptime calculation
            elapsed  = int(time.time() - stats['start_time'])
            h        = elapsed // 3600
            m        = (elapsed % 3600) // 60
            s        = elapsed % 60
            uptime_str = f"{h:02d}:{m:02d}:{s:02d}"

            # Auto-restart timer string
            restart_in = max(0, int(RESTART_AFTER_SEC - elapsed))
            rh = restart_in // 3600
            rm = (restart_in % 3600) // 60
            restart_str = f"{rh:02d}:{rm:02d}"

            remaining_mb = stats.get('remaining_mb', 0.0)
            
            speed = speed_tracker.speed_mbps
            eta_str = "Calculating..."
            if speed > 0.5:
                speed_mb_s = speed / 8.0
                eta_sec = remaining_mb / speed_mb_s
                if eta_sec < 60:
                    eta_str = f"{eta_sec:.0f}s"
                elif eta_sec < 3600:
                    eta_str = f"{int(eta_sec//60)}m {int(eta_sec%60)}s"
                else:
                    eta_str = f"{int(eta_sec//3600)}h {int((eta_sec%3600)//60)}m"

            # Sync stats packet to Firebase
            status_packet = {
                "last_heartbeat": time.time(),
                "is_running": True,
                "current_action": stats['current_action'],
                "current_file": stats['current_file'],
                "current_size": stats['current_size'],
                "file_progress": stats['file_progress'],
                "speed_mbps": speed,
                "free_gb": get_free_gb(),
                "uptime": uptime_str,
                "restart_timer": restart_str,
                "eta": eta_str,
                "global_topics_done": stats['global_topics_done'],
                "global_topics_total": stats['global_topics_total'],
                "global_videos_done": stats['global_videos_done'],
                "topic_name": stats['topic_name'],
                "topic_done": stats['topic_done'],
                "topic_total": stats['topic_total'],
                "slots": stats.get('slots', [])
            }
            db.child(DB_ROOT).child("status").update(status_packet)
            
        except Exception as e:
            print(f"Stats reporter error: {e}")
        await asyncio.sleep(10)

async def run_queue_engine(user, bot, stats, all_tasks_ref, done_ids, finished_topics):
    failed_in_current_run = set()
    warned_topics = set()

    while not stats['all_done']:
        await check_control_state(stats)

        # Dynamic reload of queue and topics
        queue = db.child(DB_ROOT).child("queue").get().val() or []
        source_topics = db.child(DB_ROOT).child("source_topics").get().val() or {}
        mapped_topics = db.child(DB_ROOT).child("mapped_topics").get().val() or {}
        
        # Reload finished topics
        finish_data     = db.child(DB_ROOT).child("finished_topics").get().val() or {}
        finished_topics = set(str(k) for k in finish_data.keys())
        
        stats['global_topics_total'] = len(queue)
        stats['global_topics_done'] = len(finished_topics)

        # Calculate total remaining MB
        remaining_mb = 0.0
        for q_id in queue:
            if str(q_id) not in finished_topics:
                topic = source_topics.get(str(q_id), {})
                if isinstance(topic, dict):
                    remaining_mb += topic.get("size_mb", 0.0)
                else:
                    remaining_mb += 100.0
        stats['remaining_mb'] = remaining_mb

        # Find next unprocessed topic ID in the queue (skipping failed ones in this run)
        next_topic_id = None
        for q_id in queue:
            if q_id not in finished_topics and q_id not in failed_in_current_run:
                next_topic_id = q_id
                break

        if not next_topic_id:
            # If everything was completed, but some failed in this run pass, we clear and retry
            if failed_in_current_run:
                log_to_firebase("🔄 Retrying topics that had file failures in this pass...")
                failed_in_current_run.clear()
                await asyncio.sleep(10)
                continue
            else:
                # Everything successfully completed
                stats['all_done'] = True
                break

        topic_data = source_topics.get(next_topic_id)
        if not topic_data:
            # If topic ID in queue doesn't exist in metadata, mark it finished
            db.child(DB_ROOT).child("finished_topics").child(next_topic_id).set(True)
            continue

        title = topic_data.get("name") if isinstance(topic_data, dict) else topic_data
        stats['topic_name'] = title
        stats['topic_done'] = 0
        stats['topic_total'] = 0

        log_to_firebase(f"\n📂 Processing Queue Item: '{title}' (ID: {next_topic_id})")

        # ── Fetch target topic mapping ──
        target_topic_id = None
        if TARGET_TYPE == "group_topic":
            target_topic_id = mapped_topics.get(next_topic_id)
            if not target_topic_id:
                stats['current_action'] = f"⏳ Awaiting mapping for '{title}'..."
                if next_topic_id not in warned_topics:
                    log_to_firebase(f"⚠️ Target Topic mapping missing for '{title}'. Please click 'Auto-Map Targets' on the dashboard.")
                    warned_topics.add(next_topic_id)
                await asyncio.sleep(5)
                continue

        # ── Fetch messages from source ──
        msgs = []
        try:
            # If source type is topics, get messages from specific topic, else scan whole feed
            reply_param = int(next_topic_id) if SOURCE_TYPE == "group_topic" else None
            
            async for m in user.iter_messages(SOURCE_GROUP_ID, reply_to=reply_param, limit=None):
                if not is_valid_media(m):
                    continue
                if str(m.id) in done_ids:
                    continue
                msgs.append(m)
        except Exception as e:
            log_to_firebase(f"⚠️ Failed reading messages from topic '{title}': {e}")
            failed_in_current_run.add(next_topic_id)
            continue

        msgs.reverse()
        stats['topic_total'] = len(msgs)

        if not msgs:
            log_to_firebase(f"✅ Topic '{title}' has no new files to clone. Marking done.")
            db.child(DB_ROOT).child("finished_topics").child(next_topic_id).set(True)
            continue

        # ── Setup Dynamic Parallel Slots ──
        sample  = [get_file_size_gb(m) for m in msgs[:10]]
        avg_gb  = sum(sample) / len(sample) if sample else 0.5
        n_slots = calc_safe_slots(avg_gb)
        sem     = asyncio.Semaphore(n_slots)

        log_to_firebase(f"   ↳ Files to clone: {len(msgs)} | Speed slots: {n_slots} workers")

        tasks = [
            asyncio.create_task(process_file(user, m, target_topic_id, sem, stats, bot))
            for m in msgs
        ]
        all_tasks_ref['tasks'] = tasks

        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            topic_success_count = 0
            any_failed = False
            
            for m, r in zip(msgs, results):
                if isinstance(r, Exception):
                    any_failed = True
                    log_to_firebase(f"❌ File '{m.id}' failed inside topic '{title}': {r}")
                else:
                    done_ids.add(str(m.id))
                    topic_success_count += 1
            
            stats['topic_done'] = topic_success_count
            
        except asyncio.CancelledError:
            # Loop aborted (Pause/Stop/Restart)
            for t in tasks:
                if not t.done(): t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            log_to_firebase("⏸ Processing loop cancelled. Saving state...")
            raise

        if any_failed:
            failed_in_current_run.add(next_topic_id)
            log_to_firebase(f"⚠️ Topic '{title}' had failures. It will be retried in the next pass.")
        else:
            # Mark this topic completed ONLY if no files failed!
            db.child(DB_ROOT).child("finished_topics").child(next_topic_id).set(True)
            log_to_firebase(f"✅ Completed processing topic: '{title}'")

# ── Main Cloning Loop ─────────────────────────────────────────────────────────
async def main():
    global cached_command
    """Main Orchestrator Loop"""
    try:
        db.child(DB_ROOT).child("logs").remove()
    except:
        pass
    log_to_firebase("🚀 Initializing Cloner Ultra Core Engine...")
    
    global stats
    all_tasks_ref = {'tasks': []}
    all_tasks_ref['main_task'] = asyncio.current_task()
    
    user = None
    bot = None
    stats = {
        'success':              0,
        'errors':               0,
        'topic_name':           'Syncing Firebase...',
        'topic_done':           0,
        'topic_total':          0,
        'global_topics_done':   0,
        'global_topics_total':  0,
        'global_videos_done':   0,
        'current_file':         '...',
        'current_size':         '...',
        'current_action':       'Initializing',
        'file_progress':        0,
        'last_error':           '',
        'start_time':           time.time(),
        'all_done':             False,
        'restarting':           False,
        'slots': [
            {
                "current_file": "Idle",
                "current_size": "0.0 MB",
                "file_progress": 0,
                "current_action": "IDLE"
            }
            for _ in range(MAX_WORKERS)
        ]
    }

    try:
        user = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
        bot  = TelegramClient(StringSession(''), API_ID, API_HASH)
        await user.start()
        await bot.start(bot_token=BOT_TOKEN)
        log_to_firebase("✅ Connection to Telegram API established!")

        # Start helper loops
        asyncio.create_task(monitor_and_reporter(bot, stats))
        asyncio.create_task(auto_restart_timer(user, bot, stats, all_tasks_ref))
        asyncio.create_task(triggers_listener_loop(user, bot))

        while True:
            # Initialize sync state from Firebase
            done_data       = db.child(DB_ROOT).child("done_ids").get().val() or {}
            done_ids        = set(str(k) for k in done_data.keys())
            finish_data     = db.child(DB_ROOT).child("finished_topics").get().val() or {}
            finished_topics = set(str(k) for k in finish_data.keys())
            
            stats['global_videos_done']  = len(done_ids)
            stats['global_topics_done']  = len(finished_topics)

            # ── Listening to Start Command ──
            log_to_firebase("💤 Idle. Awaiting Start command from Admin Dashboard...")
            stats['current_action'] = '💤 Awaiting Start command'
            
            # Wait until command is "start"
            while True:
                if cached_command == "start":
                    break
                elif cached_command == "restart":
                    log_to_firebase("🔄 Restart signal received! Exiting gracefully...")
                    import os
                    os._exit(0)
                await asyncio.sleep(5)

            log_to_firebase("🚀 Start command received! Running queue...")

            stats['all_done'] = False
            stats['user_stopped'] = False
            
            try:
                await run_queue_engine(user, bot, stats, all_tasks_ref, done_ids, finished_topics)
            except asyncio.CancelledError:
                log_to_firebase("⏸ Processing cancelled (User stopped).")

            if stats.get('restarting'):
                break

            if stats.get('user_stopped'):
                log_to_firebase("⏸ Process paused by user. Returning to idle...")
            else:
                db.child(DB_ROOT).child("status").child("current_action").set("🏆 ALL DONE!")
                log_to_firebase("\n🏆 SUCCESS: All files in the queue have been successfully cloned! Returning to idle...")
                
            db.child(DB_ROOT).child("control").child("command").set("stop")
            cached_command = "stop"
            await asyncio.sleep(2)

    except asyncio.CancelledError:
        pass
    finally:
        if stats and stats.get('restarting'):
            log_to_firebase("🔄 Auto-restart request submitted to Firebase. Awaiting cloud orchestrator...")
            try:
                db.child(DB_ROOT).child("control").child("trigger_restart").set(True)
            except Exception as e:
                print(f"Error setting trigger_restart: {e}")
        else:
            log_to_firebase("\n🏁 Main engine stopped permanently.")
            
        try:
            if user: await user.disconnect()
        except: pass
        try:
            if bot: await bot.disconnect()
        except: pass

# Run Engine Setup
print("✅ Core Engine logic loaded.")
