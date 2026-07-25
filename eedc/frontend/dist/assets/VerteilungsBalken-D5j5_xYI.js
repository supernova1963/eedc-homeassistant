import{c as l,j as a}from"./index-DHYWzBU6.js";import"./vendor-DGs-b1qk.js";import{h as i}from"./IASubTabBar-B8kjUFR1.js";/**
 * @license lucide-react v0.330.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const p=l("Layers",[["path",{d:"m12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83Z",key:"8b97xw"}],["path",{d:"m22 17.65-9.17 4.16a2 2 0 0 1-1.66 0L2 17.65",key:"dd6zsq"}],["path",{d:"m22 12.65-9.17 4.16a2 2 0 0 1-1.66 0L2 12.65",key:"ep9fru"}]]);/**
 * @license lucide-react v0.330.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const u=l("Power",[["path",{d:"M12 2v10",key:"mnfbl"}],["path",{d:"M18.4 6.6a9 9 0 1 1-12.77.04",key:"obofu9"}]]);function y({segmente:s,einheit:m="kWh",titel:n}){const t=s.map(e=>Math.max(0,e.wert??0)),d=t.reduce((e,r)=>e+r,0);return d<=0?null:a.jsxs("div",{children:[n&&a.jsx("p",{className:"text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wider mb-2",children:n}),a.jsx("div",{className:"space-y-2.5",children:s.map((e,r)=>{const c=Math.round(t[r]/d*100);return a.jsxs("div",{className:"flex items-center gap-3 text-xs",children:[a.jsx("span",{className:"w-28 text-gray-600 dark:text-gray-400 shrink-0",children:e.label}),a.jsx("div",{className:"flex-1 bg-gray-200 dark:bg-gray-700 rounded-sm h-2 min-w-[2rem]",children:a.jsx("div",{className:`h-2 rounded-sm ${e.farbe}`,style:{width:`${c}%`}})}),a.jsxs("span",{className:"w-28 text-right text-gray-700 dark:text-gray-300 font-medium tabular-nums whitespace-nowrap shrink-0",children:[i(t[r],0)," ",m," · ",c," %"]})]},e.label)})})]})}export{p as L,u as P,y as V};
