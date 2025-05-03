document.addEventListener("DOMContentLoaded",()=>{
  const apiInp=document.getElementById("apiUrl");
  const topicSel=document.getElementById("defaultTopic");
  const saveBtn=document.getElementById("saveBtn");

  chrome.storage.sync.get(["apiBase","defaultTopic","summaryLen","summaryVoice"],({apiBase,defaultTopic,summaryLen,summaryVoice})=>{
    apiInp.value=apiBase||"https://app.aunoo.ai";
    document.getElementById("summaryLen").value=summaryLen||50;
    document.getElementById("summaryVoice").value=summaryVoice||"Business Analyst";
    fetch(`${apiInp.value.replace(/\/+$/,'')}/api/topics`).then(r=>r.json()).then(topics=>{
      topics.forEach(t=>{
        const label=typeof t==="string"?t:(t.name||t);
        const opt=document.createElement("option");
        opt.value=label;opt.textContent=label;topicSel.appendChild(opt);
      });
      if(defaultTopic) topicSel.value=defaultTopic;
    }).catch(()=>{});
  });

  saveBtn.onclick=()=>{
    chrome.storage.sync.set({
      apiBase:apiInp.value.trim(),
      defaultTopic:topicSel.value,
      summaryLen:parseInt(document.getElementById("summaryLen").value)||50,
      summaryVoice:document.getElementById("summaryVoice").value
    },()=>{
      saveBtn.textContent="Saved ✔";
      setTimeout(()=>saveBtn.textContent="Save",1500);
    });
  };
}); 