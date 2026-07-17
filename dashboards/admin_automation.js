// admin_automation.js - Multi-Teacher Cloner dashboard script

let db = null;
let currentConfig = {};

const localServerUrl = window.location.protocol === "file:"
    ? "https://restartrepo-production.up.railway.app"
    : window.location.origin;

// 1. Initialize Firebase connection
function initFirebase(dbUrl) {
    if (!dbUrl) return;
    
    // Clean URL
    const cleanUrl = dbUrl.trim().replace(/\/+$/, "");
    
    try {
        if (typeof firebase === 'undefined') {
            console.warn("Firebase SDK is not loaded yet. Retrying in 500ms...");
            setTimeout(() => initFirebase(dbUrl), 500);
            return;
        }
        
        const config = { databaseURL: cleanUrl };
        
        if (firebase.apps.length === 0) {
            firebase.initializeApp(config);
            db = firebase.database();
            console.log("Firebase initialized successfully with URL:", cleanUrl);
            loadCatalog();
            loadConfig();
            setupStatusListener();
        } else {
            firebase.app().delete().then(() => {
                firebase.initializeApp(config);
                db = firebase.database();
                console.log("Firebase re-initialized with URL:", cleanUrl);
                loadCatalog();
                loadConfig();
                setupStatusListener();
            }).catch(e => {
                console.error("Firebase app deletion failed:", e);
                // Fallback direct init
                firebase.initializeApp(config);
                db = firebase.database();
                loadCatalog();
                loadConfig();
                setupStatusListener();
            });
        }
    } catch (e) {
        console.error("Firebase init failed:", e);
        alert("Firebase Connection failed. Check Console or URL.");
    }
}

// Helper to strip trailing slashes
String.prototype.rstrip = function (char) {
    if (this.endsWith(char)) {
        return this.substring(0, this.length - char.length);
    }
    return this;
};

// 2. Load Catalog to populate Course Selector
function loadCatalog() {
    if (!db) return;
    
    db.ref("new_automation_courses/catalog").once("value", (snapshot) => {
        const catalog = snapshot.val();
        const selector = document.getElementById("active-course-key");
        
        // Reset and keep the 'all' option
        selector.innerHTML = '<option value="all">🚀 ALL COURSES (Sequential Queue Mode)</option>';
        
        if (catalog && Array.isArray(catalog)) {
            catalog.forEach(item => {
                const key = item.local_file.replace(".json", "").replace(".", "_");
                const option = document.createElement("option");
                option.value = key;
                option.textContent = `📚 ${item.title} (${item.lecture_count} lectures)`;
                selector.appendChild(option);
            });
            
            // Set selected course option once catalog is ready
            if (currentConfig.active_course_key) {
                selector.value = currentConfig.active_course_key;
            }
        }
    });
}

// 3. Load dynamic configurations
function loadConfig() {
    if (!db) return;
    
    db.ref("new_automation_courses/config").once("value", (snapshot) => {
        const config = snapshot.val() || {};
        currentConfig = config;
        
        // Populate inputs
        document.getElementById("api-id").value = config.api_id || "";
        document.getElementById("api-hash").value = config.api_hash || "";
        document.getElementById("bot-token").value = config.bot_token || "";
        document.getElementById("owner-id").value = config.owner_chat_id || "";
        document.getElementById("extracted-by").value = config.extracted_by || "@cryvex4";
        
        document.getElementById("kaggle-username").value = config.kaggle_username || "";
        document.getElementById("kaggle-key").value = config.kaggle_key || "";
        document.getElementById("kaggle-slug").value = config.kaggle_slug || "new-automation-cloner";
        
        if (config.active_course_key) {
            document.getElementById("active-course-key").value = config.active_course_key;
        }
    });
}

