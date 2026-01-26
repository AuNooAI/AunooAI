import{d,r as u,j as l,Z as j,p as E}from"./index-DkU67ToI.js";/**
 * @license lucide-react v0.487.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const I=[["path",{d:"M5 12h14",key:"1ays0h"}],["path",{d:"m12 5 7 7-7 7",key:"xquz4c"}]],Q=d("arrow-right",I);/**
 * @license lucide-react v0.487.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const A=[["path",{d:"M12 7v14",key:"1akyts"}],["path",{d:"M3 18a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h5a4 4 0 0 1 4 4 4 4 0 0 1 4-4h5a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1h-6a3 3 0 0 0-3 3 3 3 0 0 0-3-3z",key:"ruj8y"}]],W=d("book-open",A);/**
 * @license lucide-react v0.487.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const R=[["path",{d:"M6 22V4a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v18Z",key:"1b4qmf"}],["path",{d:"M6 12H4a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h2",key:"i71pzd"}],["path",{d:"M18 9h2a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2h-2",key:"10jefs"}],["path",{d:"M10 6h4",key:"1itunk"}],["path",{d:"M10 10h4",key:"tcdvrf"}],["path",{d:"M10 14h4",key:"kelpxr"}],["path",{d:"M10 18h4",key:"1ulq68"}]],Y=d("building-2",R);/**
 * @license lucide-react v0.487.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const V=[["path",{d:"M5 12h14",key:"1ays0h"}]],ee=d("minus",V);/**
 * @license lucide-react v0.487.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const D=[["circle",{cx:"12",cy:"12",r:"10",key:"1mglay"}],["circle",{cx:"12",cy:"12",r:"6",key:"1vlfrh"}],["circle",{cx:"12",cy:"12",r:"2",key:"1c9p78"}]],re=d("target",D);/**
 * @license lucide-react v0.487.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const O=[["polyline",{points:"22 17 13.5 8.5 8.5 13.5 2 7",key:"1r2t7k"}],["polyline",{points:"16 17 22 17 22 11",key:"11uiuu"}]],te=d("trending-down",O);/**
 * @license lucide-react v0.487.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const T=[["path",{d:"M4 14a1 1 0 0 1-.78-1.63l9.9-10.2a.5.5 0 0 1 .86.46l-1.92 6.02A1 1 0 0 0 13 10h7a1 1 0 0 1 .78 1.63l-9.9 10.2a.5.5 0 0 1-.86-.46l1.92-6.02A1 1 0 0 0 11 14z",key:"1xq2db"}]],oe=d("zap",T);function z(e,r=[]){let n=[];function s(c,i){const o=u.createContext(i);o.displayName=c+"Context";const a=n.length;n=[...n,i];const p=v=>{const{scope:m,children:x,...f}=v,S=m?.[e]?.[a]||o,C=u.useMemo(()=>f,Object.values(f));return l.jsx(S.Provider,{value:C,children:x})};p.displayName=c+"Provider";function P(v,m){const x=m?.[e]?.[a]||o,f=u.useContext(x);if(f)return f;if(i!==void 0)return i;throw new Error(`\`${v}\` must be used within \`${c}\``)}return[p,P]}const t=()=>{const c=n.map(i=>u.createContext(i));return function(o){const a=o?.[e]||c;return u.useMemo(()=>({[`__scope${e}`]:{...o,[e]:a}}),[o,a])}};return t.scopeName=e,[s,L(t,...r)]}function L(...e){const r=e[0];if(e.length===1)return r;const n=()=>{const s=e.map(t=>({useScope:t(),scopeName:t.scopeName}));return function(c){const i=s.reduce((o,{useScope:a,scopeName:p})=>{const v=a(c)[`__scope${p}`];return{...o,...v}},{});return u.useMemo(()=>({[`__scope${r.scopeName}`]:i}),[i])}};return n.scopeName=r.scopeName,n}var q=["a","button","div","form","h2","h3","img","input","label","li","nav","ol","p","select","span","svg","ul"],N=q.reduce((e,r)=>{const n=j(`Primitive.${r}`),s=u.forwardRef((t,c)=>{const{asChild:i,...o}=t,a=i?n:r;return typeof window<"u"&&(window[Symbol.for("radix-ui")]=!0),l.jsx(a,{...o,ref:c})});return s.displayName=`Primitive.${r}`,{...e,[r]:s}},{}),g="Progress",y=100,[B]=z(g),[Z,G]=B(g),b=u.forwardRef((e,r)=>{const{__scopeProgress:n,value:s=null,max:t,getValueLabel:c=H,...i}=e;(t||t===0)&&!_(t)&&console.error(X(`${t}`,"Progress"));const o=_(t)?t:y;s!==null&&!k(s,o)&&console.error(F(`${s}`,"Progress"));const a=k(s,o)?s:null,p=h(a)?c(a,o):void 0;return l.jsx(Z,{scope:n,value:a,max:o,children:l.jsx(N.div,{"aria-valuemax":o,"aria-valuemin":0,"aria-valuenow":h(a)?a:void 0,"aria-valuetext":p,role:"progressbar","data-state":w(a,o),"data-value":a??void 0,"data-max":o,...i,ref:r})})});b.displayName=g;var $="ProgressIndicator",M=u.forwardRef((e,r)=>{const{__scopeProgress:n,...s}=e,t=G($,n);return l.jsx(N.div,{"data-state":w(t.value,t.max),"data-value":t.value??void 0,"data-max":t.max,...s,ref:r})});M.displayName=$;function H(e,r){return`${Math.round(e/r*100)}%`}function w(e,r){return e==null?"indeterminate":e===r?"complete":"loading"}function h(e){return typeof e=="number"}function _(e){return h(e)&&!isNaN(e)&&e>0}function k(e,r){return h(e)&&!isNaN(e)&&e<=r&&e>=0}function X(e,r){return`Invalid prop \`max\` of value \`${e}\` supplied to \`${r}\`. Only numbers greater than 0 are valid max values. Defaulting to \`${y}\`.`}function F(e,r){return`Invalid prop \`value\` of value \`${e}\` supplied to \`${r}\`. The \`value\` prop must be:
  - a positive number
  - less than the value passed to \`max\` (or ${y} if no \`max\` prop is set)
  - \`null\` or \`undefined\` if the progress is indeterminate.

Defaulting to \`null\`.`}var U=b,J=M;function ae({className:e,value:r,...n}){return l.jsx(U,{"data-slot":"progress",className:E("bg-primary/20 relative h-2 w-full overflow-hidden rounded-full",e),...n,children:l.jsx(J,{"data-slot":"progress-indicator",className:"bg-primary h-full w-full flex-1 transition-all",style:{transform:`translateX(-${100-(r||0)}%)`}})})}export{Q as A,Y as B,ee as M,ae as P,re as T,oe as Z,te as a,W as b};
