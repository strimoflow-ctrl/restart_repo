// Configuration Variables
let database = null;
let dbRoot = "cloner_v5_mapping";
let isBotActive = false;
const localServerUrl = window.location.origin.includes("localhost") || window.location.protocol === "file:"
    ? "http://localhost:8000"
    : window.location.origin;

// Bot instances storage
let botInstances = [];

// DOM Elements
const elLocalStatus = document.getElementById("local-server-status");
const elKaggleStatus = document.getElementById("kaggle-engine-status");
const elConsole = document.getElementById("system-console");
const elSelectInstance = document.getElementById("select-bot-instance");
const elSaveQueueBtn = document.getElementById("btn-save-queue");
let hasUnsavedQueueChanges = false;

// Dynamic Cache for rendering topics list
const renderCache = {
    source_topics: {},
    finished_topics: {},
    queue: [],
    status: { topic_name: "" }
};

let renderTimeout = null;
function triggerCachedRender() {
    if (renderTimeout) return;
    renderTimeout = setTimeout(() => {
        renderQueue(renderCache);
        renderTimeout = null;
    }, 100);
}

// Input Fields
const elFbUrl = document.getElementById("fb-url");
const elFbRoot = document.getElementById("fb-root");
const elApiId = document.getElementById("api-id");
const elApiHash = document.getElementById("api-hash");
const elBotToken = document.getElementById("bot-token");
const elOwnerId = document.getElementById("owner-id");
const elSourceId = document.getElementById("source-group-id");
const elSourceType = document.getElementById("source-type");
const elTargetId = document.getElementById("target-group-id");
const elTargetType = document.getElementById("target-type");
const elKaggleUser = document.getElementById("kaggle-username");
const elKaggleKey = document.getElementById("kaggle-key");
const elKaggleSlug = document.getElementById("kaggle-slug");
const elKaggleWorkers = document.getElementById("kaggle-workers");
const elWorkersVal = document.getElementById("workers-val");
const elCaptionTemplate = document.getElementById("caption-template");
const elWordReplacements = document.getElementById("word-replacements");

// OTP Elements
const elLoginPhone = document.getElementById("login-phone");
const elBtnSendOtp = document.getElementById("btn-send-otp");
const elOtpWrapper = document.getElementById("login-otp-wrapper");
const elLoginOtp = document.getElementById("login-otp");
const elBtnVerifyOtp = document.getElementById("btn-verify-otp");
const el2FaWrapper = document.getElementById("login-2fa-wrapper");
const elLogin2Fa = document.getElementById("login-2fa");
const elSessionDisplay = document.getElementById("session-display");
const elSessionString = document.getElementById("session-string");

// Stats Elements
const elStatSpeed = document.getElementById("stat-speed");
const elStatDisk = document.getElementById("stat-disk");
const elStatDone = document.getElementById("stat-done");
const elStatVideos = document.getElementById("stat-videos");
const elStatUptime = document.getElementById("stat-uptime");
const elStatRestartTimer = document.getElementById("stat-restart-timer");
const elStatEta = document.getElementById("stat-eta");

// Queue Elements
const elQueueContainer = document.getElementById("topics-list-container");

// System Console Helper
function logToConsole(message, type = "system") {
    const timestamp = new Date().toLocaleTimeString();
    const logLine = document.createElement("div");
    logLine.className = `log-line ${type}`;
    logLine.innerText = `[${timestamp}] ${message}`;
    elConsole.appendChild(logLine);
    elConsole.scrollTop = elConsole.scrollHeight;
}

// Load bot instances list from LocalStorage
function loadBotInstances() {
    const saved = localStorage.getItem("bot_instances");
    if (saved) {
        botInstances = JSON.parse(saved);
        
        // Clean out default dummy placeholders from localStorage
        const dummyRoots = ["cloner_v5_mapping", "cloner_v7_mapping", "cloner_v8_mapping"];
        const dummyNames = ["Bot Instance 1 (v5)", "Bot Instance 2 (v6)", "Bot Instance 3 (v7)", "Bot Instance 4 (v8)", "Custom (0)"];
        botInstances = botInstances.filter(bot => {
            return !dummyNames.includes(bot.name) && !dummyRoots.includes(bot.root) && bot.root !== "cloner_v6_mapping" || bot.name === "AL!EN 2.0🖤HIMANSHU 🖤";
        });
        
        // If filtered list is empty, initialize with current active custom bot
        if (botInstances.length === 0) {
            const activeUrl = localStorage.getItem("fb_url") || elFbUrl.value.trim() || "https://secret-gpt-default-rtdb.asia-southeast1.firebasedatabase.app";
            const activeRoot = localStorage.getItem("fb_root") || elFbRoot.value.trim() || "cloner_v6_mapping";
            botInstances = [
                { name: "AL!EN 2.0🖤HIMANSHU 🖤", url: activeUrl, root: activeRoot }
            ];
        }
        localStorage.setItem("bot_instances", JSON.stringify(botInstances));
    } else {
        const activeUrl = localStorage.getItem("fb_url") || elFbUrl.value.trim() || "https://secret-gpt-default-rtdb.asia-southeast1.firebasedatabase.app";
        const activeRoot = localStorage.getItem("fb_root") || elFbRoot.value.trim() || "cloner_v6_mapping";
        botInstances = [
            { name: "AL!EN 2.0🖤HIMANSHU 🖤", url: activeUrl, root: activeRoot }
        ];
        localStorage.setItem("bot_instances", JSON.stringify(botInstances));
    }
    renderInstanceSelector();
}