// 4. Setup Live Status Listener
function setupStatusListener() {
    if (!db) return;
    
    db.ref("new_automation_courses/status").on("value", (snapshot) => {
        const status = snapshot.val();
        const indicator = document.getElementById("active-clone-indicator");
        
        if (status) {
            // Update stats
            document.getElementById("stat-action").textContent = status.action || "Idle";
            document.getElementById("stat-key").textContent = status.active_key || "N/A";
            document.getElementById("stat-progress").textContent = `${status.done_count || 0} / ${status.total_files || 0}`;
            document.getElementById("stat-speed").textContent = status.speed || "0 Mbps";
            document.getElementById("stat-disk").textContent = status.disk_free || "0 GB";
            
            const progressPct = parseFloat(status.progress || 0).toFixed(1);
            document.getElementById("stat-percent").textContent = `${progressPct}%`;
            
            // Update engine status indicator
            if (status.action && status.action !== "Idle" && !status.action.includes("Completed")) {
                indicator.textContent = "RUNNING";
                indicator.style.color = "#10b981";
                indicator.style.background = "rgba(16, 185, 129, 0.1)";
                indicator.style.border = "1px solid rgba(16, 185, 129, 0.2)";
                document.getElementById("kaggle-engine-status").className = "status online";
                document.getElementById("kaggle-engine-status").textContent = "RUNNING";
            } else {
                indicator.textContent = "IDLE";
                indicator.style.color = "#9ca3af";
                indicator.style.background = "rgba(255,255,255,0.05)";
                indicator.style.border = "1px solid rgba(255,255,255,0.08)";
                document.getElementById("kaggle-engine-status").className = "status offline";
                document.getElementById("kaggle-engine-status").textContent = "IDLE";
            }
        }
    });
}

// 5. Save Configuration to Firebase
document.getElementById("btn-save-config").addEventListener("click", () => {
    if (!db) {
        alert("Firebase is not initialized yet. Check Database URL.");
        return;
    }
    
    const configPayload = {
        api_id: parseInt(document.getElementById("api-id").value) || null,
        api_hash: document.getElementById("api-hash").value.trim(),
        bot_token: document.getElementById("bot-token").value.trim(),
        owner_chat_id: parseInt(document.getElementById("owner-id").value) || null,
        extracted_by: document.getElementById("extracted-by").value.trim(),
        kaggle_username: document.getElementById("kaggle-username").value.trim(),
        kaggle_key: document.getElementById("kaggle-key").value.trim(),
        kaggle_slug: document.getElementById("kaggle-slug").value.trim(),
        active_course_key: document.getElementById("active-course-key").value,
        session_string: currentConfig.session_string || "", // Keep existing session if not re-generated
        server_url: window.location.origin // Pass Railway server URL for Auto-Restart
    };
    
    db.ref("new_automation_courses/config").set(configPayload, (err) => {
        if (err) {
            alert("Failed to save configuration: " + err);
        } else {
            alert("✅ Configuration successfully saved & synced to Firebase Realtime DB!");
            loadConfig(); // Refresh
        }
    });
});

// 6. Telegram Login Flow (Send OTP Code)
document.getElementById("btn-send-otp").addEventListener("click", () => {
    const phone = document.getElementById("phone-number").value.trim();
    const apiId = parseInt(document.getElementById("api-id").value);
    const apiHash = document.getElementById("api-hash").value.trim();
    
    if (!phone || !apiId || !apiHash) {
        alert("Please enter API ID, API Hash, and Phone Number first.");
        return;
    }
    
    const btn = document.getElementById("btn-send-otp");
    btn.disabled = true;
    btn.textContent = "Sending...";
    
    fetch(localServerUrl + "/api/telegram/send_code", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ phone, api_id: apiId, api_hash: apiHash })
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            btn.textContent = "OTP Sent!";
            btn.style.color = "#10b981";
            
            // Enable verify fields
            document.getElementById("otp-code").disabled = false;
            document.getElementById("twofa-password").disabled = false;
            document.getElementById("btn-verify-otp").disabled = false;
            
            alert("📩 OTP code sent successfully! Check your Telegram messages.");
        } else {
            btn.disabled = false;
            btn.textContent = "Send OTP Code";
            alert("Error sending OTP: " + data.error);
        }
    })
    .catch(err => {
        btn.disabled = false;
        btn.textContent = "Send OTP Code";
        alert("Request failed: " + err);
    });
});

