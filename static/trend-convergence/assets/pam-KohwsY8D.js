import{r as t,j as e,z as T,J as j,K as S}from"./index-DdtWfgQx.js";import{u as v,e as A}from"./usePAM-SqO77ZZJ.js";import"./alert-DU6rgL7q.js";import"./card-B-GnX200.js";import"./badge-B3LzrrQd.js";const w=()=>{const[n,c]=t.useState([]),[i,r]=t.useState(""),[d,p]=t.useState(!0),a=v(),[m,k]=t.useState("comprehensive"),[l,N]=t.useState("1_year"),[u,C]=t.useState(["T1","T2","T3","T4","T5"]),[g,E]=t.useState(90),[h,D]=t.useState(100),[f,x]=t.useState("executive");t.useEffect(()=>{b(),a.loadDefinitions(),a.loadCachedReport()},[]);const b=async()=>{try{const o=await fetch("/api/topics");if(o.ok){const s=await o.json();s.topics&&(c(s.topics),s.topics.length>0&&!i&&r(s.topics[0].name))}}catch(o){console.error("Failed to load topics:",o)}finally{p(!1)}},y=()=>{a.startGeneration({topic:"",analysisType:m,entityType:"publisher",timeHorizon:l,trendFocus:u,daysBack:g,articleLimit:h,model:"gpt-4.1-mini"})};return e.jsxs("div",{className:"pam-app",children:[e.jsx(T,{currentPage:"pam",topics:n,selectedTopic:i,onTopicChange:r}),e.jsx("main",{className:"pam-main-content",children:d?e.jsxs("div",{className:"pam-loading-container",children:[e.jsx("div",{className:"pam-loading-spinner"}),e.jsx("p",{children:"Loading PAM Dashboard..."})]}):e.jsxs("div",{className:"pam-dashboard-wrapper",children:[e.jsx("div",{className:"pam-standalone-toolbar",children:e.jsx("button",{onClick:y,disabled:a.isGenerating,className:"pam-refresh-button",children:a.isGenerating?"Analyzing...":"Generate Analysis"})}),e.jsx(A,{topic:i,isGenerating:a.isGenerating,currentStage:a.currentStage,stageProgress:a.stageProgress,data:a.data,error:a.error,activeView:f,onViewChange:x,onClearError:a.clearError})]})})]})},P=`
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
`;if(typeof document<"u"){const n=document.createElement("style");n.textContent=P,document.head.appendChild(n)}j.createRoot(document.getElementById("root")).render(e.jsx(S.StrictMode,{children:e.jsx(w,{})}));