// Render Instance Switcher Dropdown in UI
function renderInstanceSelector() {
    if (!elSelectInstance) return;
    elSelectInstance.innerHTML = "";
    botInstances.forEach((bot, index) => {
        const opt = document.createElement("option");
        opt.value = index;
        opt.innerText = bot.name;
        elSelectInstance.appendChild(opt);
    });
    
    // Select the option matching current active dbRoot
    const activeIndex = botInstances.findIndex(bot => bot.root === dbRoot);
    if (activeIndex > -1) {
        elSelectInstance.value = activeIndex;
    }
}

// Load Credentials from LocalStorage first (for easy UI recovery)
function loadLocalConfig() {
    loadBotInstances();
    const url = localStorage.getItem("fb_url");
    const root = localStorage.getItem("fb_root") || "cloner_v5_mapping";
    if (url) {
        elFbUrl.value = url;
        elFbRoot.value = root;
        initFirebase(url, root);
    }
}

// Initialize Firebase
function initFirebase(url, root) {
    try {
        const newRoot = root || "cloner_v5_mapping";
        
        // Turn off listeners on previous root before we switch dbRoot string!
        if (database && dbRoot && dbRoot !== newRoot) {
            try {
                database.ref(`${dbRoot}/config`).off();
                database.ref(`${dbRoot}/control/command`).off();
                database.ref(`${dbRoot}/status`).off();
                database.ref(`${dbRoot}/logs`).off();
                database.ref(`${dbRoot}/source_topics`).off();
                database.ref(`${dbRoot}/finished_topics`).off();
                database.ref(`${dbRoot}/queue`).off();
            } catch(e) {}
        }
        
        dbRoot = newRoot;
        const config = { databaseURL: url };
        
        // Initialize or recover existing app
        if (firebase.apps.length === 0) {
            firebase.initializeApp(config);
        } else {
            // Delete and re-init to allow URL changes
            firebase.app().delete().then(() => {
                firebase.initializeApp(config);
            });
        }
        
        database = firebase.database();
        localStorage.setItem("fb_url", url);
        localStorage.setItem("fb_root", dbRoot);
        
        // Sync Dropdown options with the active dbRoot
        if (elSelectInstance && botInstances.length > 0) {
            let activeIndex = botInstances.findIndex(bot => bot.root === dbRoot);
            if (activeIndex === -1) {
                // If the connected node is not in our bot list, add it as a Custom entry!
                const newBot = { name: `Custom (${dbRoot})`, url: url, root: dbRoot };
                botInstances.push(newBot);
                localStorage.setItem("bot_instances", JSON.stringify(botInstances));
                renderInstanceSelector();
                activeIndex = botInstances.length - 1;
            }
            elSelectInstance.value = activeIndex;
        }

        logToConsole("Firebase Connected Successfully!", "success");
        
        setupFirebaseListeners();
    } catch (e) {
        logToConsole(`Firebase Connection Failed: ${e.message}`, "error");
    }
}

loadLocalConfig();