// 7. Telegram Login Flow (Verify OTP Code)
document.getElementById("btn-verify-otp").addEventListener("click", () => {
    const code = document.getElementById("otp-code").value.trim();
    const password = document.getElementById("twofa-password").value.trim();
    
    if (!code) {
        alert("Please enter the verification code.");
        return;
    }
    
    const btn = document.getElementById("btn-verify-otp");
    btn.disabled = true;
    btn.textContent = "Verifying...";
    
    fetch(localServerUrl + "/api/telegram/verify_code", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code, password })
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            btn.textContent = "Verified!";
            
            // Save Session String directly in Firebase config
            if (db) {
                db.ref("new_automation_courses/config/session_string").set(data.session_string, (err) => {
                    if (err) {
                        alert("Session generated successfully, but failed to write to Firebase: " + err);
                    } else {
                        alert("🎉 Successfully logged in! Telethon Session String has been generated and saved directly to Firebase.");
                        // Clean login UI
                        document.getElementById("phone-number").value = "";
                        document.getElementById("otp-code").value = "";
                        document.getElementById("otp-code").disabled = true;
                        document.getElementById("twofa-password").value = "";
                        document.getElementById("twofa-password").disabled = true;
                        document.getElementById("btn-verify-otp").disabled = true;
                        document.getElementById("btn-send-otp").disabled = false;
                        document.getElementById("btn-send-otp").textContent = "Send OTP Code";
                        document.getElementById("btn-send-otp").style.color = "var(--accent)";
                        loadConfig(); // Refresh session string state
                    }
                });
            } else {
                alert("Session string: " + data.session_string + "\n(Warning: Firebase is not initialized, save this string manually!)");
            }
        } else if (data.requires_password) {
            btn.disabled = false;
            btn.textContent = "Login & Generate";
            alert("🔑 Two-Factor authentication is enabled. Please enter your 2FA password in the input field.");
        } else {
            btn.disabled = false;
            btn.textContent = "Login & Generate";
            alert("Verification failed: " + data.error);
        }
    })
    .catch(err => {
        btn.disabled = false;
        btn.textContent = "Login & Generate";
        alert("Verification request failed: " + err);
    });
});

// 8. Launch cloner bot on Kaggle
document.getElementById("btn-trigger-cloner").addEventListener("click", () => {
    const username = document.getElementById("kaggle-username").value.trim();
    const key = document.getElementById("kaggle-key").value.trim();
    const slug = document.getElementById("kaggle-slug").value.trim();
    
    if (!username || !key || !slug) {
        alert("Please configure Kaggle settings (Username, API Key, and Slug) before launching.");
        return;
    }
    
    const btn = document.getElementById("btn-trigger-cloner");
    btn.disabled = true;
    btn.textContent = "Launching Bot...";
    
    fetch(localServerUrl + "/api/kaggle/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            username,
            key,
            slug,
            db_root: "new_automation_courses",
            title: "Multi-Teacher Forum Cloner Automation"
        })
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            alert("🚀 Cloner notebook pushed to Kaggle successfully! The VM will start mirroring shortly.");
        } else {
            alert("Kaggle trigger failed: " + data.error);
        }
        btn.disabled = false;
        btn.textContent = "LAUNCH MIRROR BOT";
    })
    .catch(err => {
        alert("Request failed: " + err);
        btn.disabled = false;
        btn.textContent = "LAUNCH MIRROR BOT";
    });
});

// 9. Force Restart Trigger in Firebase
document.getElementById("btn-trigger-restart").addEventListener("click", () => {
    if (!db) {
        alert("Firebase is not connected.");
        return;
    }
    
    if (confirm("Are you sure you want to force restart the active cloner? (This will write trigger_restart = true in Firebase to trigger server push)")) {
        db.ref("new_automation_courses/control/trigger_restart").set(true, (err) => {
            if (err) {
                alert("Failed to trigger restart: " + err);
            } else {
                alert("🔄 Restart request written successfully! The cloud server will push the notebook shortly.");
            }
        });
    }
});

// 10. Auto-initialize using current Firebase details (extract from environment or input URL prompt)
window.addEventListener("load", () => {
    // Read the current default firebase URL from standard config URL if available
    const dbUrl = "https://secret-gpt-default-rtdb.asia-southeast1.firebasedatabase.app";
    document.getElementById("fb-url").value = dbUrl;
    initFirebase(dbUrl);
    
    // Add event listener to URL input for manually switching database connections
    document.getElementById("fb-url").addEventListener("change", (e) => {
        initFirebase(e.target.value);
    });
});
