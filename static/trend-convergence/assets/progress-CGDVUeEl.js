import{d as l,r as u,j as d,Z as j,p as E}from"./index-BF4tu-qZ.js";/**
 * @license lucide-react v0.487.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const I=[["path",{d:"M5 12h14",key:"1ays0h"}],["path",{d:"m12 5 7 7-7 7",key:"xquz4c"}]],W=l("arrow-right",I);/**
 * @license lucide-react v0.487.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const A=[["path",{d:"M12 7v14",key:"1akyts"}],["path",{d:"M3 18a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h5a4 4 0 0 1 4 4 4 4 0 0 1 4-4h5a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1h-6a3 3 0 0 0-3 3 3 3 0 0 0-3-3z",key:"ruj8y"}]],Y=l("book-open",A);/**
 * @license lucide-react v0.487.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const R=[["path",{d:"M6 22V4a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v18Z",key:"1b4qmf"}],["path",{d:"M6 12H4a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h2",key:"i71pzd"}],["path",{d:"M18 9h2a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2h-2",key:"10jefs"}],["path",{d:"M10 6h4",key:"1itunk"}],["path",{d:"M10 10h4",key:"tcdvrf"}],["path",{d:"M10 14h4",key:"kelpxr"}],["path",{d:"M10 18h4",key:"1ulq68"}]],ee=l("building-2",R);/**
 * @license lucide-react v0.487.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const V=[["circle",{cx:"12",cy:"12",r:"10",key:"1mglay"}],["path",{d:"M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20",key:"13o1zl"}],["path",{d:"M2 12h20",key:"9i4pu4"}]],te=l("globe",V);/**
 * @license lucide-react v0.487.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const z=[["path",{d:"M5 12h14",key:"1ays0h"}]],re=l("minus",z);/**
 * @license lucide-react v0.487.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const D=[["circle",{cx:"12",cy:"12",r:"10",key:"1mglay"}],["circle",{cx:"12",cy:"12",r:"6",key:"1vlfrh"}],["circle",{cx:"12",cy:"12",r:"2",key:"1c9p78"}]],oe=l("target",D);/**
 * @license lucide-react v0.487.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const O=[["polyline",{points:"22 17 13.5 8.5 8.5 13.5 2 7",key:"1r2t7k"}],["polyline",{points:"16 17 22 17 22 11",key:"11uiuu"}]],ae=l("trending-down",O);/**
 * @license lucide-react v0.487.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const T=[["path",{d:"M4 14a1 1 0 0 1-.78-1.63l9.9-10.2a.5.5 0 0 1 .86.46l-1.92 6.02A1 1 0 0 0 13 10h7a1 1 0 0 1 .78 1.63l-9.9 10.2a.5.5 0 0 1-.86-.46l1.92-6.02A1 1 0 0 0 11 14z",key:"1xq2db"}]],ne=l("zap",T);function L(e,t=[]){let n=[];function s(c,i){const o=u.createContext(i);o.displayName=c+"Context";const a=n.length;n=[...n,i];const p=v=>{const{scope:m,children:x,...h}=v,S=m?.[e]?.[a]||o,C=u.useMemo(()=>h,Object.values(h));return d.jsx(S.Provider,{value:C,children:x})};p.displayName=c+"Provider";function P(v,m){const x=m?.[e]?.[a]||o,h=u.useContext(x);if(h)return h;if(i!==void 0)return i;throw new Error(`\`${v}\` must be used within \`${c}\``)}return[p,P]}const r=()=>{const c=n.map(i=>u.createContext(i));return function(o){const a=o?.[e]||c;return u.useMemo(()=>({[`__scope${e}`]:{...o,[e]:a}}),[o,a])}};return r.scopeName=e,[s,q(r,...t)]}function q(...e){const t=e[0];if(e.length===1)return t;const n=()=>{const s=e.map(r=>({useScope:r(),scopeName:r.scopeName}));return function(c){const i=s.reduce((o,{useScope:a,scopeName:p})=>{const v=a(c)[`__scope${p}`];return{...o,...v}},{});return u.useMemo(()=>({[`__scope${t.scopeName}`]:i}),[i])}};return n.scopeName=t.scopeName,n}var B=["a","button","div","form","h2","h3","img","input","label","li","nav","ol","p","select","span","svg","ul"],b=B.reduce((e,t)=>{const n=j(`Primitive.${t}`),s=u.forwardRef((r,c)=>{const{asChild:i,...o}=r,a=i?n:t;return typeof window<"u"&&(window[Symbol.for("radix-ui")]=!0),d.jsx(a,{...o,ref:c})});return s.displayName=`Primitive.${t}`,{...e,[t]:s}},{}),y="Progress",g=100,[G]=L(y),[Z,H]=G(y),N=u.forwardRef((e,t)=>{const{__scopeProgress:n,value:s=null,max:r,getValueLabel:c=X,...i}=e;(r||r===0)&&!_(r)&&console.error(F(`${r}`,"Progress"));const o=_(r)?r:g;s!==null&&!k(s,o)&&console.error(U(`${s}`,"Progress"));const a=k(s,o)?s:null,p=f(a)?c(a,o):void 0;return d.jsx(Z,{scope:n,value:a,max:o,children:d.jsx(b.div,{"aria-valuemax":o,"aria-valuemin":0,"aria-valuenow":f(a)?a:void 0,"aria-valuetext":p,role:"progressbar","data-state":w(a,o),"data-value":a??void 0,"data-max":o,...i,ref:t})})});N.displayName=y;var M="ProgressIndicator",$=u.forwardRef((e,t)=>{const{__scopeProgress:n,...s}=e,r=H(M,n);return d.jsx(b.div,{"data-state":w(r.value,r.max),"data-value":r.value??void 0,"data-max":r.max,...s,ref:t})});$.displayName=M;function X(e,t){return`${Math.round(e/t*100)}%`}function w(e,t){return e==null?"indeterminate":e===t?"complete":"loading"}function f(e){return typeof e=="number"}function _(e){return f(e)&&!isNaN(e)&&e>0}function k(e,t){return f(e)&&!isNaN(e)&&e<=t&&e>=0}function F(e,t){return`Invalid prop \`max\` of value \`${e}\` supplied to \`${t}\`. Only numbers greater than 0 are valid max values. Defaulting to \`${g}\`.`}function U(e,t){return`Invalid prop \`value\` of value \`${e}\` supplied to \`${t}\`. The \`value\` prop must be:
  - a positive number
  - less than the value passed to \`max\` (or ${g} if no \`max\` prop is set)
  - \`null\` or \`undefined\` if the progress is indeterminate.

Defaulting to \`null\`.`}var J=N,K=$;function se({className:e,value:t,...n}){return d.jsx(J,{"data-slot":"progress",className:E("bg-primary/20 relative h-2 w-full overflow-hidden rounded-full",e),...n,children:d.jsx(K,{"data-slot":"progress-indicator",className:"bg-primary h-full w-full flex-1 transition-all",style:{transform:`translateX(-${100-(t||0)}%)`}})})}export{W as A,ee as B,te as G,re as M,se as P,oe as T,ne as Z,ae as a,Y as b};