// Setup Firebase RTDB Event Listeners
function setupFirebaseListeners() {
    if (!database) return;
    
    // Reset console UI and render cache to display fresh info for the selected bot
    elConsole.innerHTML = "";
    logToConsole(`Active Firebase root node: ${dbRoot}`, "system");
    renderCache.source_topics = {};
    renderCache.finished_topics = {};
    renderCache.queue = [];
    renderCache.status = { topic_name: "" };
    
    hasUnsavedQueueChanges = false;
    if (elSaveQueueBtn) {
        elSaveQueueBtn.style.display = "none";
    }
    
    // 1. Sync configuration inputs from Firebase (if they exist)
    database.ref(`${dbRoot}/config`).once("value", (snapshot) => {
        const val = snapshot.val();
        if (val) {
            if (val.telegram) {
                elApiId.value = val.telegram.api_id || "";
                elApiHash.value = val.telegram.api_hash || "";
                elBotToken.value = val.telegram.bot_token || "";
                elOwnerId.value = val.telegram.owner_chat_id || "";
                if (val.telegram.session_string) {
                    elSessionString.value = val.telegram.session_string;
                    elSessionDisplay.classList.remove("hidden");
                }
            }
            if (val.groups) {
                elSourceId.value = val.groups.source_group_id || "";
                elSourceType.value = val.groups.source_type || "group_topic";
                elTargetId.value = val.groups.target_group_id || "";
                elTargetType.value = val.groups.target_type || "group_topic";
            }
            if (val.kaggle) {
                elKaggleUser.value = val.kaggle.username || "";
                elKaggleKey.value = val.kaggle.key || "";
                elKaggleSlug.value = val.kaggle.slug || "";
                if (document.getElementById("kaggle-title")) {
                    document.getElementById("kaggle-title").value = val.kaggle.title || "";
                }
                if (val.kaggle.workers) {
                    elKaggleWorkers.value = val.kaggle.workers;
                    elWorkersVal.innerText = val.kaggle.workers;
                }
                elCaptionTemplate.value = val.kaggle.caption_template || "";
                elWordReplacements.value = val.kaggle.replacements || "";
            }
        }
    });

    database.ref(`${dbRoot}/control/command`).on("value", (snapshot) => {
        const cmd = snapshot.val() || "stop";
        isBotActive = (cmd === "start");

        // Lock/unlock UI elements based on active bot state
        const elScanBtn = document.getElementById("btn-scan-topics");
        const elMapBtn = document.getElementById("btn-create-topics");
        const elSaveBtn = document.getElementById("btn-save-telegram");
        const elSaveKaggleBtn = document.getElementById("btn-save-kaggle");
        
        if (isBotActive) {
            if (elScanBtn) elScanBtn.disabled = true;
            if (elMapBtn) elMapBtn.disabled = true;
            if (elSaveBtn) elSaveBtn.disabled = true;
            if (elSaveKaggleBtn) elSaveKaggleBtn.disabled = true;
        } else {
            if (elScanBtn) elScanBtn.disabled = false;
            if (elMapBtn) elMapBtn.disabled = false;
            if (elSaveBtn) elSaveBtn.disabled = false;
            if (elSaveKaggleBtn) elSaveKaggleBtn.disabled = false;
        }

        // Re-render the queue to update item draggable states
        if (typeof triggerCachedRender === "function") {
            triggerCachedRender();
        }

        // Highlight the correct control buttons
        document.getElementById("btn-control-start").classList.remove("active");
        document.getElementById("btn-control-pause").classList.remove("active");
        document.getElementById("btn-control-stop").classList.remove("active");

        if (cmd === "start") {
            document.getElementById("btn-control-start").classList.add("active");
        } else if (cmd === "pause") {
            document.getElementById("btn-control-pause").classList.add("active");
        } else if (cmd === "stop") {
            document.getElementById("btn-control-stop").classList.add("active");
        }
    });

    // 2. Monitor Engine Status & Stats
    database.ref(`${dbRoot}/status`).on("value", (snapshot) => {
        const stats = snapshot.val();
        if (!stats) return;

        // Heartbeat check for Kaggle
        const now = Date.now() / 1000;
        const hb = stats.last_heartbeat || 0;
        if (now - hb < 30) {
            elKaggleStatus.innerText = "ONLINE";
            elKaggleStatus.className = "status online";
        } else {
            elKaggleStatus.innerText = "OFFLINE";
            elKaggleStatus.className = "status offline";
        }

        // Live stats mapping
        elStatSpeed.innerHTML = `${(stats.speed_mbps || 0).toFixed(1)} <span>Mbps</span>`;
        elStatDisk.innerHTML = `${(stats.free_gb || 0).toFixed(1)} <span>GB</span>`;
        elStatVideos.innerText = stats.global_videos_done || 0;
        
        // Render dynamic slots
        const slotsContainer = document.getElementById("slots-container");
        if (slotsContainer) {
            slotsContainer.innerHTML = "";
            const slots = stats.slots || [];
            slots.forEach((slot, idx) => {
                const card = document.createElement("div");
                card.className = "active-status-card";
                
                const isIdle = (slot.current_action || "IDLE").toUpperCase() === "IDLE";
                if (isIdle) {
                    card.style.opacity = "0.45";
                    card.style.border = "1px dashed rgba(255, 255, 255, 0.1)";
                    card.style.background = "rgba(255, 255, 255, 0.01)";
                }
                
                card.innerHTML = `
                    <div class="status-header" style="display: flex; align-items: center; gap: 8px;">
                        <span class="badge" style="background: ${isIdle ? '#374151' : 'var(--primary)'}; font-size: 0.7rem; padding: 2px 6px; border-radius: 4px; color: #FFF; font-weight: 600;">${slot.current_action || 'IDLE'}</span>
                        <span class="filename" style="font-weight: 500; font-size: 0.8rem; color: var(--text-primary); text-overflow: ellipsis; overflow: hidden; white-space: nowrap; flex: 1;">[Slot ${idx+1}] ${slot.current_file || 'Idle'}</span>
                    </div>
                    <div class="status-body" style="margin-top: 6px;">
                        <div class="progress-bar-container" style="background: rgba(255,255,255,0.05); height: 6px; border-radius: 3px; overflow: hidden; position: relative;">
                            <div class="progress-bar" style="width: ${slot.file_progress || 0}%; background: var(--accent); height: 100%; transition: width 0.3s ease;"></div>
                        </div>
                        <div class="status-meta" style="display: flex; justify-content: space-between; font-size: 0.75rem; color: var(--text-secondary); margin-top: 4px;">
                            <span>${slot.current_size || '0.0 MB'}</span>
                            <span>${slot.file_progress || 0}%</span>
                        </div>
                    </div>
                `;
                slotsContainer.appendChild(card);
            });
        }

        // Uptime & Auto-Restart timers
        elStatUptime.innerText = stats.uptime || "00:00:00";
        elStatRestartTimer.innerText = stats.restart_timer || "00:00";
        elStatEta.innerText = stats.eta || "Calculating...";

        // Total counters
        const doneTopics = stats.global_topics_done || 0;
        const totalTopics = stats.global_topics_total || 0;
        elStatDone.innerText = `${doneTopics} / ${totalTopics}`;
        
        // Render orchestrator active agent status
        const elOrchestratorStatus = document.getElementById("orchestrator-status");
        if (elOrchestratorStatus) {
            const orch = stats.orchestrator;
            if (orch && orch.last_check) {
                const nowSec = Date.now() / 1000;
                const diffSec = nowSec - orch.last_check;
                
                if (diffSec < 900) { // Active within 15 minutes
                    elOrchestratorStatus.style.background = "rgba(16, 185, 129, 0.15)";
                    elOrchestratorStatus.style.border = "1px solid rgba(16, 185, 129, 0.3)";
                    elOrchestratorStatus.style.color = "#34d399";
                    
                    if (orch.type === "github_actions") {
                        const mins = Math.max(0, Math.round(diffSec / 60));
                        elOrchestratorStatus.innerText = `🛰 CLOUD ACTIONS (Checked ${mins}m ago)`;
                    } else if (orch.type === "cloud_server" || orch.type === "railway") {
                        const secs = Math.max(0, Math.round(diffSec));
                        elOrchestratorStatus.innerText = `💻 CLOUD SERVER (Checked ${secs}s ago)`;
                    } else {
                        const secs = Math.max(0, Math.round(diffSec));
                        elOrchestratorStatus.innerText = `💻 PC SERVER (Checked ${secs}s ago)`;
                    }
                } else { // Offline/Stale
                    elOrchestratorStatus.style.background = "rgba(239, 68, 68, 0.15)";
                    elOrchestratorStatus.style.border = "1px solid rgba(239, 68, 68, 0.3)";
                    elOrchestratorStatus.style.color = "#f87171";
                    const hours = Math.round(diffSec / 3600);
                    elOrchestratorStatus.innerText = `❌ OFFLINE (Last check ${hours}h ago)`;
                }
            } else {
                elOrchestratorStatus.style.background = "rgba(239, 68, 68, 0.15)";
                elOrchestratorStatus.style.border = "1px solid rgba(239, 68, 68, 0.3)";
                elOrchestratorStatus.style.color = "#f87171";
                elOrchestratorStatus.innerText = "❌ NOT ACTIVE";
            }
        }
        
        // Sync status to renderCache and trigger queue render
        renderCache.status = stats;
        triggerCachedRender();
    });

    // 3. Monitor live logs path
    database.ref(`${dbRoot}/logs`).limitToLast(5).on("child_added", (snapshot) => {
        const log = snapshot.val();
        if (log) {
            let type = "system";
            if (log.toLowerCase().includes("fail") || log.toLowerCase().includes("error")) type = "error";
            else if (log.toLowerCase().includes("done") || log.toLowerCase().includes("complete")) type = "success";
            else if (log.toLowerCase().includes("wait") || log.toLowerCase().includes("retry")) type = "warn";
            logToConsole(log, type);
        }
    });

    // 4. Listen to subkeys separately to avoid lag
    database.ref(`${dbRoot}/source_topics`).on("value", (snapshot) => {
        renderCache.source_topics = snapshot.val() || {};
        triggerCachedRender();
    });

    database.ref(`${dbRoot}/finished_topics`).on("value", (snapshot) => {
        renderCache.finished_topics = snapshot.val() || {};
        triggerCachedRender();
    });

    database.ref(`${dbRoot}/queue`).on("value", (snapshot) => {
        if (hasUnsavedQueueChanges) return; // Do NOT overwrite if user has unsaved edits!
        renderCache.queue = snapshot.val() || [];
        triggerCachedRender();
    });

}

