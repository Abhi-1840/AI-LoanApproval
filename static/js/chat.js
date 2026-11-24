/**
 * AI Loan Approval System — Conversational Frontend Logic
 * Implements ChatGPT layout dynamics & Google Antigravity visual aesthetics.
 * Features: Multi-session sidebar persistence, zero-glitch text typing, strict limit handling.
 */

// ── DOM Element Bindings ──
const messagesContainer = document.getElementById("messagesContainer");
const emptyState = document.getElementById("emptyState");
const inputField = document.getElementById("messageInput");
const sendBtn = document.getElementById("sendBtn");
const newChatBtn = document.getElementById("newChatBtn");
const clearBtn = document.getElementById("clearBtn");
const sidebar = document.getElementById("sidebar");
const chatHistory = document.getElementById("chatHistory");
const desktopSidebarToggle = document.getElementById("desktopSidebarToggle");
const mobileMenuBtn = document.getElementById("mobileMenuBtn");
const sidebarBackdrop = document.getElementById("sidebarBackdrop");
const themeToggleButtons = document.querySelectorAll(".theme-toggle-btn");

let session_id = null;
let currentSessionTitle = "New Conversation";
let typingDiv = null;
let isProcessing = false;

// ── Theme Management (Light / Dark with Persistence) ──
function initTheme() {
    const currentTheme = document.documentElement.getAttribute("data-theme") || "dark";
    updateThemeUI(currentTheme);
}

function toggleTheme() {
    if (window.LoanAIMotion && typeof window.LoanAIMotion.triggerThemeTransition === "function") {
        window.LoanAIMotion.triggerThemeTransition();
    }
    const currentTheme = document.documentElement.getAttribute("data-theme") || "dark";
    const newTheme = currentTheme === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", newTheme);
    localStorage.setItem("loan_ai_theme", newTheme);
    updateThemeUI(newTheme);
}

function updateThemeUI(theme) {
    themeToggleButtons.forEach(btn => {
        btn.setAttribute("title", `Switch to ${theme === "dark" ? "Light" : "Dark"} Mode`);
    });
}

themeToggleButtons.forEach(btn => {
    btn.addEventListener("click", toggleTheme);
});

// ── Mobile & Desktop Sidebar Toggles ──
if (desktopSidebarToggle) {
    desktopSidebarToggle.addEventListener("click", () => {
        sidebar.classList.toggle("collapsed");
    });
}

if (mobileMenuBtn && sidebarBackdrop) {
    mobileMenuBtn.addEventListener("click", () => {
        sidebar.classList.add("mobile-open");
        sidebarBackdrop.classList.add("show");
    });

    sidebarBackdrop.addEventListener("click", () => {
        sidebar.classList.remove("mobile-open");
        sidebarBackdrop.classList.remove("show");
    });
}

// ── Local Storage Multi-Session Chat History ──
const STORAGE_KEY = "loan_ai_saved_sessions";

function getSavedSessions() {
    try {
        const raw = localStorage.getItem(STORAGE_KEY);
        return raw ? JSON.parse(raw) : [];
    } catch (e) {
        return [];
    }
}

function saveSessions(sessions) {
    try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions));
    } catch (e) {
        console.warn("Storage full or unavailable", e);
    }
}

function getCurrentSessionRecord() {
    const sessions = getSavedSessions();
    return sessions.find(s => s.id === session_id);
}

function updateSessionRecord(messages, newTitle = null) {
    if (!session_id) return;
    let sessions = getSavedSessions();
    let idx = sessions.findIndex(s => s.id === session_id);

    const now = new Date();
    const timeStr = now.toLocaleDateString([], { month: 'short', day: 'numeric' }) + ", " +
                    now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    if (idx === -1) {
        const newRecord = {
            id: session_id,
            title: newTitle || currentSessionTitle || "Loan Conversation",
            updatedAt: timeStr,
            messages: messages || []
        };
        sessions.unshift(newRecord);
    } else {
        if (newTitle) {
            sessions[idx].title = newTitle;
            currentSessionTitle = newTitle;
        }
        if (messages) {
            sessions[idx].messages = messages;
        }
        sessions[idx].updatedAt = timeStr;
        // Move active session to top
        const updated = sessions.splice(idx, 1)[0];
        sessions.unshift(updated);
    }

    // Keep max 25 recent sessions
    if (sessions.length > 25) {
        sessions = sessions.slice(0, 25);
    }

    saveSessions(sessions);
    renderSidebarSessions();
}

