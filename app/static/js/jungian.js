import {esc,dims} from './ui.js';
const names={Ne:'备选方向',Ni:'整体脉络',Se:'具体实例',Si:'经验与流程',Te:'结构与执行',Ti:'依据与逻辑',Fe:'协作确认',Fi:'自主取舍'};
const confidence={insufficient:'证据不足',low:'低置信度线索',medium:'中等置信度线索'};
const basis={proposal_preview:'含待审批增量的表达参考',approved_profile:'基于已审批画像的表达参考',evidence_only:'原文线索参考，本次不重复计分',insufficient:'暂无足够八维线索'};
export function guidanceView(guide,title='八维如何参与本次建议',status=null){
 if(!guide)return `<div class="jungian-guidance"><h3 class="small-heading">${esc(title)}</h3><p class="hint">此历史分析未包含八维话术说明，重新分析可生成逐维证据和参与说明。</p></div>`;
 return `<section class="jungian-guidance"><h3 class="small-heading">${esc(title)}</h3><small class="hint">${esc(status==='approved'?'已审核建议 · 八维计分结果见正式画像':status==='rejected'?'已驳回，仅保留历史分析':basis[guide.basis]||guide.basis)}</small><p class="proposal-text">${esc(guide.summary)}</p><div class="toolbar">${(guide.dimensions||[]).map(d=>`<span class="pill">${esc(d)} · ${esc(names[d]||'')}</span>`).join('')}</div>${guide.wording_tips?.length?`<ul class="style-tips">${guide.wording_tips.map(t=>`<li>${esc(t)}</li>`).join('')}</ul>`:''}</section>`;
}
export function assessmentView(analysis,context=null){
 if(!analysis||!Object.keys(analysis).length)return '<p class="hint">旧提案仅保存汇总delta；重新分析后可查看每个维度的原文、理由和表达建议。</p>';
 return `<div class="dimension-list">${dims.map(d=>{const a=analysis[d];const before=context?.current_scores?.[d];const delta=context?.effective_deltas?.[d]||0;const after=context?.projected_scores?.[d];return `<details class="dimension"><summary><strong>${d} · ${esc(names[d])}</strong><span>${before===undefined?'':`${before} ${delta>=0?'+':''}${delta} → ${after}`} · ${esc(confidence[a?.confidence]||'证据不足')}</span></summary><p class="proposal-text">${esc(a?.reasoning||'暂无足够原文线索，不调整分数。')}</p>${(a?.evidence||[]).map(e=>`<div class="evidence"><small>客户消息 #${e.message_id}</small>“${esc(e.quote)}”</div>`).join('')}${a?.expression_tip?`<p class="hint">表达建议：${esc(a.expression_tip)}</p>`:''}</details>`;}).join('')}</div>${context?.excluded_evidence_message_ids?.length?`<p class="hint">已计分证据 #${context.excluded_evidence_message_ids.join(', #')} 已排除；其余新增证据仍可计分。</p>`:''}`;
}
export function approvedReference(meta){
 if(!meta)return '<p class="hint">尚无已审核的逐维说明。生成分析后，可先预览八维增量，审批后更新正式分数。</p>';
 return `<p class="hint">最近实际变化：${dims.map(d=>d+' '+((meta.last_delta?.[d]||0)>=0?'+':'')+(meta.last_delta?.[d]||0)).join(' · ')}</p><details class="approved-reference"><summary>查看已审核八维证据与表达参考</summary>${guidanceView(meta.guidance,'八维表达参考（已审核）')}${assessmentView(meta.analysis)}</details>`;
}