// // Save All Configurations (Combined Firebase, Telegram, Groups, Kaggle)
document.getElementById("btn-save-all-config").addEventListener("click", () => {
    const url = elFbUrl.value.trim();
    const root = elFbRoot.value.trim();
    if (!url) {
        alert("Please enter a Firebase Database URL!");
        return;
    }
    
    const isNewConnection = !database || dbRoot !== root || localStorage.getItem("fb_url") !== url;
    if (isNewConnection) {
        initFirebase(url, root);
    }
    
    // Wait for connection if new, otherwise execute immediately
    const delay = isNewConnection ? 1000 : 0;
    setTimeout(() => {
        if (!database) {
            logToConsole("Firebase Connection not ready yet. Please try again.", "error");
            return;
        }
        const config = {
            telegram: {
                api_id: parseInt(elApiId.value) || 0,
                api_hash: elApiHash.value.trim(),
                session_string: elSessionString.value.trim(),
                bot_token: elBotToken.value.trim(),
                owner_chat_id: parseInt(elOwnerId.value) || 0
            },
            groups: {
                source_group_id: parseInt(elSourceId.value) || 0,
                source_type: elSourceType.value,
                target_group_id: parseInt(elTargetId.value) || 0,
                target_type: elTargetType.value
            },
            kaggle: {
                username: elKaggleUser.value.trim(),
                key: elKaggleKey.value.trim(),
                title: document.getElementById("kaggle-title").value.trim(),
                slug: elKaggleSlug.value.trim(),
                workers: parseInt(elKaggleWorkers.value) || 3,
                caption_template: elCaptionTemplate.value,
                replacements: elWordReplacements.value
            }
        };
        
        Promise.all([
            database.ref(`${dbRoot}/config/telegram`).set(config.telegram),
            database.ref(`${dbRoot}/config/groups`).set(config.groups),
            database.ref(`${dbRoot}/config/kaggle`).set(config.kaggle)
        ])
        .then(() => logToConsole("All configuration parameters successfully saved to Firebase under active node!", "success"))
        .catch(err => logToConsole(`Error saving configurations: ${err.message}`, "error"));
    }, delay);
});

