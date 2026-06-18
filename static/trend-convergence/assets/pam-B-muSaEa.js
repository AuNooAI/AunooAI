import{r as t,j as e,aD as j,aE as T,aQ as v,aR as S,aO as A}from"./index-Bf7iYWiS.js";import{u as P,P as w}from"./usePAM-BF8Jgr5E.js";import"./alert-pvcEUSF8.js";import"./card-Cjaz0ZRH.js";import"./progress-BjzQTvbd.js";import"./badge-0AhJ0vNh.js";import"./arrow-right-BZ4Bl1l5.js";import"./clock-3BFkC9T-.js";const k=()=>{const[s,c]=t.useState([]),[i,r]=t.useState(""),[d,p]=t.useState(!0),a=P(),[m,E]=t.useState("comprehensive"),[l,N]=t.useState("1_year"),[u,D]=t.useState(["T1","T2","T3","T4","T5"]),[h,R]=t.useState(90),[g,G]=t.useState(100),[f,x]=t.useState("executive");t.useEffect(()=>{b(),a.loadDefinitions(),a.loadCachedReport()},[]);const b=async()=>{try{const o=await fetch("/api/topics");if(o.ok){const n=await o.json();n.topics&&(c(n.topics),n.topics.length>0&&!i&&r(n.topics[0].name))}}catch(o){console.error("Failed to load topics:",o)}finally{p(!1)}},y=()=>{a.startGeneration({topic:"",analysisType:m,entityType:"publisher",timeHorizon:l,trendFocus:u,daysBack:h,articleLimit:g,model:"gpt-5.4-mini"})};return e.jsxs("div",{className:"pam-app",children:[e.jsx(j,{currentPage:"pam",topics:s,selectedTopic:i,onTopicChange:r}),e.jsx("main",{className:"pam-main-content",children:d?e.jsxs("div",{className:"pam-loading-container",children:[e.jsx("div",{className:"pam-loading-spinner"}),e.jsx("p",{children:"Loading PAM Dashboard..."})]}):e.jsxs("div",{className:"pam-dashboard-wrapper",children:[e.jsx("div",{className:"pam-standalone-toolbar",children:e.jsx("button",{onClick:y,disabled:a.isGenerating,className:"pam-refresh-button",children:a.isGenerating?"Analyzing...":"Generate Analysis"})}),e.jsx(w,{topic:i,isGenerating:a.isGenerating,currentStage:a.currentStage,stageProgress:a.stageProgress,data:a.data,error:a.error,activeView:f,onViewChange:x,onClearError:a.clearError})]})}),e.jsx(T,{})]})},C=`
.pam-app {
  min-height: 100vh;
  background: #f8fafc;
}

.pam-main-content {
  padding-top: 60px; /* Account for fixed navigation */
}

.pam-loading-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: calc(100vh - 60px);
  gap: 1rem;
  color: #64748b;
}

.pam-loading-spinner {
  width: 48px;
  height: 48px;
  border: 4px solid #e2e8f0;
  border-top-color: #ec4899;
  border-radius: 50%;
  animation: pam-spin 1s linear infinite;
}

@keyframes pam-spin {
  to { transform: rotate(360deg); }
}

.pam-dashboard-wrapper {
  max-width: 1600px;
  margin: 0 auto;
  padding: 1rem;
}

.pam-standalone-toolbar {
  display: flex;
  justify-content: flex-end;
  padding: 0.5rem 0;
  margin-bottom: 1rem;
}

.pam-refresh-button {
  background: #ec4899;
  color: white;
  border: none;
  padding: 0.75rem 1.5rem;
  border-radius: 0.5rem;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.2s;
}

.pam-refresh-button:hover:not(:disabled) {
  background: #db2777;
}

.pam-refresh-button:disabled {
  background: #f9a8d4;
  cursor: not-allowed;
}
`;if(typeof document<"u"){const s=document.createElement("style");s.textContent=C,document.head.appendChild(s)}v.createRoot(document.getElementById("root")).render(e.jsx(S.StrictMode,{children:e.jsx(A,{children:e.jsx(k,{})})}));
