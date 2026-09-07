/*
 * BrandWave Chatbot Widget — vanilla JS, no external dependencies.
 * Embedded via: <script src=".../chatbot-widget/widget.js" data-bot-id="..." data-api-url="..." data-color="..." data-bot-name="..." data-welcome="..." async></script>
 */
(function () {
  "use strict";

  var scriptEl = document.currentScript;
  if (!scriptEl) {
    var scripts = document.getElementsByTagName("script");
    for (var i = 0; i < scripts.length; i++) {
      if (scripts[i].src && scripts[i].src.indexOf("widget.js") !== -1) {
        scriptEl = scripts[i];
        break;
      }
    }
  }
  if (!scriptEl) return;

  var BOT_ID = scriptEl.getAttribute("data-bot-id");
  if (!BOT_ID) {
    console.error("[BrandWave Widget] data-bot-id is required.");
    return;
  }

  var API_URL = (scriptEl.getAttribute("data-api-url") || "").replace(/\/$/, "");
  if (!API_URL) {
    var src = scriptEl.src || "";
    var m = src.match(/^(https?:\/\/[^/]+)/);
    API_URL = m ? m[1] : "";
  }
  var COLOR = scriptEl.getAttribute("data-color") || "#4F46E5";
  var BOT_NAME = scriptEl.getAttribute("data-bot-name") || "Assistant";
  var WELCOME =
    scriptEl.getAttribute("data-welcome") ||
    "Hi! I'm " + BOT_NAME + ". How can I help you today?";

  var SESSION_KEY = "bw_chatbot_session_" + BOT_ID;
  var sessionId = null;
  try {
    sessionId = window.localStorage.getItem(SESSION_KEY);
  } catch (e) {}

  var PREFIX = "bw-cb";

  // ── Styles ──────────────────────────────────
  var style = document.createElement("style");
  style.textContent =
    "." + PREFIX + "-bubble{position:fixed;bottom:20px;right:20px;width:58px;height:58px;border-radius:50%;" +
    "background:" + COLOR + ";box-shadow:0 4px 16px rgba(0,0,0,.25);cursor:pointer;z-index:2147483000;" +
    "display:flex;align-items:center;justify-content:center;transition:transform .15s ease;border:none;padding:0;}" +
    "." + PREFIX + "-bubble:hover{transform:scale(1.06);}" +
    "." + PREFIX + "-bubble svg{width:26px;height:26px;fill:#fff;}" +
    "." + PREFIX + "-window{position:fixed;bottom:90px;right:20px;width:360px;max-width:calc(100vw - 24px);" +
    "height:520px;max-height:calc(100vh - 110px);background:#fff;border-radius:16px;" +
    "box-shadow:0 8px 32px rgba(0,0,0,.22);display:none;flex-direction:column;overflow:hidden;" +
    "z-index:2147483000;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;}" +
    "." + PREFIX + "-window.open{display:flex;}" +
    "." + PREFIX + "-header{background:" + COLOR + ";color:#fff;padding:14px 16px;display:flex;align-items:center;gap:10px;flex-shrink:0;}" +
    "." + PREFIX + "-avatar{width:32px;height:32px;border-radius:50%;background:rgba(255,255,255,.25);" +
    "display:flex;align-items:center;justify-content:center;font-weight:700;font-size:14px;flex-shrink:0;}" +
    "." + PREFIX + "-header-info{flex:1;min-width:0;}" +
    "." + PREFIX + "-header-name{font-size:14px;font-weight:700;line-height:1.2;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}" +
    "." + PREFIX + "-header-status{font-size:11px;opacity:.85;}" +
    "." + PREFIX + "-close{background:none;border:none;color:#fff;cursor:pointer;padding:4px;opacity:.9;flex-shrink:0;}" +
    "." + PREFIX + "-close:hover{opacity:1;}" +
    "." + PREFIX + "-close svg{width:18px;height:18px;fill:currentColor;}" +
    "." + PREFIX + "-messages{flex:1;overflow-y:auto;padding:14px;display:flex;flex-direction:column;gap:10px;background:#f7f7f9;}" +
    "." + PREFIX + "-row{display:flex;max-width:85%;}" +
    "." + PREFIX + "-row.customer{align-self:flex-end;justify-content:flex-end;}" +
    "." + PREFIX + "-row.bot{align-self:flex-start;}" +
    "." + PREFIX + "-bubble-msg{padding:9px 13px;border-radius:14px;font-size:13.5px;line-height:1.45;word-wrap:break-word;white-space:pre-wrap;}" +
    "." + PREFIX + "-row.customer ." + PREFIX + "-bubble-msg{background:" + COLOR + ";color:#fff;border-bottom-right-radius:4px;}" +
    "." + PREFIX + "-row.bot ." + PREFIX + "-bubble-msg{background:#fff;color:#1a1a1a;border:1px solid #e6e6ea;border-bottom-left-radius:4px;}" +
    "." + PREFIX + "-typing{display:flex;gap:4px;padding:10px 13px;background:#fff;border:1px solid #e6e6ea;border-radius:14px;border-bottom-left-radius:4px;width:fit-content;}" +
    "." + PREFIX + "-typing span{width:6px;height:6px;border-radius:50%;background:#b5b5be;animation:" + PREFIX + "-bounce 1.2s infinite;}" +
    "." + PREFIX + "-typing span:nth-child(2){animation-delay:.15s;}" +
    "." + PREFIX + "-typing span:nth-child(3){animation-delay:.3s;}" +
    "@keyframes " + PREFIX + "-bounce{0%,60%,100%{transform:translateY(0);opacity:.5;}30%{transform:translateY(-4px);opacity:1;}}" +
    "." + PREFIX + "-escalation{font-size:11.5px;color:#92400e;background:#fef3c7;border:1px solid #fde68a;" +
    "border-radius:8px;padding:7px 10px;margin-top:2px;}" +
    "." + PREFIX + "-inputbar{display:flex;align-items:center;gap:8px;padding:10px;border-top:1px solid #ececf0;background:#fff;flex-shrink:0;}" +
    "." + PREFIX + "-input{flex:1;border:1px solid #dedee4;border-radius:20px;padding:9px 14px;font-size:13.5px;outline:none;min-width:0;}" +
    "." + PREFIX + "-input:focus{border-color:" + COLOR + ";}" +
    "." + PREFIX + "-send{background:" + COLOR + ";border:none;width:34px;height:34px;border-radius:50%;flex-shrink:0;" +
    "display:flex;align-items:center;justify-content:center;cursor:pointer;opacity:1;transition:opacity .15s;}" +
    "." + PREFIX + "-send:disabled{opacity:.5;cursor:default;}" +
    "." + PREFIX + "-send svg{width:15px;height:15px;fill:#fff;margin-left:1px;}" +
    "." + PREFIX + "-powered{text-align:center;font-size:10px;color:#b0b0b8;padding:5px 0 8px;}" +
    "@media (max-width:480px){" +
    "." + PREFIX + "-window{bottom:0;right:0;left:0;top:0;width:100%;max-width:100%;height:100%;max-height:100%;border-radius:0;}" +
    "." + PREFIX + "-bubble{bottom:16px;right:16px;}" +
    "}";
  document.head.appendChild(style);

  // ── DOM ─────────────────────────────────────
  var bubble = document.createElement("button");
  bubble.className = PREFIX + "-bubble";
  bubble.setAttribute("aria-label", "Open chat");
  bubble.innerHTML =
    '<svg viewBox="0 0 24 24"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z"/></svg>';

  var win = document.createElement("div");
  win.className = PREFIX + "-window";
  win.innerHTML =
    '<div class="' + PREFIX + '-header">' +
    '<div class="' + PREFIX + '-avatar">' + escapeHtml(BOT_NAME.charAt(0).toUpperCase()) + "</div>" +
    '<div class="' + PREFIX + '-header-info">' +
    '<div class="' + PREFIX + '-header-name">' + escapeHtml(BOT_NAME) + "</div>" +
    '<div class="' + PREFIX + '-header-status">Online</div>' +
    "</div>" +
    '<button class="' + PREFIX + '-close" aria-label="Close chat">' +
    '<svg viewBox="0 0 24 24"><path d="M18.3 5.71L12 12.01l-6.3-6.3-1.4 1.4 6.3 6.3-6.3 6.3 1.4 1.4 6.3-6.3 6.3 6.3 1.4-1.4-6.3-6.3 6.3-6.3z"/></svg>' +
    "</button>" +
    "</div>" +
    '<div class="' + PREFIX + '-messages"></div>' +
    '<div class="' + PREFIX + '-inputbar">' +
    '<input type="text" class="' + PREFIX + '-input" placeholder="Type a message..." autocomplete="off" />' +
    '<button class="' + PREFIX + '-send" aria-label="Send message">' +
    '<svg viewBox="0 0 24 24"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>' +
    "</button>" +
    "</div>" +
    '<div class="' + PREFIX + '-powered">Powered by BrandWave</div>';

  document.body.appendChild(bubble);
  document.body.appendChild(win);

  var messagesEl = win.querySelector("." + PREFIX + "-messages");
  var inputEl = win.querySelector("." + PREFIX + "-input");
  var sendBtn = win.querySelector("." + PREFIX + "-send");
  var closeBtn = win.querySelector("." + PREFIX + "-close");

  var isOpen = false;
  var isSending = false;
  var greeted = false;

  function toggleWindow() {
    isOpen = !isOpen;
    win.classList.toggle("open", isOpen);
    if (isOpen) {
      if (!greeted) {
        addMessage("bot", WELCOME);
        greeted = true;
      }
      inputEl.focus();
    }
  }

  bubble.addEventListener("click", toggleWindow);
  closeBtn.addEventListener("click", toggleWindow);

  function escapeHtml(str) {
    var div = document.createElement("div");
    div.textContent = str == null ? "" : String(str);
    return div.innerHTML;
  }

  function scrollToBottom() {
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function addMessage(sender, text) {
    var row = document.createElement("div");
    row.className = PREFIX + "-row " + sender;
    var bubbleMsg = document.createElement("div");
    bubbleMsg.className = PREFIX + "-bubble-msg";
    bubbleMsg.textContent = text;
    row.appendChild(bubbleMsg);
    messagesEl.appendChild(row);
    scrollToBottom();
    return row;
  }

  var escalationShown = false;

  function addEscalationNotice() {
    if (escalationShown) return;
    escalationShown = true;
    var notice = document.createElement("div");
    notice.className = PREFIX + "-escalation";
    notice.textContent = "This conversation has been forwarded to our team — someone will follow up shortly.";
    messagesEl.appendChild(notice);
    scrollToBottom();
  }

  function showTyping() {
    var row = document.createElement("div");
    row.className = PREFIX + "-row bot";
    row.setAttribute("data-typing", "1");
    row.innerHTML = '<div class="' + PREFIX + '-typing"><span></span><span></span><span></span></div>';
    messagesEl.appendChild(row);
    scrollToBottom();
    return row;
  }

  function setSending(state) {
    isSending = state;
    sendBtn.disabled = state;
  }

  function sendMessage() {
    var text = inputEl.value.trim();
    if (!text || isSending) return;

    addMessage("customer", text);
    inputEl.value = "";
    setSending(true);
    var typingRow = showTyping();

    fetch(API_URL + "/api/chatbot/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        bot_id: BOT_ID,
        message: text,
        customer_session_id: sessionId,
      }),
    })
      .then(function (res) {
        if (!res.ok) throw new Error("Request failed: " + res.status);
        return res.json();
      })
      .then(function (data) {
        typingRow.remove();
        if (data.customer_session_id) {
          sessionId = data.customer_session_id;
          try {
            window.localStorage.setItem(SESSION_KEY, sessionId);
          } catch (e) {}
        }
        addMessage("bot", data.response || "Sorry, I couldn't process that.");
        if (data.should_escalate) addEscalationNotice();
      })
      .catch(function () {
        typingRow.remove();
        addMessage("bot", "Sorry, something went wrong. Please try again in a moment.");
      })
      .finally(function () {
        setSending(false);
        inputEl.focus();
      });
  }

  sendBtn.addEventListener("click", sendMessage);
  inputEl.addEventListener("keydown", function (e) {
    if (e.key === "Enter") sendMessage();
  });
})();
