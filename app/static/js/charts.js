import {esc,labels,dims} from './ui.js';
export const palette=['#278b75','#688fc1','#dfa86b','#a88cbc','#49a9ac','#d08087','#85a867','#bca45b'];
export const dimensionNames={Ne:'备选方向',Ni:'整体脉络',Se:'具体实例',Si:'经验与流程',Te:'结构与执行',Ti:'依据与逻辑',Fe:'协作确认',Fi:'自主取舍'};
const number=x=>Number.isFinite(Number(x))?Number(x):0;
const colorClass=i=>'chart-color-'+i;
let chartId=0;
const point=(x,y)=>`${x.toFixed(2)},${y.toFixed(2)}`;

export function activityChart(rows=[]){
 const w=560,h=210,left=38,right=w-16,top=18,bottom=h-30;
 const max=Math.max(4,Math.ceil(Math.max(0,...rows.map(r=>number(r.messages)))/4)*4);
 const coords=rows.map((r,i)=>[left+(right-left)*i/Math.max(rows.length-1,1),bottom-number(r.messages)/max*(bottom-top)]);
 const line=coords.map((p,i)=>(i?'L':'M')+point(...p)).join(' ');
 const area=coords.length?line+` L${right},${bottom} L${left},${bottom} Z`:'';
 const id='activity-fill-'+ ++chartId;
 const grid=[0,1,2,3,4].map(i=>{const y=bottom-(bottom-top)*i/4;return `<line x1="${left}" y1="${y}" x2="${right}" y2="${y}" class="chart-gridline"/><text x="${left-10}" y="${y+4}" text-anchor="end">${max*i/4}</text>`;}).join('');
 const ticks=rows.map((r,i)=>i%3===0||i===rows.length-1?`<text x="${coords[i][0]}" y="${h-6}" text-anchor="middle">${esc(r.date.slice(5).replace('-','/'))}</text>`:'').join('');
 return `<figure class="data-chart activity-chart"><svg viewBox="0 0 ${w} ${h}" role="img" aria-label="最近14天沟通活跃度，按消息时间统计"><desc>${esc(rows.map(r=>`${r.date}：${r.messages}条消息`).join('；'))}</desc><defs><linearGradient id="${id}" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#43a28c" stop-opacity=".22"/><stop offset="100%" stop-color="#43a28c" stop-opacity=".01"/></linearGradient></defs>${grid}<path d="${area}" fill="url(#${id})" class="chart-area"/><path d="${line}" fill="none" stroke="#278b75" stroke-width="2.7" stroke-linejoin="round" pathLength="1" class="chart-line-draw"/>${coords.map(([x,y],i)=>`<circle cx="${x}" cy="${y}" r="3.4" fill="#278b75" stroke="white" stroke-width="2" class="chart-point"><title>${esc(rows[i].date)} · ${rows[i].messages}条消息 · ${rows[i].new_customers}家新增客户</title></circle>`).join('')}${ticks}</svg><figcaption>按聊天消息时间统计 · 近14天</figcaption></figure>`;
}

export function donutChart(entries,centerLabel='客户总数'){
 const total=entries.reduce((n,e)=>n+number(e.value),0),circ=2*Math.PI*58;let offset=0;
 const arcs=entries.map((entry,i)=>{const len=total?number(entry.value)/total*circ:0;const el=`<circle cx="82" cy="82" r="58" fill="none" stroke="${palette[i%palette.length]}" stroke-width="17" stroke-dasharray="${len} ${circ-len}" stroke-dashoffset="${-offset}" transform="rotate(-90 82 82)"><title>${esc(entry.label)}：${number(entry.value)}</title></circle>`;offset+=len;return el;}).join('');
 return `<div class="donut-layout"><svg class="donut-chart" viewBox="0 0 164 164" role="img" aria-label="${esc(centerLabel)}：${total}；${esc(entries.map(e=>e.label+e.value).join('、'))}"><circle cx="82" cy="82" r="58" fill="none" stroke="#edf1ee" stroke-width="17"/>${arcs}<text class="donut-total" x="82" y="80" text-anchor="middle">${total}</text><text class="donut-caption" x="82" y="100" text-anchor="middle">${esc(centerLabel)}</text></svg><ul class="chart-legend">${entries.map((e,i)=>`<li><span class="legend-dot ${colorClass(i)}"></span><span>${esc(e.label)}</span><strong>${number(e.value)}</strong></li>`).join('')}</ul></div>`;
}

export function approvalChart(counts){
 const entries=['pending','approved','rejected'].map((key,i)=>({label:labels[key],value:number(counts?.[key]),color:['#d8ab62','#3c9a80','#b9c1bc'][i]}));const total=entries.reduce((n,e)=>n+e.value,0);let x=0;
 return `<div class="approval-mini"><div class="chart-subhead"><span>画像审核</span><strong>${total} 条提案</strong></div><svg viewBox="0 0 320 12" preserveAspectRatio="none" role="img" aria-label="${esc(entries.map(e=>e.label+e.value).join('，'))}"><rect width="320" height="12" rx="6" fill="#edf1ee"/>${entries.map(e=>{const width=total?e.value/total*320:0;const rect=`<rect x="${x}" width="${width}" height="12" fill="${e.color}"><title>${esc(e.label)} ${e.value}</title></rect>`;x+=width;return rect;}).join('')}</svg><div class="approval-counts">${entries.map(e=>`<span>${esc(e.label)} <b>${e.value}</b></span>`).join('')}</div></div>`;
}

