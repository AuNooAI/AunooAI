import{d as u,j as c,p as f,r as d,_ as E}from"./index-DDavbYvV.js";/**
 * @license lucide-react v0.487.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const I=[["path",{d:"M12 7v14",key:"1akyts"}],["path",{d:"M3 18a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h5a4 4 0 0 1 4 4 4 4 0 0 1 4-4h5a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1h-6a3 3 0 0 0-3 3 3 3 0 0 0-3-3z",key:"ruj8y"}]],Q=u("book-open",I);/**
 * @license lucide-react v0.487.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const R=[["path",{d:"M6 22V4a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v18Z",key:"1b4qmf"}],["path",{d:"M6 12H4a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h2",key:"i71pzd"}],["path",{d:"M18 9h2a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2h-2",key:"10jefs"}],["path",{d:"M10 6h4",key:"1itunk"}],["path",{d:"M10 10h4",key:"tcdvrf"}],["path",{d:"M10 14h4",key:"kelpxr"}],["path",{d:"M10 18h4",key:"1ulq68"}]],W=u("building-2",R);/**
 * @license lucide-react v0.487.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const V=[["circle",{cx:"12",cy:"12",r:"10",key:"1mglay"}],["path",{d:"M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20",key:"13o1zl"}],["path",{d:"M2 12h20",key:"9i4pu4"}]],Y=u("globe",V);/**
 * @license lucide-react v0.487.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const A=[["path",{d:"M5 12h14",key:"1ays0h"}]],ee=u("minus",A);/**
 * @license lucide-react v0.487.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const D=[["circle",{cx:"12",cy:"12",r:"10",key:"1mglay"}],["circle",{cx:"12",cy:"12",r:"6",key:"1vlfrh"}],["circle",{cx:"12",cy:"12",r:"2",key:"1c9p78"}]],te=u("target",D);/**
 * @license lucide-react v0.487.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const T=[["polyline",{points:"22 17 13.5 8.5 8.5 13.5 2 7",key:"1r2t7k"}],["polyline",{points:"16 17 22 17 22 11",key:"11uiuu"}]],re=u("trending-down",T);/**
 * @license lucide-react v0.487.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const O=[["path",{d:"M4 14a1 1 0 0 1-.78-1.63l9.9-10.2a.5.5 0 0 1 .86.46l-1.92 6.02A1 1 0 0 0 13 10h7a1 1 0 0 1 .78 1.63l-9.9 10.2a.5.5 0 0 1-.86-.46l1.92-6.02A1 1 0 0 0 11 14z",key:"1xq2db"}]],ae=u("zap",O);function oe({className:e,...t}){return c.jsx("div",{"data-slot":"card",className:f("bg-card text-card-foreground flex flex-col gap-6 rounded-xl border",e),...t})}function ne({className:e,...t}){return c.jsx("div",{"data-slot":"card-header",className:f("@container/card-header grid auto-rows-min grid-rows-[auto_auto] items-start gap-1.5 px-6 pt-6 has-data-[slot=card-action]:grid-cols-[1fr_auto] [.border-b]:pb-6",e),...t})}function se({className:e,...t}){return c.jsx("h4",{"data-slot":"card-title",className:f("leading-none",e),...t})}function ie({className:e,...t}){return c.jsx("p",{"data-slot":"card-description",className:f("text-muted-foreground",e),...t})}function ce({className:e,...t}){return c.jsx("div",{"data-slot":"card-content",className:f("px-6 [&:last-child]:pb-6",e),...t})}function z(e,t=[]){let n=[];function s(l,i){const a=d.createContext(i);a.displayName=l+"Context";const o=n.length;n=[...n,i];const p=v=>{const{scope:h,children:g,...x}=v,j=h?.[e]?.[o]||a,S=d.useMemo(()=>x,Object.values(x));return c.jsx(j.Provider,{value:S,children:g})};p.displayName=l+"Provider";function N(v,h){const g=h?.[e]?.[o]||a,x=d.useContext(g);if(x)return x;if(i!==void 0)return i;throw new Error(`\`${v}\` must be used within \`${l}\``)}return[p,N]}const r=()=>{const l=n.map(i=>d.createContext(i));return function(a){const o=a?.[e]||l;return d.useMemo(()=>({[`__scope${e}`]:{...a,[e]:o}}),[a,o])}};return r.scopeName=e,[s,L(r,...t)]}function L(...e){const t=e[0];if(e.length===1)return t;const n=()=>{const s=e.map(r=>({useScope:r(),scopeName:r.scopeName}));return function(l){const i=s.reduce((a,{useScope:o,scopeName:p})=>{const v=o(l)[`__scope${p}`];return{...a,...v}},{});return d.useMemo(()=>({[`__scope${t.scopeName}`]:i}),[i])}};return n.scopeName=t.scopeName,n}var B=["a","button","div","form","h2","h3","img","input","label","li","nav","ol","p","select","span","svg","ul"],k=B.reduce((e,t)=>{const n=E(`Primitive.${t}`),s=d.forwardRef((r,l)=>{const{asChild:i,...a}=r,o=i?n:t;return typeof window<"u"&&(window[Symbol.for("radix-ui")]=!0),c.jsx(o,{...a,ref:l})});return s.displayName=`Primitive.${t}`,{...e,[t]:s}},{}),y="Progress",b=100,[G]=z(y),[q,H]=G(y),M=d.forwardRef((e,t)=>{const{__scopeProgress:n,value:s=null,max:r,getValueLabel:l=Z,...i}=e;(r||r===0)&&!_(r)&&console.error(X(`${r}`,"Progress"));const a=_(r)?r:b;s!==null&&!P(s,a)&&console.error(F(`${s}`,"Progress"));const o=P(s,a)?s:null,p=m(o)?l(o,a):void 0;return c.jsx(q,{scope:n,value:o,max:a,children:c.jsx(k.div,{"aria-valuemax":a,"aria-valuemin":0,"aria-valuenow":m(o)?o:void 0,"aria-valuetext":p,role:"progressbar","data-state":w(o,a),"data-value":o??void 0,"data-max":a,...i,ref:t})})});M.displayName=y;var $="ProgressIndicator",C=d.forwardRef((e,t)=>{const{__scopeProgress:n,...s}=e,r=H($,n);return c.jsx(k.div,{"data-state":w(r.value,r.max),"data-value":r.value??void 0,"data-max":r.max,...s,ref:t})});C.displayName=$;function Z(e,t){return`${Math.round(e/t*100)}%`}function w(e,t){return e==null?"indeterminate":e===t?"complete":"loading"}function m(e){return typeof e=="number"}function _(e){return m(e)&&!isNaN(e)&&e>0}function P(e,t){return m(e)&&!isNaN(e)&&e<=t&&e>=0}function X(e,t){return`Invalid prop \`max\` of value \`${e}\` supplied to \`${t}\`. Only numbers greater than 0 are valid max values. Defaulting to \`${b}\`.`}function F(e,t){return`Invalid prop \`value\` of value \`${e}\` supplied to \`${t}\`. The \`value\` prop must be:
  - a positive number
  - less than the value passed to \`max\` (or ${b} if no \`max\` prop is set)
  - \`null\` or \`undefined\` if the progress is indeterminate.

Defaulting to \`null\`.`}var U=M,J=C;function le({className:e,value:t,...n}){return c.jsx(U,{"data-slot":"progress",className:f("bg-primary/20 relative h-2 w-full overflow-hidden rounded-full",e),...n,children:c.jsx(J,{"data-slot":"progress-indicator",className:"bg-primary h-full w-full flex-1 transition-all",style:{transform:`translateX(-${100-(t||0)}%)`}})})}export{W as B,oe as C,Y as G,ee as M,le as P,te as T,ae as Z,ce as a,ne as b,se as c,ie as d,re as e,Q as f};