function renderSidebarSessions() {
    if (!chatHistory) return;
    const sessions = getSavedSessions();
    chatHistory.innerHTML = "";

    if (sessions.length === 0) {
        const emptyItem = document.createElement("div");
        emptyItem.className = "history-item active";
        emptyItem.innerHTML = `
            <svg class="history-item-icon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
            </svg>
            <div class="history-item-details">
                <span class="session-label">Current Session</span>
                <span class="session-time">New</span>
            </div>
            <span class="live-pill">Live</span>
        `;
        chatHistory.appendChild(emptyItem);
        return;
    }

    sessions.forEach(sess => {
        const item = document.createElement("div");
        const isActive = sess.id === session_id;
        item.className = `history-item ${isActive ? "active" : ""}`;
        item.setAttribute("data-id", sess.id);

        item.innerHTML = `
            <svg class="history-item-icon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
            </svg>
            <div class="history-item-details">
                <span class="session-label" title="${sess.title}">${sess.title}</span>
                <span class="session-time">${sess.updatedAt || ""}</span>
            </div>
            ${isActive ? '<span class="live-pill">Live</span>' : ''}
            <button class="delete-chat-btn" title="Delete conversation">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <line x1="18" y1="6" x2="6" y2="18"></line>
                    <line x1="6" y1="6" x2="18" y2="18"></line>
                </svg>
            </button>
        `;

        // Switch to this session on click
        item.addEventListener("click", (e) => {
            if (e.target.closest(".delete-chat-btn")) return;
            switchSession(sess.id);
        });

        // Delete button
        const delBtn = item.querySelector(".delete-chat-btn");
        if (delBtn) {
            delBtn.addEventListener("click", (e) => {
                e.stopPropagation();
                deleteSession(sess.id);
            });
        }

        chatHistory.appendChild(item);
    });
}

function switchSession(targetSessionId) {
    if (session_id === targetSessionId) return;

    const sessions = getSavedSessions();
    const target = sessions.find(s => s.id === targetSessionId);
    if (!target) return;

    session_id = target.id;
    currentSessionTitle = target.title;

    // Render all saved messages from that session
    messagesContainer.innerHTML = "";
    if (emptyState) emptyState.style.display = "none";

    if (target.messages && target.messages.length > 0) {
        target.messages.forEach(msg => {
            renderMessageNode(msg.text, msg.sender, msg.time || "", false, false);
        });
    } else {
        if (emptyState) {
            emptyState.style.display = "block";
            messagesContainer.appendChild(emptyState);
        }
    }

    renderSidebarSessions();

    // Close mobile drawer if open
    if (sidebarBackdrop && sidebarBackdrop.classList.contains("show")) {
        sidebar.classList.remove("mobile-open");
        sidebarBackdrop.classList.remove("show");
    }

    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

function deleteSession(targetSessionId) {
    let sessions = getSavedSessions();
    sessions = sessions.filter(s => s.id !== targetSessionId);
    saveSessions(sessions);

    if (session_id === targetSessionId) {
        startNewChat();
    } else {
        renderSidebarSessions();
    }
}

// ── Auto-Resizing Textarea & Input State ──
function adjustTextareaHeight() {
    inputField.style.height = "auto";
    const maxHeight = 160;
    const newHeight = Math.min(inputField.scrollHeight, maxHeight);
    inputField.style.height = `${newHeight}px`;

    // Toggle Send Button active state
    if (inputField.value.trim().length > 0 && !isProcessing) {
        sendBtn.removeAttribute("disabled");
    } else {
        sendBtn.setAttribute("disabled", "true");
    }
}

inputField.addEventListener("input", adjustTextareaHeight);

inputField.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        if (!sendBtn.disabled) {
            sendMessage();
        }
    }
});

sendBtn.addEventListener("click", sendMessage);

