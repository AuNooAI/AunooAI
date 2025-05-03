// Aunoo Bulk Research – background service worker

let API_BASE = "https://app.aunoo.ai"; // will be overridden by stored value
chrome.storage.sync.get("apiBase",({apiBase})=>{if(apiBase) API_BASE=apiBase.replace(/\/+$/,'');});

// helper to build full URL
function api(path) {
  if (path.startsWith("/")) return `${API_BASE}${path}`;
  return `${API_BASE}/${path}`;
}

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: "aunoo-send-article",
    title: "Analyze with Aunoo",
    contexts: ["page", "link"],
  });
});

// Context-menu handler – send URL for analysis
chrome.contextMenus.onClicked.addListener(async (info) => {
  const url = info.linkUrl || info.pageUrl;
  if (!url) return;

  const payload = await new Promise((resolve)=>{
    chrome.storage.sync.get(["defaultTopic","summaryLen","summaryVoice"],({defaultTopic,summaryLen,summaryVoice})=>{
      resolve({
        urls:[url],
        summary_type:"standard",
        model_name:"gpt-4o",
        summary_length: summaryLen || 50,
        summary_voice: summaryVoice || "Business Analyst",
        topic:defaultTopic||"general"
      });
    });
  });

  // Put HUD into loading state and open immediately
  chrome.storage.local.set({ analysisState:{status:"loading",url}, lastAnalysis:[], lastError:null }, openPopupSafe);

  try {
    const res = await fetch(api("/api/bulk-research"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(await res.text());
    const analysis = await res.json();
    const resultsArray = Array.isArray(analysis) ? analysis : analysis.results;
    chrome.storage.local.set({ analysisState:{status:"ready",results:resultsArray}, lastAnalysis: resultsArray || [] });
  } catch (err) {
    chrome.storage.local.set({ analysisState:{status:"error",message:err.message||String(err)}, lastError: err.message || String(err) });
  }
});

// Listener from popup.js for saving articles
chrome.runtime.onMessage.addListener((msg, _sender, reply) => {
  if (msg?.type === "SAVE_ANALYSIS") {
    fetch(api("/api/save-bulk-articles"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ articles: msg.payload }),
    })
      .then((r) => (r.ok ? r.json() : Promise.reject(r.text())))
      .then(() => reply({ ok: true }))
      .catch(async (e) => {
        const message = typeof e === "string" ? e : await e;
        reply({ ok: false, error: message });
      });
    return true; // keep message channel open
  }
});

function openPopupSafe() {
  chrome.windows.getCurrent({}, (win) => {
    if (!win) {
      chrome.action.openPopup();
      return;
    }
    chrome.windows.update(win.id, { focused: true }, () => {
      chrome.action.openPopup();
    });
  });
} 