import{d as p,r as u,j as c,V as E,m as f}from"./index-BJlqs742.js";/**
 * @license lucide-react v0.487.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const I=[["path",{d:"M6 22V4a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v18Z",key:"1b4qmf"}],["path",{d:"M6 12H4a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h2",key:"i71pzd"}],["path",{d:"M18 9h2a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2h-2",key:"10jefs"}],["path",{d:"M10 6h4",key:"1itunk"}],["path",{d:"M10 10h4",key:"tcdvrf"}],["path",{d:"M10 14h4",key:"kelpxr"}],["path",{d:"M10 18h4",key:"1ulq68"}]],K=p("building-2",I);/**
 * @license lucide-react v0.487.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const R=[["circle",{cx:"12",cy:"12",r:"10",key:"1mglay"}],["path",{d:"M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20",key:"13o1zl"}],["path",{d:"M2 12h20",key:"9i4pu4"}]],Q=p("globe",R);/**
 * @license lucide-react v0.487.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const V=[["path",{d:"M5 12h14",key:"1ays0h"}]],W=p("minus",V);/**
 * @license lucide-react v0.487.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const A=[["circle",{cx:"12",cy:"12",r:"10",key:"1mglay"}],["circle",{cx:"12",cy:"12",r:"6",key:"1vlfrh"}],["circle",{cx:"12",cy:"12",r:"2",key:"1c9p78"}]],Y=p("target",A);/**
 * @license lucide-react v0.487.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const D=[["polyline",{points:"22 17 13.5 8.5 8.5 13.5 2 7",key:"1r2t7k"}],["polyline",{points:"16 17 22 17 22 11",key:"11uiuu"}]],ee=p("trending-down",D);/**
 * @license lucide-react v0.487.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const T=[["path",{d:"M4 14a1 1 0 0 1-.78-1.63l9.9-10.2a.5.5 0 0 1 .86.46l-1.92 6.02A1 1 0 0 0 13 10h7a1 1 0 0 1 .78 1.63l-9.9 10.2a.5.5 0 0 1-.86-.46l1.92-6.02A1 1 0 0 0 11 14z",key:"1xq2db"}]],re=p("zap",T);function L(e,r=[]){let n=[];function s(l,i){const a=u.createContext(i);a.displayName=l+"Context";const o=n.length;n=[...n,i];const d=x=>{const{scope:g,children:h,...v}=x,j=g?.[e]?.[o]||a,S=u.useMemo(()=>v,Object.values(v));return c.jsx(j.Provider,{value:S,children:h})};d.displayName=l+"Provider";function N(x,g){const h=g?.[e]?.[o]||a,v=u.useContext(h);if(v)return v;if(i!==void 0)return i;throw new Error(`\`${x}\` must be used within \`${l}\``)}return[d,N]}const t=()=>{const l=n.map(i=>u.createContext(i));return function(a){const o=a?.[e]||l;return u.useMemo(()=>({[`__scope${e}`]:{...a,[e]:o}}),[a,o])}};return t.scopeName=e,[s,O(t,...r)]}function O(...e){const r=e[0];if(e.length===1)return r;const n=()=>{const s=e.map(t=>({useScope:t(),scopeName:t.scopeName}));return function(l){const i=s.reduce((a,{useScope:o,scopeName:d})=>{const x=o(l)[`__scope${d}`];return{...a,...x}},{});return u.useMemo(()=>({[`__scope${r.scopeName}`]:i}),[i])}};return n.scopeName=r.scopeName,n}var z=["a","button","div","form","h2","h3","img","input","label","li","nav","ol","p","select","span","svg","ul"],$=z.reduce((e,r)=>{const n=E(`Primitive.${r}`),s=u.forwardRef((t,l)=>{const{asChild:i,...a}=t,o=i?n:r;return typeof window<"u"&&(window[Symbol.for("radix-ui")]=!0),c.jsx(o,{...a,ref:l})});return s.displayName=`Primitive.${r}`,{...e,[r]:s}},{}),y="Progress",b=100,[G]=L(y),[q,B]=G(y),M=u.forwardRef((e,r)=>{const{__scopeProgress:n,value:s=null,max:t,getValueLabel:l=H,...i}=e;(t||t===0)&&!P(t)&&console.error(Z(`${t}`,"Progress"));const a=P(t)?t:b;s!==null&&!_(s,a)&&console.error(X(`${s}`,"Progress"));const o=_(s,a)?s:null,d=m(o)?l(o,a):void 0;return c.jsx(q,{scope:n,value:o,max:a,children:c.jsx($.div,{"aria-valuemax":a,"aria-valuemin":0,"aria-valuenow":m(o)?o:void 0,"aria-valuetext":d,role:"progressbar","data-state":w(o,a),"data-value":o??void 0,"data-max":a,...i,ref:r})})});M.displayName=y;var k="ProgressIndicator",C=u.forwardRef((e,r)=>{const{__scopeProgress:n,...s}=e,t=B(k,n);return c.jsx($.div,{"data-state":w(t.value,t.max),"data-value":t.value??void 0,"data-max":t.max,...s,ref:r})});C.displayName=k;function H(e,r){return`${Math.round(e/r*100)}%`}function w(e,r){return e==null?"indeterminate":e===r?"complete":"loading"}function m(e){return typeof e=="number"}function P(e){return m(e)&&!isNaN(e)&&e>0}function _(e,r){return m(e)&&!isNaN(e)&&e<=r&&e>=0}function Z(e,r){return`Invalid prop \`max\` of value \`${e}\` supplied to \`${r}\`. Only numbers greater than 0 are valid max values. Defaulting to \`${b}\`.`}function X(e,r){return`Invalid prop \`value\` of value \`${e}\` supplied to \`${r}\`. The \`value\` prop must be:
  - a positive number
  - less than the value passed to \`max\` (or ${b} if no \`max\` prop is set)
  - \`null\` or \`undefined\` if the progress is indeterminate.

Defaulting to \`null\`.`}var F=M,U=C;function te({className:e,value:r,...n}){return c.jsx(F,{"data-slot":"progress",className:f("bg-primary/20 relative h-2 w-full overflow-hidden rounded-full",e),...n,children:c.jsx(U,{"data-slot":"progress-indicator",className:"bg-primary h-full w-full flex-1 transition-all",style:{transform:`translateX(-${100-(r||0)}%)`}})})}function ae({className:e,...r}){return c.jsx("div",{"data-slot":"card",className:f("bg-card text-card-foreground flex flex-col gap-6 rounded-xl border",e),...r})}function oe({className:e,...r}){return c.jsx("div",{"data-slot":"card-header",className:f("@container/card-header grid auto-rows-min grid-rows-[auto_auto] items-start gap-1.5 px-6 pt-6 has-data-[slot=card-action]:grid-cols-[1fr_auto] [.border-b]:pb-6",e),...r})}function ne({className:e,...r}){return c.jsx("h4",{"data-slot":"card-title",className:f("leading-none",e),...r})}function se({className:e,...r}){return c.jsx("p",{"data-slot":"card-description",className:f("text-muted-foreground",e),...r})}function ie({className:e,...r}){return c.jsx("div",{"data-slot":"card-content",className:f("px-6 [&:last-child]:pb-6",e),...r})}export{K as B,ae as C,Q as G,W as M,te as P,Y as T,re as Z,ie as a,oe as b,ne as c,se as d,ee as e};
