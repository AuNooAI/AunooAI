import{d,r as u,j as l,Z as j,p as E}from"./index-DlIXuvD1.js";/**
 * @license lucide-react v0.487.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const I=[["path",{d:"M12 7v14",key:"1akyts"}],["path",{d:"M3 18a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h5a4 4 0 0 1 4 4 4 4 0 0 1 4-4h5a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1h-6a3 3 0 0 0-3 3 3 3 0 0 0-3-3z",key:"ruj8y"}]],Q=d("book-open",I);/**
 * @license lucide-react v0.487.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const R=[["path",{d:"M6 22V4a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v18Z",key:"1b4qmf"}],["path",{d:"M6 12H4a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h2",key:"i71pzd"}],["path",{d:"M18 9h2a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2h-2",key:"10jefs"}],["path",{d:"M10 6h4",key:"1itunk"}],["path",{d:"M10 10h4",key:"tcdvrf"}],["path",{d:"M10 14h4",key:"kelpxr"}],["path",{d:"M10 18h4",key:"1ulq68"}]],W=d("building-2",R);/**
 * @license lucide-react v0.487.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const V=[["circle",{cx:"12",cy:"12",r:"10",key:"1mglay"}],["path",{d:"M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20",key:"13o1zl"}],["path",{d:"M2 12h20",key:"9i4pu4"}]],Y=d("globe",V);/**
 * @license lucide-react v0.487.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const A=[["path",{d:"M5 12h14",key:"1ays0h"}]],ee=d("minus",A);/**
 * @license lucide-react v0.487.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const D=[["circle",{cx:"12",cy:"12",r:"10",key:"1mglay"}],["circle",{cx:"12",cy:"12",r:"6",key:"1vlfrh"}],["circle",{cx:"12",cy:"12",r:"2",key:"1c9p78"}]],te=d("target",D);/**
 * @license lucide-react v0.487.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const O=[["polyline",{points:"22 17 13.5 8.5 8.5 13.5 2 7",key:"1r2t7k"}],["polyline",{points:"16 17 22 17 22 11",key:"11uiuu"}]],re=d("trending-down",O);/**
 * @license lucide-react v0.487.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const T=[["path",{d:"M4 14a1 1 0 0 1-.78-1.63l9.9-10.2a.5.5 0 0 1 .86.46l-1.92 6.02A1 1 0 0 0 13 10h7a1 1 0 0 1 .78 1.63l-9.9 10.2a.5.5 0 0 1-.86-.46l1.92-6.02A1 1 0 0 0 11 14z",key:"1xq2db"}]],oe=d("zap",T);function z(e,t=[]){let n=[];function s(c,i){const o=u.createContext(i);o.displayName=c+"Context";const a=n.length;n=[...n,i];const p=v=>{const{scope:x,children:h,...f}=v,S=x?.[e]?.[a]||o,C=u.useMemo(()=>f,Object.values(f));return l.jsx(S.Provider,{value:C,children:h})};p.displayName=c+"Provider";function P(v,x){const h=x?.[e]?.[a]||o,f=u.useContext(h);if(f)return f;if(i!==void 0)return i;throw new Error(`\`${v}\` must be used within \`${c}\``)}return[p,P]}const r=()=>{const c=n.map(i=>u.createContext(i));return function(o){const a=o?.[e]||c;return u.useMemo(()=>({[`__scope${e}`]:{...o,[e]:a}}),[o,a])}};return r.scopeName=e,[s,L(r,...t)]}function L(...e){const t=e[0];if(e.length===1)return t;const n=()=>{const s=e.map(r=>({useScope:r(),scopeName:r.scopeName}));return function(c){const i=s.reduce((o,{useScope:a,scopeName:p})=>{const v=a(c)[`__scope${p}`];return{...o,...v}},{});return u.useMemo(()=>({[`__scope${t.scopeName}`]:i}),[i])}};return n.scopeName=t.scopeName,n}var B=["a","button","div","form","h2","h3","img","input","label","li","nav","ol","p","select","span","svg","ul"],k=B.reduce((e,t)=>{const n=j(`Primitive.${t}`),s=u.forwardRef((r,c)=>{const{asChild:i,...o}=r,a=i?n:t;return typeof window<"u"&&(window[Symbol.for("radix-ui")]=!0),l.jsx(a,{...o,ref:c})});return s.displayName=`Primitive.${t}`,{...e,[t]:s}},{}),y="Progress",g=100,[G]=z(y),[Z,q]=G(y),N=u.forwardRef((e,t)=>{const{__scopeProgress:n,value:s=null,max:r,getValueLabel:c=H,...i}=e;(r||r===0)&&!_(r)&&console.error(X(`${r}`,"Progress"));const o=_(r)?r:g;s!==null&&!b(s,o)&&console.error(F(`${s}`,"Progress"));const a=b(s,o)?s:null,p=m(a)?c(a,o):void 0;return l.jsx(Z,{scope:n,value:a,max:o,children:l.jsx(k.div,{"aria-valuemax":o,"aria-valuemin":0,"aria-valuenow":m(a)?a:void 0,"aria-valuetext":p,role:"progressbar","data-state":w(a,o),"data-value":a??void 0,"data-max":o,...i,ref:t})})});N.displayName=y;var M="ProgressIndicator",$=u.forwardRef((e,t)=>{const{__scopeProgress:n,...s}=e,r=q(M,n);return l.jsx(k.div,{"data-state":w(r.value,r.max),"data-value":r.value??void 0,"data-max":r.max,...s,ref:t})});$.displayName=M;function H(e,t){return`${Math.round(e/t*100)}%`}function w(e,t){return e==null?"indeterminate":e===t?"complete":"loading"}function m(e){return typeof e=="number"}function _(e){return m(e)&&!isNaN(e)&&e>0}function b(e,t){return m(e)&&!isNaN(e)&&e<=t&&e>=0}function X(e,t){return`Invalid prop \`max\` of value \`${e}\` supplied to \`${t}\`. Only numbers greater than 0 are valid max values. Defaulting to \`${g}\`.`}function F(e,t){return`Invalid prop \`value\` of value \`${e}\` supplied to \`${t}\`. The \`value\` prop must be:
  - a positive number
  - less than the value passed to \`max\` (or ${g} if no \`max\` prop is set)
  - \`null\` or \`undefined\` if the progress is indeterminate.

Defaulting to \`null\`.`}var U=N,J=$;function ae({className:e,value:t,...n}){return l.jsx(U,{"data-slot":"progress",className:E("bg-primary/20 relative h-2 w-full overflow-hidden rounded-full",e),...n,children:l.jsx(J,{"data-slot":"progress-indicator",className:"bg-primary h-full w-full flex-1 transition-all",style:{transform:`translateX(-${100-(t||0)}%)`}})})}export{W as B,Y as G,ee as M,ae as P,te as T,oe as Z,re as a,Q as b};
