import{c as m,j as a}from"./index-BB_t3Jn4.js";import"./vendor-DGs-b1qk.js";import{h as o}from"./IASubTabBar-D46jejeL.js";import{H as h}from"./OnboardingLeer-DPIu3Z6e.js";/**
 * @license lucide-react v0.330.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const f=m("Layers",[["path",{d:"m12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83Z",key:"8b97xw"}],["path",{d:"m22 17.65-9.17 4.16a2 2 0 0 1-1.66 0L2 17.65",key:"dd6zsq"}],["path",{d:"m22 12.65-9.17 4.16a2 2 0 0 1-1.66 0L2 12.65",key:"ep9fru"}]]);/**
 * @license lucide-react v0.330.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const k=m("Power",[["path",{d:"M12 2v10",key:"mnfbl"}],["path",{d:"M18.4 6.6a9 9 0 1 1-12.77.04",key:"obofu9"}]]);function w({segmente:t,einheit:d="kWh",titel:c,herkunft:i}){const s=t.map(e=>Math.max(0,e.wert??0)),n=s.reduce((e,r)=>e+r,0);return n<=0?null:a.jsxs("div",{children:[a.jsx(h,{titel:c,herkunft:i,className:"mb-2"}),a.jsx("div",{className:"space-y-2.5",children:t.map((e,r)=>{const l=Math.round(s[r]/n*100);return a.jsxs("div",{className:"flex items-center gap-3 text-xs",children:[a.jsx("span",{className:"w-28 text-gray-600 dark:text-gray-400 shrink-0",children:e.label}),a.jsx("div",{className:"flex-1 bg-gray-200 dark:bg-gray-700 rounded-sm h-2 min-w-[2rem]",children:a.jsx("div",{className:`h-2 rounded-sm ${e.farbe}`,style:{width:`${l}%`}})}),a.jsxs("span",{className:"w-28 text-right text-gray-700 dark:text-gray-300 font-medium tabular-nums whitespace-nowrap shrink-0",children:[o(s[r],0)," ",d," · ",l," %"]})]},e.label)})})]})}export{f as L,k as P,w as V};