// ── Interactive Suggestion Cards & Quick Profiles ──
document.querySelectorAll(".suggestion-card").forEach(card => {
    function activateSuggestion() {
        const promptText = card.getAttribute("data-prompt");
        if (promptText) {
            inputField.value = promptText;
            adjustTextareaHeight();
            sendMessage();
        }
    }
    card.addEventListener("click", activateSuggestion);
    card.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            activateSuggestion();
        }
    });
});

document.querySelectorAll(".profile-chip").forEach(chip => {
    chip.addEventListener("click", () => {
        const customerId = chip.getAttribute("data-id");
        const promptText = chip.getAttribute("data-prompt");
        if (customerId) {
            inputField.value = customerId;
            adjustTextareaHeight();
            sendMessage();
        } else if (promptText) {
            inputField.value = promptText;
            adjustTextareaHeight();
            sendMessage();
        }
    });
});

// ── Initialization & Session Handling ──
window.onload = async function () {
    initTheme();
    adjustTextareaHeight();
    renderSidebarSessions();

    const sessions = getSavedSessions();
    if (sessions.length > 0) {
        // Load the most recent session
        switchSession(sessions[0].id);
    } else {
        await startNewChat();
    }
};

async function startNewChat() {
    try {
        const res = await fetch("/new_chat");
        const data = await res.json();
        session_id = data.session_id;
    } catch (e) {
        session_id = "sess_" + Math.random().toString(36).substring(2, 10);
    }

    currentSessionTitle = "New Conversation";
    messagesContainer.innerHTML = "";
    if (emptyState) {
        emptyState.style.display = "block";
        messagesContainer.appendChild(emptyState);
    }
    inputField.value = "";
    adjustTextareaHeight();
    renderSidebarSessions();
}

newChatBtn.addEventListener("click", startNewChat);

// ── Clear Chat Messages ──
if (clearBtn) {
    clearBtn.addEventListener("click", () => {
        messagesContainer.innerHTML = "";
        if (emptyState) {
            emptyState.style.display = "block";
            messagesContainer.appendChild(emptyState);
        }
        updateSessionRecord([], currentSessionTitle);
    });
}

