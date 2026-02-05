import{d as g,r as c,j as l,Z as E,A as I}from"./index-CwVQK5p4.js";/**
 * @license lucide-react v0.487.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const R=[["path",{d:"M5 12h14",key:"1ays0h"}],["path",{d:"m12 5 7 7-7 7",key:"xquz4c"}]],U=g("arrow-right",R);/**
 * @license lucide-react v0.487.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const A=[["path",{d:"M5 12h14",key:"1ays0h"}]],Z=g("minus",A);/**
 * @license lucide-react v0.487.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const k=[["polyline",{points:"22 17 13.5 8.5 8.5 13.5 2 7",key:"1r2t7k"}],["polyline",{points:"16 17 22 17 22 11",key:"11uiuu"}]],J=g("trending-down",k);function D(e,r=[]){let s=[];function a(u,i){const o=c.createContext(i);o.displayName=u+"Context";const n=s.length;s=[...s,i];const d=p=>{const{scope:f,children:x,...v}=p,M=f?.[e]?.[n]||o,j=c.useMemo(()=>v,Object.values(v));return l.jsx(M.Provider,{value:j,children:x})};d.displayName=u+"Provider";function y(p,f){const x=f?.[e]?.[n]||o,v=c.useContext(x);if(v)return v;if(i!==void 0)return i;throw new Error(`\`${p}\` must be used within \`${u}\``)}return[d,y]}const t=()=>{const u=s.map(i=>c.createContext(i));return function(o){const n=o?.[e]||u;return c.useMemo(()=>({[`__scope${e}`]:{...o,[e]:n}}),[o,n])}};return t.scopeName=e,[a,V(t,...r)]}function V(...e){const r=e[0];if(e.length===1)return r;const s=()=>{const a=e.map(t=>({useScope:t(),scopeName:t.scopeName}));return function(u){const i=a.reduce((o,{useScope:n,scopeName:d})=>{const p=n(u)[`__scope${d}`];return{...o,...p}},{});return c.useMemo(()=>({[`__scope${r.scopeName}`]:i}),[i])}};return s.scopeName=r.scopeName,s}var L=["a","button","div","form","h2","h3","img","input","label","li","nav","ol","p","select","span","svg","ul"],b=L.reduce((e,r)=>{const s=E(`Primitive.${r}`),a=c.forwardRef((t,u)=>{const{asChild:i,...o}=t,n=i?s:r;return typeof window<"u"&&(window[Symbol.for("radix-ui")]=!0),l.jsx(n,{...o,ref:u})});return a.displayName=`Primitive.${r}`,{...e,[r]:a}},{}),P="Progress",h=100,[O]=D(P),[T,G]=O(P),_=c.forwardRef((e,r)=>{const{__scopeProgress:s,value:a=null,max:t,getValueLabel:u=X,...i}=e;(t||t===0)&&!N(t)&&console.error(q(`${t}`,"Progress"));const o=N(t)?t:h;a!==null&&!$(a,o)&&console.error(z(`${a}`,"Progress"));const n=$(a,o)?a:null,d=m(n)?u(n,o):void 0;return l.jsx(T,{scope:s,value:n,max:o,children:l.jsx(b.div,{"aria-valuemax":o,"aria-valuemin":0,"aria-valuenow":m(n)?n:void 0,"aria-valuetext":d,role:"progressbar","data-state":C(n,o),"data-value":n??void 0,"data-max":o,...i,ref:r})})});_.displayName=P;var w="ProgressIndicator",S=c.forwardRef((e,r)=>{const{__scopeProgress:s,...a}=e,t=G(w,s);return l.jsx(b.div,{"data-state":C(t.value,t.max),"data-value":t.value??void 0,"data-max":t.max,...a,ref:r})});S.displayName=w;function X(e,r){return`${Math.round(e/r*100)}%`}function C(e,r){return e==null?"indeterminate":e===r?"complete":"loading"}function m(e){return typeof e=="number"}function N(e){return m(e)&&!isNaN(e)&&e>0}function $(e,r){return m(e)&&!isNaN(e)&&e<=r&&e>=0}function q(e,r){return`Invalid prop \`max\` of value \`${e}\` supplied to \`${r}\`. Only numbers greater than 0 are valid max values. Defaulting to \`${h}\`.`}function z(e,r){return`Invalid prop \`value\` of value \`${e}\` supplied to \`${r}\`. The \`value\` prop must be:
  - a positive number
  - less than the value passed to \`max\` (or ${h} if no \`max\` prop is set)
  - \`null\` or \`undefined\` if the progress is indeterminate.

Defaulting to \`null\`.`}var B=_,F=S;function K({className:e,value:r,...s}){return l.jsx(B,{"data-slot":"progress",className:I("bg-primary/20 relative h-2 w-full overflow-hidden rounded-full",e),...s,children:l.jsx(F,{"data-slot":"progress-indicator",className:"bg-primary h-full w-full flex-1 transition-all",style:{transform:`translateX(-${100-(r||0)}%)`}})})}export{U as A,Z as M,K as P,J as T};
