import{c as u,r as d,j as c,J as E,h as x}from"./index-C0_QUzAl.js";/**
 * @license lucide-react v0.487.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const I=[["path",{d:"M5 12h14",key:"1ays0h"}],["path",{d:"m12 5 7 7-7 7",key:"xquz4c"}]],Q=u("arrow-right",I);/**
 * @license lucide-react v0.487.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const A=[["path",{d:"M6 22V4a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v18Z",key:"1b4qmf"}],["path",{d:"M6 12H4a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h2",key:"i71pzd"}],["path",{d:"M18 9h2a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2h-2",key:"10jefs"}],["path",{d:"M10 6h4",key:"1itunk"}],["path",{d:"M10 10h4",key:"tcdvrf"}],["path",{d:"M10 14h4",key:"kelpxr"}],["path",{d:"M10 18h4",key:"1ulq68"}]],W=u("building-2",A);/**
 * @license lucide-react v0.487.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const R=[["circle",{cx:"12",cy:"12",r:"10",key:"1mglay"}],["path",{d:"M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20",key:"13o1zl"}],["path",{d:"M2 12h20",key:"9i4pu4"}]],Y=u("globe",R);/**
 * @license lucide-react v0.487.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const D=[["path",{d:"M5 12h14",key:"1ays0h"}]],ee=u("minus",D);/**
 * @license lucide-react v0.487.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const T=[["circle",{cx:"12",cy:"12",r:"10",key:"1mglay"}],["circle",{cx:"12",cy:"12",r:"6",key:"1vlfrh"}],["circle",{cx:"12",cy:"12",r:"2",key:"1c9p78"}]],re=u("target",T);/**
 * @license lucide-react v0.487.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const V=[["polyline",{points:"22 17 13.5 8.5 8.5 13.5 2 7",key:"1r2t7k"}],["polyline",{points:"16 17 22 17 22 11",key:"11uiuu"}]],te=u("trending-down",V);/**
 * @license lucide-react v0.487.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const z=[["path",{d:"M4 14a1 1 0 0 1-.78-1.63l9.9-10.2a.5.5 0 0 1 .86.46l-1.92 6.02A1 1 0 0 0 13 10h7a1 1 0 0 1 .78 1.63l-9.9 10.2a.5.5 0 0 1-.86-.46l1.92-6.02A1 1 0 0 0 11 14z",key:"1xq2db"}]],ae=u("zap",z);function L(e,r=[]){let n=[];function s(l,i){const a=d.createContext(i);a.displayName=l+"Context";const o=n.length;n=[...n,i];const p=f=>{const{scope:h,children:g,...v}=f,j=h?.[e]?.[o]||a,S=d.useMemo(()=>v,Object.values(v));return c.jsx(j.Provider,{value:S,children:g})};p.displayName=l+"Provider";function N(f,h){const g=h?.[e]?.[o]||a,v=d.useContext(g);if(v)return v;if(i!==void 0)return i;throw new Error(`\`${f}\` must be used within \`${l}\``)}return[p,N]}const t=()=>{const l=n.map(i=>d.createContext(i));return function(a){const o=a?.[e]||l;return d.useMemo(()=>({[`__scope${e}`]:{...a,[e]:o}}),[a,o])}};return t.scopeName=e,[s,O(t,...r)]}function O(...e){const r=e[0];if(e.length===1)return r;const n=()=>{const s=e.map(t=>({useScope:t(),scopeName:t.scopeName}));return function(l){const i=s.reduce((a,{useScope:o,scopeName:p})=>{const f=o(l)[`__scope${p}`];return{...a,...f}},{});return d.useMemo(()=>({[`__scope${r.scopeName}`]:i}),[i])}};return n.scopeName=r.scopeName,n}var q=["a","button","div","form","h2","h3","img","input","label","li","nav","ol","p","select","span","svg","ul"],$=q.reduce((e,r)=>{const n=E(`Primitive.${r}`),s=d.forwardRef((t,l)=>{const{asChild:i,...a}=t,o=i?n:r;return typeof window<"u"&&(window[Symbol.for("radix-ui")]=!0),c.jsx(o,{...a,ref:l})});return s.displayName=`Primitive.${r}`,{...e,[r]:s}},{}),y="Progress",b=100,[G]=L(y),[B,H]=G(y),k=d.forwardRef((e,r)=>{const{__scopeProgress:n,value:s=null,max:t,getValueLabel:l=Z,...i}=e;(t||t===0)&&!P(t)&&console.error(X(`${t}`,"Progress"));const a=P(t)?t:b;s!==null&&!_(s,a)&&console.error(F(`${s}`,"Progress"));const o=_(s,a)?s:null,p=m(o)?l(o,a):void 0;return c.jsx(B,{scope:n,value:o,max:a,children:c.jsx($.div,{"aria-valuemax":a,"aria-valuemin":0,"aria-valuenow":m(o)?o:void 0,"aria-valuetext":p,role:"progressbar","data-state":w(o,a),"data-value":o??void 0,"data-max":a,...i,ref:r})})});k.displayName=y;var M="ProgressIndicator",C=d.forwardRef((e,r)=>{const{__scopeProgress:n,...s}=e,t=H(M,n);return c.jsx($.div,{"data-state":w(t.value,t.max),"data-value":t.value??void 0,"data-max":t.max,...s,ref:r})});C.displayName=M;function Z(e,r){return`${Math.round(e/r*100)}%`}function w(e,r){return e==null?"indeterminate":e===r?"complete":"loading"}function m(e){return typeof e=="number"}function P(e){return m(e)&&!isNaN(e)&&e>0}function _(e,r){return m(e)&&!isNaN(e)&&e<=r&&e>=0}function X(e,r){return`Invalid prop \`max\` of value \`${e}\` supplied to \`${r}\`. Only numbers greater than 0 are valid max values. Defaulting to \`${b}\`.`}function F(e,r){return`Invalid prop \`value\` of value \`${e}\` supplied to \`${r}\`. The \`value\` prop must be:
  - a positive number
  - less than the value passed to \`max\` (or ${b} if no \`max\` prop is set)
  - \`null\` or \`undefined\` if the progress is indeterminate.

Defaulting to \`null\`.`}var J=k,U=C;function oe({className:e,value:r,...n}){return c.jsx(J,{"data-slot":"progress",className:x("bg-primary/20 relative h-2 w-full overflow-hidden rounded-full",e),...n,children:c.jsx(U,{"data-slot":"progress-indicator",className:"bg-primary h-full w-full flex-1 transition-all",style:{transform:`translateX(-${100-(r||0)}%)`}})})}function ne({className:e,...r}){return c.jsx("div",{"data-slot":"card",className:x("bg-card text-card-foreground flex flex-col gap-6 rounded-xl border",e),...r})}function se({className:e,...r}){return c.jsx("div",{"data-slot":"card-header",className:x("@container/card-header grid auto-rows-min grid-rows-[auto_auto] items-start gap-1.5 px-6 pt-6 has-data-[slot=card-action]:grid-cols-[1fr_auto] [.border-b]:pb-6",e),...r})}function ie({className:e,...r}){return c.jsx("h4",{"data-slot":"card-title",className:x("leading-none",e),...r})}function ce({className:e,...r}){return c.jsx("p",{"data-slot":"card-description",className:x("text-muted-foreground",e),...r})}function le({className:e,...r}){return c.jsx("div",{"data-slot":"card-content",className:x("px-6 [&:last-child]:pb-6",e),...r})}export{Q as A,W as B,ne as C,Y as G,ee as M,oe as P,re as T,ae as Z,le as a,se as b,ie as c,ce as d,te as e};