// Auto slugify title to slug field
document.getElementById("kaggle-title").addEventListener("input", (e) => {
    const title = e.target.value;
    const slug = title
        .toLowerCase()
        .replace(/[^a-z0-9\s-]/g, '') // remove invalid chars
        .replace(/\s+/g, '-')         // replace spaces with hyphens
        .replace(/-+/g, '-')          // collapse duplicate hyphens
        .trim();
    elKaggleSlug.value = slug;
});



// Queue Rendering & Management
function renderQueue(rootData) {
    if (!rootData) return;
    const sourceTopics = rootData.source_topics || {};
    const finishedTopics = rootData.finished_topics || {};
    const queue = rootData.queue || [];
    const status = rootData.status || {};
    
    // Clear container
    elQueueContainer.innerHTML = "";
    
    // If empty
    if (Object.keys(sourceTopics).length === 0) {
        elQueueContainer.innerHTML = '<div class="placeholder-text">Scan source to discover topics / channels.</div>';
        return;
    }

    // Determine current processing topic from status
    const currentTopicName = status.topic_name || "";

    // If queue is empty or has mismatched length, we build/sync it
    const topicKeys = Object.keys(sourceTopics);
    let renderList = [];

    if (queue.length === 0) {
        // Initial setup of queue
        renderList = topicKeys;
        database.ref(`${dbRoot}/queue`).set(renderList);
    } else {
        renderList = queue;
    }

    // Stable sort based on status: Done first, then Active, then Pending (preserving original order)
    const originalOrder = {};
    renderList.forEach((id, index) => {
        originalOrder[id] = index;
    });

    renderList.sort((a, b) => {
        const isDoneA = finishedTopics[a] === true;
        const isDoneB = finishedTopics[b] === true;
        if (isDoneA && !isDoneB) return -1;
        if (!isDoneA && isDoneB) return 1;
        
        const isActiveA = !isDoneA && (sourceTopics[a] === currentTopicName || (sourceTopics[a] && typeof sourceTopics[a] === 'object' && sourceTopics[a].name === currentTopicName));
        const isActiveB = !isDoneB && (sourceTopics[b] === currentTopicName || (sourceTopics[b] && typeof sourceTopics[b] === 'object' && sourceTopics[b].name === currentTopicName));
        if (isActiveA && !isActiveB) return -1;
        if (!isActiveA && isActiveB) return 1;
        
        return originalOrder[a] - originalOrder[b];
    });

    renderList.forEach((id) => {
        const topic = sourceTopics[id];
        if (!topic) return; // In case topic was deleted

        const isDone = finishedTopics[id] === true;
        const isActive = !isDone && (topic === currentTopicName || (typeof topic === 'object' && topic.name === currentTopicName));

        let name = "Unknown Topic";
        let videos = 0;
        let pdfs = 0;
        let sizeText = "0.0 MB";

        if (typeof topic === "object") {
            name = topic.name || name;
            videos = topic.videos || 0;
            pdfs = topic.pdfs || 0;
            const sizeMb = topic.size_mb || 0;
            sizeText = sizeMb > 1024 ? `${(sizeMb/1024).toFixed(2)} GB` : `${sizeMb.toFixed(0)} MB`;
        } else {
            name = topic; // old schema compatibility
        }

        let statusClass = "pending";
        let statusText = "Pending";
        if (isDone) {
            statusClass = "done";
            statusText = "Done";
        } else if (isActive) {
            statusClass = "active";
            
            // Find active topic ID by matching name
            const activeTopicId = Object.keys(sourceTopics).find(key => {
                const t = sourceTopics[key];
                return t === currentTopicName || (t && typeof t === 'object' && t.name === currentTopicName);
            });
            
            let totalVal = status.topic_total || 0;
            
            // Fallback to total metadata files if topic_total is 0
            if (totalVal === 0 && activeTopicId && sourceTopics[activeTopicId] && typeof sourceTopics[activeTopicId] === 'object') {
                totalVal = (sourceTopics[activeTopicId].videos || 0) + (sourceTopics[activeTopicId].pdfs || 0);
            }
            
            let doneVal = 0;
            if (activeTopicId) {
                // Sum files in all other completed topics
                let completedOtherSum = 0;
                Object.keys(finishedTopics).forEach(key => {
                    if (finishedTopics[key] === true && key !== activeTopicId) {
                        const t = sourceTopics[key];
                        if (t && typeof t === 'object') {
                            completedOtherSum += (t.videos || 0) + (t.pdfs || 0);
                        }
                    }
                });
                
                // Subtract other completed topics' files from global completed files
                doneVal = Math.max(0, (status.global_videos_done || 0) - completedOtherSum);
                if (totalVal > 0 && doneVal > totalVal) {
                    doneVal = totalVal;
                }
            }
            
            statusText = `Cloning (${doneVal} / ${totalVal})`;
        }

        const canDrag = !isBotActive && !isDone && !isActive;

        let deleteBtn = "";
        if (isDone) {
            deleteBtn = `
                <div style="display: flex; align-items: center; gap: 8px; margin-right: 4px;">
                    <span style="font-size: 0.8rem; color: var(--success); font-weight: 600;">✓</span>
                    <button class="btn-reset-topic" title="Reset to Pending (Re-run)" onclick="resetTopicStatus('${id}')" style="background: rgba(245, 158, 11, 0.15); border: 1px solid rgba(245, 158, 11, 0.3); color: var(--warn); border-radius: 4px; padding: 2px 6px; font-size: 0.7rem; cursor: pointer; transition: all 0.2s;">Reset</button>
                </div>
            `;
        } else if (isActive) {
            // Active cloning topic cannot be deleted
            deleteBtn = `<button class="btn-delete" title="Cannot delete active topic" onclick="alert('Cannot delete the currently cloning topic!')" style="opacity: 0.3; cursor: not-allowed;">✕</button>`;
        } else if (isBotActive) {
            // Deleting blocked while bot is running
            deleteBtn = `<button class="btn-delete" title="Pause bot to edit" onclick="alert('Please pause the cloner bot before editing or deleting topics!')" style="opacity: 0.3; cursor: not-allowed;">✕</button>`;
        } else {
            // Normal delete button
            deleteBtn = `<button class="btn-delete" title="Remove from queue" onclick="deleteQueueItem('${id}')">✕</button>`;
        }

        const dragHandleStyle = canDrag 
            ? `cursor: grab; opacity: 0.75;` 
            : `cursor: not-allowed; opacity: 0.25;`;

        const itemHtml = `
            <div class="queue-item" data-id="${id}" draggable="${canDrag ? 'true' : 'false'}" style="${canDrag ? '' : 'border-color: rgba(255,255,255,0.05); background: rgba(0,0,0,0.1);'}">
                <div class="item-left">
                    <span class="drag-handle" style="${dragHandleStyle}">☰</span>
                    <div class="item-info">
                        <span class="item-title" title="${name}">${name}</span>
                        <div class="item-stats">
                            <span>Videos: <span>${videos}</span></span>
                            <span>PDFs: <span>${pdfs}</span></span>
                            <span>Size: <span>${sizeText}</span></span>
                        </div>
                    </div>
                </div>
                <div class="item-right">
                    <span class="status-badge ${statusClass}">${statusText}</span>
                    ${deleteBtn}
                </div>
            </div>
        `;
        elQueueContainer.insertAdjacentHTML("beforeend", itemHtml);
    });

    setupDragAndDrop();
}

