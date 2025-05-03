function $(id) { return document.getElementById(id); }

document.addEventListener("DOMContentLoaded", async () => {
  const content = $("content");
  const saveBtn = $("saveBtn");
  const loading = $("loading");

  chrome.storage.local.get(["analysisState","lastAnalysis","lastError"], ({ analysisState, lastAnalysis, lastError }) => {
    if(analysisState?.status==="loading"){
      loading.style.display="block";
      return; // wait for ready state on next popup reopen
    }
    loading.style.display="none";

    if (lastError) {
      content.innerHTML = `<p id="error">${lastError}</p>`;
      chrome.storage.local.remove("lastError");
      return;
    }

    if (!lastAnalysis || !Array.isArray(lastAnalysis) || !lastAnalysis.length) {
      content.textContent = "No analysis available.";
      return;
    }

    const a = lastAnalysis[0]; // assuming single URL

    $("articleForm").style.display = "block";
    $("title").value = a.title || "";
    $("sentiment").value = a.sentiment || "Neutral";
    $("summary").value = a.summary || "";
    $("category").value = a.category || "";
    $("future_signal").value = a.future_signal || "";
    $("driver_type").value = a.driver_type || "";

    let API_BASE="https://app.aunoo.ai";
    chrome.storage.sync.get(["apiBase","defaultTopic"],({apiBase,defaultTopic})=>{
      if(apiBase) API_BASE=apiBase.replace(/\/+$/,'');

      // fetch with API_BASE
      fetch(`${API_BASE}/api/topics`)
        .then((r) => r.json())
        .then((topics) => {
          const sel = $("topic");
          topics.forEach((t) => {
            const label = typeof t === "string" ? t : (t.name || t.topic || "");
            if (!label) return;
            const opt = document.createElement("option");
            opt.value = label;
            opt.textContent = label;
            sel.appendChild(opt);
          });
          if (sel.options.length) {
            sel.value = a.topic || sel.options[0].value;
          }
        })
        .catch(() => {});

      // Populate other dropdowns
      Promise.all([
        fetch(`${API_BASE}/api/driver_types`).then(r=>r.json()).catch(()=>[]),
        fetch(`${API_BASE}/api/future_signals`).then(r=>r.json()).catch(()=>[]),
        fetch(`${API_BASE}/api/sentiments`).then(r=>r.json()).catch(()=>[]),
      ]).then(([drivers, signals, sentiments])=>{
        const fill=(selId,list,val)=>{
          const sel=$(selId);
          sel.innerHTML="";
          list.forEach(item=>{
            const label=typeof item==="string"?item:(item.name||item);
            const opt=document.createElement("option");
            opt.value=label;opt.textContent=label;sel.appendChild(opt);
          });
          if(list.length) sel.value=val||list[0];
        };
        fill("driver_type",drivers,a.driver_type);
        fill("future_signal",signals,a.future_signal);
        fill("sentiment",sentiments,a.sentiment);
        fetch(`${API_BASE}/api/time_to_impact`).then(r=>r.json()).then(list=>fill("time_to_impact",list,a.time_to_impact)).catch(()=>{});
        if(defaultTopic)$("topic").value=defaultTopic;

        $("sentiment_explanation").value=a.sentiment_explanation||"";
        $("future_signal_explanation").value=a.future_signal_explanation||"";
        $("driver_type_explanation").value=a.driver_type_explanation||"";
        $("time_to_impact_explanation").value=a.time_to_impact_explanation||"";

        saveBtn.hidden = false;
        saveBtn.onclick = () => {
          saveBtn.disabled = true;
          saveBtn.textContent = "Saving…";

          // Merge edited values back
          const edited = {
            ...a,
            title: $("title").value.trim(),
            sentiment: $("sentiment").value,
            summary: $("summary").value.trim(),
            category: $("category").value.trim(),
            future_signal: $("future_signal").value.trim(),
            driver_type: $("driver_type").value.trim(),
            driver_type_explanation: $("driver_type_explanation").value.trim(),
            sentiment_explanation: $("sentiment_explanation").value.trim(),
            future_signal_explanation: $("future_signal_explanation").value.trim(),
            time_to_impact: $("time_to_impact").value,
            time_to_impact_explanation: $("time_to_impact_explanation").value.trim(),
            topic: $("topic").value,
          };

          lastAnalysis[0] = edited;

          chrome.runtime.sendMessage({ type: "SAVE_ANALYSIS", payload: lastAnalysis }, (resp) => {
            if (resp?.ok) {
              saveBtn.textContent = "Saved ✔";
              saveBtn.classList.add("btn-success");
              chrome.storage.local.remove("lastAnalysis");
            } else {
              saveBtn.textContent = "Error – try again";
              saveBtn.disabled = false;
            }
          });
        };
      });
    });
  });

  // Listen for analysisState updates while popup is open
  chrome.storage.onChanged.addListener((changes, area) => {
    if (area === "local" && changes.analysisState) {
      const state = changes.analysisState.newValue;
      if (state && state.status === "ready") {
        // Reload to display results
        location.reload();
      }
    }
  });
}); 