// ── Sending & Processing Messages ──
async function sendMessage() {
    const text = inputField.value.trim();
    if (!text || isProcessing) return;

    if (!session_id) {
        await startNewChat();
    }

    // Hide empty state once conversation starts
    if (emptyState && emptyState.parentNode === messagesContainer) {
        emptyState.style.display = "none";
    }

    // Update conversation title based on first query
    const sess = getCurrentSessionRecord();
    if (!sess || sess.messages.length === 0) {
        let title = text.length > 28 ? text.substring(0, 28) + "..." : text;
        if (/cust\w+/i.test(text)) {
            title = "KYC: " + text.match(/cust\w+/i)[0];
        }
        currentSessionTitle = title;
    }

    // Add User Message
    addMessage(text, "user");
    inputField.value = "";
    adjustTextareaHeight();

    isProcessing = true;
    sendBtn.setAttribute("disabled", "true");
    addTyping();

    try {
        const resp = await fetch("/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                session_id: session_id,
                user_input: text
            })
        });

        const data = await resp.json();
        removeTyping();

        if (data.orchestration_command) {
            await handleOrchestration(data.orchestration_command, text);
            return;
        }

        // Clean any backend tokens from response
        const cleanReply = sanitizeMessage(data.response_text);
        addMessage(cleanReply, "assistant");

        // If user just completed in-chat registration, update session record and title
        if (cleanReply.includes("Registration Completed Successfully")) {
            const nameMatch = cleanReply.match(/Welcome to AI Loan Approval System, \*\*([^*]+)\*\*/i);
            const custMatch = cleanReply.match(/Customer ID\*\*:\s*`([^`]+)`/i);
            const newTitle = nameMatch ? `KYC: ${nameMatch[1]} (${custMatch ? custMatch[1] : 'Verified'})` : "KYC: Verified Customer";
            currentSessionTitle = newTitle;
            updateSessionRecord(null, newTitle);
        }

    } catch (err) {
        removeTyping();
        addMessage("Connection error. Please check your backend connection and try again.", "assistant");
    } finally {
        isProcessing = false;
        adjustTextareaHeight();
    }
}

// ── Backend Orchestration Handler (KYC & Underwriting) ──
async function handleOrchestration(cmd, user_text) {
    const step = cmd.replace("[[FLASK_CALL:", "").replace("]]", "");

    if (step === "VERIFY_KYC") {
        const customer_id = (user_text.match(/cust[\w\d]+/i) || [""])[0];

        addTyping();
        try {
            const resp = await fetch("/orchestrate", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    step: "VERIFY_KYC",
                    session_id: session_id,
                    customer_info: { customer_id: customer_id }
                })
            });

            const data = await resp.json();
            removeTyping();

            if (data.status === "success") {
                const c = data.customer_data;
                const newTitle = `KYC: ${c.name} (${customer_id})`;
                currentSessionTitle = newTitle;

                const prelimLimit = Number(c.pre_approved_limit || c.salary * 15).toLocaleString('en-IN');
                const cardHtml = `
                    <strong>KYC Verification Successful</strong><br>
                    • Customer Name: <strong>${c.name}</strong><br>
                    • Credit Score: <strong>${c.credit_score}</strong><br>
                    • Monthly Salary: <strong>₹${Number(c.salary).toLocaleString('en-IN')}</strong><br>
                    • Preliminary Loan Eligibility: <strong>Up to ₹${prelimLimit}</strong><br>
                    • Application Status: <span class="status-badge preapproved">Preliminary Eligible</span><br><br>
                    <small style="color:var(--text-muted);display:block;line-height:1.45;">This is an initial eligibility estimate based on your monthly net salary (15x salary). Final loan approval is subject to CIBIL verification, age eligibility, FOIR calculation, document verification and the lender's final assessment.</small><br>
                    How much loan amount would you like to apply for (up to ₹${prelimLimit})?
                `;
                addMessage(cardHtml, "assistant", false);
                updateSessionRecord(null, newTitle);
            } else {
                addMessage(data.message || "Customer verification failed. Please check the Customer ID.", "assistant");
            }
        } catch (err) {
            removeTyping();
            addMessage("KYC verification error. Please retry.", "assistant");
        }
    }

// ── Flexible Loan Amount & Tenure Parser ──
function extractLoanAmount(text) {
    if (!text) return null;
    const clean = text.toString().toLowerCase().replace(/,/g, "").replace(/₹/g, "").replace(/rs\.?/g, "").trim();

    // Match Lakhs: 5 lakh, 5.5 lakhs, 5 lac
    const lakhMatch = clean.match(/(\d+(?:\.\d+)?)\s*(?:lakhs|lakh|lacs|lac|l)\b/);
    if (lakhMatch) {
        return Math.round(parseFloat(lakhMatch[1]) * 100000);
    }

    // Match Thousands: 50k, 50 k
    const kMatch = clean.match(/(\d+(?:\.\d+)?)\s*k\b/);
    if (kMatch) {
        return Math.round(parseFloat(kMatch[1]) * 1000);
    }

    // Match direct 4+ digit number (e.g. 50000)
    const numMatch = clean.match(/\b\d{4,}\b/);
    if (numMatch) {
        return parseInt(numMatch[0], 10);
    }

    // Match 3 digit number (e.g. 500)
    const num3Match = clean.match(/\b\d{3}\b/);
    if (num3Match) {
        return parseInt(num3Match[0], 10);
    }

    // Fallback to any digits
    const anyMatch = clean.match(/\d+/);
    if (anyMatch) {
        return parseInt(anyMatch[0], 10);
    }
    return null;
}

function extractTenure(text) {
    if (!text) return null;
    const clean = text.toString().toLowerCase();
    const yrMatch = clean.match(/(\d+)\s*(?:years?|yrs?)\b/);
    if (yrMatch) {
        return parseInt(yrMatch[1], 10) * 12;
    }
    const moMatch = clean.match(/(\d+)\s*(?:months?|mos?|m)\b/);
    if (moMatch) {
        return parseInt(moMatch[1], 10);
    }
    const tenMatch = clean.match(/tenure\s*(?:of|is|:)?\s*(\d+)/);
    if (tenMatch) {
        const val = parseInt(tenMatch[1], 10);
        return val <= 6 ? val * 12 : val;
    }
    return null;
}

    if (step === "UNDERWRITE") {
        let amt = extractLoanAmount(user_text);
        let tenure = extractTenure(user_text);
        if (!amt) {
            const rawPrompt = prompt("Please enter the requested loan amount:");
            amt = extractLoanAmount(rawPrompt);
            if (!tenure) tenure = extractTenure(rawPrompt);
        }

        addTyping();
        try {
            const resp = await fetch("/orchestrate", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    step: "UNDERWRITE",
                    session_id: session_id,
                    customer_info: { loan_amount: amt, tenure: tenure }
                })
            });

            const data = await resp.json();
            removeTyping();

            if (data.worker_message) {
                const cleanWorker = sanitizeMessage(data.worker_message);
                addMessage(cleanWorker, "assistant");
            }

            if (data.email_message) {
                const cleanEmail = sanitizeMessage(data.email_message);
                setTimeout(() => {
                    addMessage(cleanEmail, "assistant", false);
                }, 350);
            }
        } catch (err) {
            removeTyping();
            addMessage("Underwriting process encountered an error. Please retry.", "assistant");
        }
    }
}

// ── Sanitize Message (Strips all programming tokens) ──
function sanitizeMessage(text) {
    if (!text) return "";
    return text.replace(/\[\[FLASK_CALL:[A-Z_]+\]\]/g, "").trim();
}

// ── Message Presentation & Avatars ──
function addMessage(text, sender, useTypewriter = true) {
    if (emptyState && emptyState.style.display !== "none") {
        emptyState.style.display = "none";
    }

    const now = new Date();
    const timeStr = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    // Save message to current session history
    let sess = getCurrentSessionRecord();
    let currentMsgs = sess ? sess.messages : [];
    currentMsgs.push({
        text: text,
        sender: sender,
        time: timeStr
    });
    updateSessionRecord(currentMsgs);

    renderMessageNode(text, sender, timeStr, useTypewriter);
}

function renderMessageNode(text, sender, timeStr, useTypewriter = false, animateEnter = true) {
    const group = document.createElement("div");
    group.className = `message-group ${sender}${animateEnter ? "" : " no-enter-anim"}`;

    // Avatar SVG Icons
    const avatar = document.createElement("div");
    avatar.className = "message-avatar";

    if (sender === "assistant") {
        avatar.appendChild(createLoanAILogo({ size: 24, isGenerating: false }));
    } else {
        avatar.innerHTML = `
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
                <circle cx="12" cy="7" r="4"></circle>
            </svg>
        `;
    }

    const bodyWrap = document.createElement("div");
    bodyWrap.className = "message-body-wrap";

    // Header with Sender Name, Role Badge, and Time
    const headerRow = document.createElement("div");
    headerRow.className = "message-header-row";

    const senderName = document.createElement("span");
    senderName.className = "sender-name";
    senderName.innerText = sender === "user" ? "You" : "Loan AI Assistant";

    headerRow.appendChild(senderName);

    if (sender === "assistant") {
        const badge = document.createElement("span");
        badge.className = "role-badge";
        badge.innerText = "Underwriter";
        headerRow.appendChild(badge);
    }

    const timeSpan = document.createElement("span");
    timeSpan.className = "message-timestamp";
    timeSpan.innerText = timeStr || new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    headerRow.appendChild(timeSpan);

    const messageCard = document.createElement("div");
    messageCard.className = "message-card";

    bodyWrap.appendChild(headerRow);
    bodyWrap.appendChild(messageCard);

    // Copy Action Button
    if (sender === "assistant") {
        const actions = document.createElement("div");
        actions.className = "message-actions";

        const copyBtn = document.createElement("button");
        copyBtn.className = "copy-btn";
        copyBtn.innerHTML = `
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
            </svg>
            <span>Copy</span>
        `;
        copyBtn.addEventListener("click", () => {
            const rawText = messageCard.innerText;
            navigator.clipboard.writeText(rawText).then(() => {
                copyBtn.innerHTML = `<span>Copied!</span>`;
                setTimeout(() => {
                    copyBtn.innerHTML = `
                        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                        </svg>
                        <span>Copy</span>
                    `;
                }, 2000);
            });
        });

        actions.appendChild(copyBtn);
        bodyWrap.appendChild(actions);
    }

    group.appendChild(avatar);
    group.appendChild(bodyWrap);
    messagesContainer.appendChild(group);

    if (sender === "assistant" && useTypewriter) {
        typeWriterEffect(messageCard, text, 14);
    } else {
        messageCard.innerHTML = formatMessage(text);
    }

    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

// ── Text Formatter (Clean badges without raw code) ──
function formatMessage(text) {
    if (!text) return "";
    let clean = sanitizeMessage(text);

    let formatted = clean
        .replace(/^\s*[-*]\s+(.*)/gm, "• $1")
        .replace(/\n/g, "<br>")
        .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
        .replace(/(^|[\s(>])\*([^*\n]+?)\*(?=[\s.,!?;:)<]|$)/g, "$1<em>$2</em>");

    // Single-pass replacement for status chips (prevents recursive tag nesting)
    formatted = formatted.replace(/\b(Preliminary Eligible|Under Review|Final Approved|Pre-Approved|Approved|Verification Successful|KYC Verified|Rejected|Rejection)\b/gi, (match) => {
        const lower = match.toLowerCase();
        if (lower === "preliminary eligible" || lower === "pre-approved") {
            return `<span class="status-badge preapproved">Preliminary Eligible</span>`;
        } else if (lower === "under review") {
            return `<span class="status-badge review">Under Review</span>`;
        } else if (lower === "final approved" || lower === "approved") {
            return `<span class="status-badge approved">Final Approved</span>`;
        } else if (lower.includes("reject")) {
            return `<span class="status-badge rejected">Rejected</span>`;
        } else {
            return `<span class="status-badge verified">${match}</span>`;
        }
    });

    return formatted;
}

// ── LoanAI Logo Component Helper ──
const LOANAI_LOGO_SRC = "/static/img/loanai-logo.png";

function createLoanAILogo(options = {}) {
    const { size = 24, isGenerating = false, className = "" } = options;
    const img = document.createElement("img");
    img.src = LOANAI_LOGO_SRC;
    img.alt = "LoanAI";
    img.className = `loanai-logo ${isGenerating ? "generating" : ""} ${className}`.trim();
    img.width = size;
    img.height = size;
    return img;
}

function setGeneratingState(isGenerating) {
    document.body.classList.toggle("ai-generating", isGenerating);
    const statusText = document.getElementById("systemStatusText");
    if (statusText) {
        statusText.textContent = isGenerating ? "Thinking..." : "AI Ready";
    }
    const sidebarLogo = document.getElementById("sidebarBrandLogo");
    if (sidebarLogo) {
        if (isGenerating) {
            sidebarLogo.classList.add("generating");
        } else {
            sidebarLogo.classList.remove("generating");
        }
    }
}
function typeWriterEffect(element, rawText, speed = 14) {
    const clean = sanitizeMessage(rawText);
    if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
        element.innerHTML = formatMessage(clean);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
        return;
    }
    const words = clean.split(/\s+/);
    let index = 0;
    let accumulated = "";
    element.innerHTML = "";

    function type() {
        if (index < words.length) {
            accumulated += (index === 0 ? "" : " ") + words[index];
            element.innerHTML = formatMessage(accumulated);
            index++;
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
            setTimeout(type, speed);
        } else {
            element.innerHTML = formatMessage(clean);
        }
    }

    type();
}

// ── Modern Animated Typing Indicator ──
function addTyping() {
    if (typingDiv) return;

    setGeneratingState(true);

    typingDiv = document.createElement("div");
    typingDiv.className = "message-group assistant typing-placeholder";

    const avatar = document.createElement("div");
    avatar.className = "message-avatar";
    avatar.appendChild(createLoanAILogo({ size: 24, isGenerating: true }));

    const bodyWrap = document.createElement("div");
    bodyWrap.className = "message-body-wrap";

    const card = document.createElement("div");
    card.className = "message-card";
    card.innerHTML = `
        <div class="typing-container">
            <span class="typing-label">LoanAI is generating response...</span>
            <div class="typing-dots">
                <span class="typing-dot"></span>
                <span class="typing-dot"></span>
                <span class="typing-dot"></span>
            </div>
        </div>
    `;

    bodyWrap.appendChild(card);
    typingDiv.appendChild(avatar);
    typingDiv.appendChild(bodyWrap);

    messagesContainer.appendChild(typingDiv);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

function removeTyping() {
    setGeneratingState(false);
    if (typingDiv) {
        typingDiv.remove();
        typingDiv = null;
    }
}