// Delete Item from Queue
window.deleteQueueItem = function(id) {
    if (!database) return;
    database.ref(`${dbRoot}/queue`).get().then((snap) => {
        const currentQueue = snap.val() || [];
        const index = currentQueue.indexOf(id);
        if (index > -1) {
            currentQueue.splice(index, 1);
            database.ref(`${dbRoot}/queue`).set(currentQueue);
            logToConsole(`Topic ID ${id} removed from the active queue.`, "warn");
        }
    });
};

// Reset Done Topic status to Pending
window.resetTopicStatus = function(id) {
    if (!database) return;
    if (confirm("Are you sure you want to reset this topic to Pending? The bot will scan and clone any missing files on the next run.")) {
        database.ref(`${dbRoot}/finished_topics/${id}`).remove()
            .then(() => logToConsole(`Topic ID ${id} reset to Pending successfully.`, "info"))
            .catch(err => logToConsole(`Error resetting topic: ${err.message}`, "error"));
    }
};

// Drag and Drop caching variables to prevent layout thrashing and lag
let cachedLastLocked = null;
let cachedLockedElements = [];
let cachedDraggables = [];

// Drag and Drop implementation
function setupDragAndDrop() {
    const items = elQueueContainer.querySelectorAll(".queue-item");
    items.forEach(item => {
        item.addEventListener("dragstart", () => {
            item.classList.add("dragging");
            
            // Cache locked elements on drag start (Done or Active status)
            const lockedItems = [...elQueueContainer.querySelectorAll(".queue-item")].filter(item => {
                const badge = item.querySelector(".status-badge");
                return badge && (badge.classList.contains("done") || badge.classList.contains("active"));
            });
            cachedLockedElements = lockedItems;
            cachedLastLocked = lockedItems[lockedItems.length - 1];
            
            // Cache other draggable items (excluding the dragging one)
            cachedDraggables = [...elQueueContainer.querySelectorAll(".queue-item:not(.dragging)")];
        });
        
        item.addEventListener("dragend", () => {
            item.classList.remove("dragging");
            cachedLockedElements = [];
            cachedLastLocked = null;
            cachedDraggables = [];
            
            // Instead of saving immediately, mark as unsaved and show the save order button
            hasUnsavedQueueChanges = true;
            if (elSaveQueueBtn) {
                elSaveQueueBtn.style.display = "inline-block";
            }
        });
    });

    elQueueContainer.addEventListener("dragover", e => {
        e.preventDefault();
        const dragging = elQueueContainer.querySelector(".dragging");
        if (!dragging) return;

        // Find element we are dragging after using cached positions
        const afterElement = getCachedDragAfterElement(e.clientY);

        if (afterElement) {
            const isAfterElementLocked = cachedLockedElements.includes(afterElement);
            if (isAfterElementLocked) {
                // Prevent dropping above locked items; place it right after the last locked element
                if (cachedLastLocked && cachedLastLocked.nextSibling) {
                    elQueueContainer.insertBefore(dragging, cachedLastLocked.nextSibling);
                } else {
                    elQueueContainer.appendChild(dragging);
                }
            } else {
                // Normal insert before a pending item
                elQueueContainer.insertBefore(dragging, afterElement);
            }
        } else {
            elQueueContainer.appendChild(dragging);
        }
    });
}

