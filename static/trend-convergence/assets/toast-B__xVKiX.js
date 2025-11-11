function t(n,e="info",a=5e3){let s=document.getElementById("toastContainer");s||(s=document.createElement("div"),s.id="toastContainer",document.body.appendChild(s));const o=document.createElement("div");o.className=`toast ${e}`;const c={success:"fas fa-check-circle",error:"fas fa-exclamation-circle",warning:"fas fa-exclamation-triangle",info:"fas fa-info-circle"};o.innerHTML=`
    <i class="${c[e]}"></i>
    <span>${n}</span>
  `,s.appendChild(o),setTimeout(()=>o.classList.add("show"),10),setTimeout(()=>{o.classList.remove("show"),setTimeout(()=>o.remove(),300)},a)}function i(n,e){t(n,"success",e)}function r(n,e){t(n,"error",e)}function f(n,e){t(n,"warning",e)}export{r as showError,i as showSuccess,t as showToast,f as showWarning};