export function radarChart(scores){
 const cx=170,cy=138,r=92;
 const pos=(i,value)=>{const a=i*Math.PI/4-Math.PI/2;return [cx+Math.cos(a)*r*value/100,cy+Math.sin(a)*r*value/100];};
 const polygon=value=>dims.map((d,i)=>point(...pos(i,typeof value==='number'?value:number(value[d])))).join(' ');
 return `<figure class="data-chart radar-chart"><svg viewBox="0 0 340 282" role="img" aria-label="八维参考雷达图，虚线为中性值50"><desc>${esc(dims.map(d=>d+' '+number(scores[d])).join('，'))}。探索性参考，非人格诊断。</desc>${[25,50,75,100].map(v=>`<polygon points="${polygon(v)}" fill="${v===100?'#f8faf8':'none'}" stroke="${v===50?'#b5c6bb':'#e4ece6'}" stroke-dasharray="${v===50?'4 4':'none'}"/>`).reverse().join('')}${dims.map((d,i)=>{const [x,y]=pos(i,100);return `<line x1="${cx}" y1="${cy}" x2="${x}" y2="${y}" stroke="#e4ece6"/>`;}).join('')}<polygon points="${polygon(scores)}" fill="#2f967a" fill-opacity=".16" stroke="#278b75" stroke-width="2.2" class="radar-shape"/>${dims.map((d,i)=>{const [x,y]=pos(i,number(scores[d]));const [lx,ly]=pos(i,128);return `<circle cx="${x}" cy="${y}" r="3.4" fill="#278b75"><title>${d} ${number(scores[d])} · ${esc(dimensionNames[d])}</title></circle><text x="${lx}" y="${ly-3}" text-anchor="middle" class="radar-label">${d}<tspan x="${lx}" dy="15" class="radar-score">${number(scores[d])}</tspan></text>`;}).join('')}</svg><figcaption><span class="line-key"></span>正式画像 <span class="line-key dashed"></span>中性基线 50</figcaption></figure>`;
}

export function versionChart(versions,active=['Te'],zoom=true){
 const series=active.filter(d=>dims.includes(d));const values=versions.flatMap(v=>series.map(d=>number(v.scores[d])));
 const rawMin=Math.max(0,Math.floor(Math.min(50,...values)-2)),rawMax=Math.min(100,Math.ceil(Math.max(50,...values)+2));
 const span=Math.min(100,Math.max(4,Math.ceil((rawMax-rawMin)/4)*4));
 const min=zoom?Math.max(0,Math.min(rawMin,100-span)):0,max=zoom?min+span:100;
 const w=560,h=210,left=34,right=w-20,top=15,bottom=h-31;
 const pos=(v,i,d)=>[versions.length===1?(left+right)/2:left+(right-left)*i/Math.max(versions.length-1,1),bottom-(number(v.scores[d])-min)/Math.max(max-min,1)*(bottom-top)];
 const grid=[0,1,2,3,4].map(i=>{const y=bottom-(bottom-top)*i/4;return `<line x1="${left}" y1="${y}" x2="${right}" y2="${y}" class="chart-gridline"/><text x="${left-9}" y="${y+4}" text-anchor="end">${(min+(max-min)*i/4).toFixed(1).replace('.0','')}</text>`;}).join('');
 return `<figure class="data-chart version-chart"><svg viewBox="0 0 ${w} ${h}" role="img" aria-label="正式画像版本变化，${esc(series.join('、'))}，纵轴${min}至${max}">${grid}${series.map(d=>{const points=versions.map((v,i)=>pos(v,i,d));const color=palette[dims.indexOf(d)];return `<path d="${points.map((p,i)=>(i?'L':'M')+point(...p)).join(' ')}" fill="none" stroke="${color}" stroke-width="2.4" stroke-linejoin="round" class="chart-line-draw" pathLength="1"/>${points.map(([x,y],i)=>`<circle cx="${x}" cy="${y}" r="4" fill="${color}" stroke="white" stroke-width="1.5" class="chart-point"><title>v${versions[i].version} · ${d} ${number(versions[i].scores[d])}</title></circle>`).join('')}`;}).join('')}${versions.map((v,i)=>i%Math.max(1,Math.ceil(versions.length/7))===0||i===versions.length-1?`<text x="${pos(v,i,series[0]||'Te')[0]}" y="${h-7}" text-anchor="middle">v${v.version}</text>`:'').join('')}</svg><figcaption>${zoom?`局部刻度 ${min}–${max}，用于查看小幅变化`:'完整刻度 0–100'} · 仅含已生效版本${versions.length===1?' · 目前仅有初始版本':''}</figcaption></figure>`;
}

export function scoreComparison(scores,deltas={}){
 return `<div class="score-comparison">${dims.map((d,i)=>`<div class="compare-row"><span class="dimension-code">${d}</span><span class="dimension-name">${dimensionNames[d]}</span><div class="compare-meter"><meter class="${colorClass(i)}" min="0" max="100" value="${number(scores[d])}" aria-label="${d}正式参考分数">${number(scores[d])}</meter><span class="neutral-marker" aria-hidden="true"></span></div><strong>${number(scores[d])}</strong><span class="delta-chip ${number(deltas[d])?'changed':''}">${number(deltas[d])>0?'+':''}${number(deltas[d])}</span></div>`).join('')}<div class="chart-caption">分数范围 0–100 · 标线为中性值50 · 右侧为最近审批的实际变化</div></div>`;
}