function getCachedDragAfterElement(y) {
    return cachedDraggables.reduce((closest, child) => {
        const box = child.getBoundingClientRect();
        const offset = y - box.top - box.height / 2;
        if (offset < 0 && offset > closest.offset) {
            return { offset: offset, element: child };
        } else {
            return closest;
        }
    }, { offset: Number.NEGATIVE_INFINITY }).element;
}

function saveNewQueueOrder() {
    if (!database) return;
    const items = [...elQueueContainer.querySelectorAll(".queue-item")];
    const newOrder = items.map(item => item.getAttribute("data-id"));
    database.ref(`${dbRoot}/queue`).set(newOrder)
        .then(() => logToConsole("Queue order updated successfully", "success"))
        .catch(err => logToConsole(`Error saving queue order: ${err.message}`, "error"));
}

// Scan Source Button trigger
document.getElementById("btn-scan-topics").addEventListener("click", () => {
    if (!database) {
        alert("Please connect Firebase first!");
        return;
    }
    database.ref(`${dbRoot}/control/trigger_scan`).set(true)
        .then(() => logToConsole("Triggered source scanning... Check terminal log.", "info"))
        .catch(err => logToConsole(`Error triggering scan: ${err.message}`, "error"));
});

// Auto-Map Topics Button trigger
document.getElementById("btn-create-topics").addEventListener("click", () => {
    if (!database) {
        alert("Please connect Firebase first!");
        return;
    }
    database.ref(`${dbRoot}/control/trigger_map`).set(true)
        .then(() => logToConsole("Triggered topic mapping and auto creation in target group...", "info"))
        .catch(err => logToConsole(`Error triggering topic map: ${err.message}`, "error"));
});

// Engine Control Commands
document.getElementById("btn-control-start").addEventListener("click", () => {
    if (!database) return;
    database.ref(`${dbRoot}/control/command`).set("start")
        .then(() => logToConsole("Command sent: START CLONING", "success"));
});

document.getElementById("btn-control-pause").addEventListener("click", () => {
    if (!database) return;
    database.ref(`${dbRoot}/control/command`).set("pause")
        .then(() => logToConsole("Command sent: PAUSE CLONING", "warn"));
});

document.getElementById("btn-control-stop").addEventListener("click", () => {
    if (!database) return;
    if (confirm("Are you sure you want to stop the engine? This will pause cloning completely.")) {
        database.ref(`${dbRoot}/control/command`).set("stop")
            .then(() => logToConsole("Command sent: STOP ENGINE", "error"));
    }
});

// Clear console log UI
document.getElementById("btn-clear-console").addEventListener("click", () => {
    elConsole.innerHTML = "";
    logToConsole("Terminal clear.", "system");
});

// ── LOCAL SERVER ACTIONS ──

// Check Local Server Health
function checkLocalServerHealth() {
    fetch(`${localServerUrl}/api/health`)
        .then(res => res.json())
        .then(data => {
            if (data.status === "ok" && elLocalStatus) {
                elLocalStatus.innerText = "ONLINE";
                elLocalStatus.className = "status online";
            }
        })
        .catch(() => {
            if (elLocalStatus) {
                elLocalStatus.innerText = "OFFLINE";
                elLocalStatus.className = "status offline";
            }
        });
}
setInterval(checkLocalServerHealth, 5000);
checkLocalServerHealth();

// Telegram Send OTP
elBtnSendOtp.addEventListener("click", () => {
    const phone = elLoginPhone.value.trim();
    const apiId = parseInt(elApiId.value);
    const apiHash = elApiHash.value.trim();

    if (!phone || isNaN(apiId) || !apiHash) {
        alert("Please enter Phone, API ID, and API Hash in configuration!");
        return;
    }

    elBtnSendOtp.innerText = "Sending...";
    elBtnSendOtp.disabled = true;

    fetch(`${localServerUrl}/api/telegram/send_code`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ phone, api_id: apiId, api_hash: apiHash })
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            logToConsole("OTP requested. Please check Telegram.", "info");
            elOtpWrapper.classList.remove("hidden");
            if (el2FaWrapper) {
                el2FaWrapper.classList.add("hidden");
                elLogin2Fa.value = "";
            }
        } else {
            logToConsole(`OTP request failed: ${data.error}`, "error");
            elBtnSendOtp.innerText = "Send OTP";
            elBtnSendOtp.disabled = false;
        }
    })
    .catch(err => {
        logToConsole(`Connection failed: ${err.message}`, "error");
        elBtnSendOtp.innerText = "Send OTP";
        elBtnSendOtp.disabled = false;
    });
});

