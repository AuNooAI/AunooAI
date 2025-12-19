import{r as t,j as e,as as j,au as T,ay as v,az as S,aw as A}from"./index-CrwZCP2i.js";import{u as w,e as P}from"./usePAM-CVSBWUQF.js";import"./alert-CbwmrB0G.js";import"./card-DL7hs4Ys.js";import"./badge-DkD14eOg.js";const k=()=>{const[s,c]=t.useState([]),[i,r]=t.useState(""),[d,p]=t.useState(!0),a=w(),[m,N]=t.useState("comprehensive"),[l,E]=t.useState("1_year"),[u,D]=t.useState(["T1","T2","T3","T4","T5"]),[h,G]=t.useState(90),[g,M]=t.useState(100),[f,x]=t.useState("executive");t.useEffect(()=>{b(),a.loadDefinitions(),a.loadCachedReport()},[]);const b=async()=>{try{const n=await fetch("/api/topics");if(n.ok){const o=await n.json();o.topics&&(c(o.topics),o.topics.length>0&&!i&&r(o.topics[0].name))}}catch(n){console.error("Failed to load topics:",n)}finally{p(!1)}},y=()=>{a.startGeneration({topic:"",analysisType:m,entityType:"publisher",timeHorizon:l,trendFocus:u,daysBack:h,articleLimit:g,model:"gpt-4.1-mini"})};return e.jsxs("div",{className:"pam-app",children:[e.jsx(j,{currentPage:"pam",topics:s,selectedTopic:i,onTopicChange:r}),e.jsx("main",{className:"pam-main-content",children:d?e.jsxs("div",{className:"pam-loading-container",children:[e.jsx("div",{className:"pam-loading-spinner"}),e.jsx("p",{children:"Loading PAM Dashboard..."})]}):e.jsxs("div",{className:"pam-dashboard-wrapper",children:[e.jsx("div",{className:"pam-standalone-toolbar",children:e.jsx("button",{onClick:y,disabled:a.isGenerating,className:"pam-refresh-button",children:a.isGenerating?"Analyzing...":"Generate Analysis"})}),e.jsx(P,{topic:i,isGenerating:a.isGenerating,currentStage:a.currentStage,stageProgress:a.stageProgress,data:a.data,error:a.error,activeView:f,onViewChange:x,onClearError:a.clearError})]})}),e.jsx(T,{})]})},C=`
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