// Telegram Verify OTP
elBtnVerifyOtp.addEventListener("click", () => {
    const code = elLoginOtp.value.trim();
    if (!code) {
        alert("Please enter OTP!");
        return;
    }

    const payload = { code };
    if (el2FaWrapper && !el2FaWrapper.classList.contains("hidden")) {
        payload.password = elLogin2Fa.value.trim();
        if (!payload.password) {
            alert("Two-step verification is enabled. Please enter your 2FA password!");
            return;
        }
    }

    elBtnVerifyOtp.innerText = "Verifying...";
    elBtnVerifyOtp.disabled = true;

    fetch(`${localServerUrl}/api/telegram/verify_code`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
    })
    .then(res => res.json())
    .then(data => {
        if (data.success && data.session_string) {
            logToConsole("Login Successful!", "success");
            elSessionString.value = data.session_string;
            elSessionDisplay.classList.remove("hidden");
            
            if (el2FaWrapper) {
                el2FaWrapper.classList.add("hidden");
                elLogin2Fa.value = "";
            }
            
            // Reset buttons state
            elBtnSendOtp.innerText = "Send OTP";
            elBtnSendOtp.disabled = false;
            elBtnVerifyOtp.innerText = "Verify & Login";
            elBtnVerifyOtp.disabled = false;
            
            // Automatically update config in Firebase with the new Session String
            if (database) {
                database.ref(`${dbRoot}/config/telegram/session_string`).set(data.session_string)
                    .then(() => logToConsole("Session string automatically updated in Firebase DB!", "success"));
            }
        } else if (data.requires_password) {
            logToConsole("Two-step verification is enabled. Please enter your 2FA password and click Verify & Login again.", "warn");
            if (el2FaWrapper) {
                el2FaWrapper.classList.remove("hidden");
            }
            elBtnVerifyOtp.innerText = "Verify & Login";
            elBtnVerifyOtp.disabled = false;
        } else {
            logToConsole(`OTP Verification failed: ${data.error}`, "error");
            elBtnVerifyOtp.innerText = "Verify & Login";
            elBtnVerifyOtp.disabled = false;
        }
    })
    .catch(err => {
        logToConsole(`Connection failed: ${err.message}`, "error");
        elBtnVerifyOtp.innerText = "Verify & Login";
        elBtnVerifyOtp.disabled = false;
    });
});

// Update slider text in UI
if (elKaggleWorkers && elWorkersVal) {
    elKaggleWorkers.addEventListener("input", (e) => {
        elWorkersVal.innerText = e.target.value;
    });
}

// Dropdown Bot Instance Switcher Listener
if (elSelectInstance) {
    elSelectInstance.addEventListener("change", (e) => {
        const index = parseInt(e.target.value);
        const bot = botInstances[index];
        if (bot) {
            localStorage.setItem("fb_url", bot.url);
            localStorage.setItem("fb_root", bot.root);
            window.location.reload();
        }
    });
}

// Add Bot Button Listener
const elBtnAddBot = document.getElementById("btn-add-bot");
if (elBtnAddBot) {
    elBtnAddBot.addEventListener("click", () => {
        const name = prompt("Enter Bot Label/Name (e.g. Bot 5):");
        if (!name) return;
        const root = prompt("Enter Firebase Root Node (e.g. cloner_v7_mapping):");
        if (!root) return;
        const url = prompt("Enter Firebase Database URL:", elFbUrl.value.trim());
        if (!url) return;
        
        const newBot = { name, url, root };
        botInstances.push(newBot);
        localStorage.setItem("bot_instances", JSON.stringify(botInstances));
        
        renderInstanceSelector();
        
        elFbUrl.value = url;
        elFbRoot.value = root;
        initFirebase(url, root);
        
        logToConsole(`Added new bot instance: ${name}`, "success");
    });
}

// Remove Bot Button Listener
const elBtnRemoveBot = document.getElementById("btn-remove-bot");
if (elBtnRemoveBot) {
    elBtnRemoveBot.addEventListener("click", () => {
        if (botInstances.length <= 1) {
            alert("You must have at least one bot instance configured!");
            return;
        }
        const activeIndex = parseInt(elSelectInstance.value);
        const bot = botInstances[activeIndex];
        if (confirm(`Are you sure you want to remove the bot instance '${bot.name}'?`)) {
            botInstances.splice(activeIndex, 1);
            localStorage.setItem("bot_instances", JSON.stringify(botInstances));
            
            renderInstanceSelector();
            
            const firstBot = botInstances[0];
            elFbUrl.value = firstBot.url;
            elFbRoot.value = firstBot.root;
            initFirebase(firstBot.url, firstBot.root);
            
            logToConsole(`Deleted bot instance: ${bot.name}`, "warn");
        }
    });
}

// Save Queue Order Button Listener
if (elSaveQueueBtn) {
    elSaveQueueBtn.addEventListener("click", () => {
        saveNewQueueOrder();
        hasUnsavedQueueChanges = false;
        elSaveQueueBtn.style.display = "none";
    });
}


