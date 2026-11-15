import {session} from './api.js';
export const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export const date=v=>v?new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(v)):'尚未跟进';
export const fullDate=v=>v?new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(v)):'—';
export const labels={potential:'潜在客户',following:'跟进中',cooperating:'合作中',closed:'已结束',pending:'待审核',approved:'已批准',rejected:'已驳回',superadmin:'超级管理员',admin:'管理员',employee:'普通员工',readonly:'只读用户',all:'全部客户',department:'本部门客户',own:'本人负责',assigned:'特定授权',mock:'Mock 演示',manual:'人工提案',ai:'AI 分析'};
export const businessLabels={needs:'业务需求',purchase_stage:'购买阶段',concerns:'关注因素',communication_preferences:'沟通偏好',objections:'客户异议'};
export const dims=['Ne','Ni','Se','Si','Te','Ti','Fe','Fi'];
export const canWrite=()=>session.user?.role!=='readonly';
export const canAdmin=()=>['superadmin','admin'].includes(session.user?.role);
export const isSuper=()=>session.user?.role==='superadmin';
export const pill=v=>`<span class="pill ${esc(v)}">${esc(labels[v]||v)}</span>`;
export const empty=(title='暂无记录',hint='新增客户或导入聊天后，相关内容会出现在这里。')=>`<div class="empty"><strong>${esc(title)}</strong>${esc(hint)}</div>`;
let fieldId=0;
export function field(label,control,wide=false,hint=''){
 let id='';const first=control.match(/<(input|select|textarea)\b[^>]*>/i);
 if(label&&first&&!/type="(?:checkbox|hidden|radio)"/.test(first[0])){
  id=first[0].match(/\bid="([^"]+)"/)?.[1]||'field-'+ ++fieldId;
  let tag=first[0].replace(/\saria-label="[^"]*"/g,'');
  if(!/\bid=/.test(tag))tag=tag.replace(/>$/,` id="${id}">`);
  if(hint)tag=tag.replace(/>$/,` aria-describedby="${id}-hint">`);
  control=control.replace(first[0],tag);
 }
 return `<div class="field ${wide?'wide':''}">${label?`<label ${id?`for="${id}"`:''}>${esc(label)}</label>`:''}${control}${hint?`<small ${id?`id="${id}-hint"`:''}>${esc(hint)}</small>`:''}</div>`;
}
export const input=(name,value='',type='text',extra='')=>`<input ${/aria-label=/.test(extra)?'':`aria-label="${esc(name)}"`} name="${esc(name)}" type="${type}" value="${esc(value)}" ${extra}>`;
export const textarea=(name,value='',extra='')=>`<textarea ${/aria-label=/.test(extra)?'':`aria-label="${esc(name)}"`} name="${esc(name)}" ${extra}>${esc(value)}</textarea>`;
export const select=(name,options,value='',extra='')=>`<select ${/aria-label=/.test(extra)?'':`aria-label="${esc(name)}"`} name="${esc(name)}" ${extra}>${options.map(([v,l])=>`<option value="${esc(v)}" ${String(v)===String(value)?'selected':''}>${esc(l)}</option>`).join('')}</select>`;
export const customerOptions=items=>[['','请选择客户'],...items.map(c=>[c.id,`${c.name} · #${c.id}`])];
export function heading(title,subtitle,actions='',eyebrow='WORKSPACE'){
  return `<div class="page-heading"><div><div class="eyebrow">${esc(eyebrow)}</div><h1>${esc(title)}</h1><p class="subtitle">${esc(subtitle)}</p></div><div class="toolbar">${actions}</div></div>`;
}
export const panel=(title,body,extra='')=>`<section class="panel"><div class="panel-head"><h2>${esc(title)}</h2>${extra}</div>${body}</section>`;
export function toast(text){const el=document.querySelector('#toast');el.textContent=text;el.classList.add('show');clearTimeout(window.toastTimer);window.toastTimer=setTimeout(()=>el.classList.remove('show'),3500);}
export function modal(title,body,large=false){const el=document.querySelector('#modal');if(el.open)el.close();el.className=large?'large':'';el.innerHTML=`<div class="modal-head"><h2 id="modal-title">${esc(title)}</h2><button class="close" aria-label="关闭">×</button></div><div class="modal-body">${body}</div>`;el.querySelector('.close').onclick=()=>el.close();el.showModal();return el;}
export function closeModal(){document.querySelector('#modal').close();}
export function formHandler(form,handler){form.addEventListener('submit',async event=>{event.preventDefault();if(form.dataset.submitting)return;form.dataset.submitting='true';form.setAttribute('aria-busy','true');event.submitter?.classList.add('is-loading');const buttons=[...form.querySelectorAll('button[type=submit],button:not([type])')];const disabled=buttons.map(b=>b.disabled);buttons.forEach(b=>b.disabled=true);const err=form.querySelector('.error');if(err)err.textContent='';try{await handler(Object.fromEntries(new FormData(form)),event.submitter);}catch(error){if(err)err.textContent=error.message;else toast(error.message);}finally{delete form.dataset.submitting;form.setAttribute('aria-busy','false');event.submitter?.classList.remove('is-loading');buttons.forEach((b,i)=>b.disabled=disabled[i]);}});}
export function bindActions(root,handlers){root.addEventListener('click',async e=>{const button=e.target.closest('[data-action]');if(!button||!root.contains(button))return;const handler=handlers[button.dataset.action];if(!handler)return;button.disabled=true;try{await handler(button);}catch(error){toast(error.message);}finally{button.disabled=false;}});}
export function pager(data){return `<div class="pager"><span>共 ${data.total} 条 · 第 ${data.page} / ${Math.max(1,Math.ceil(data.total/data.page_size))} 页</span><div class="toolbar"><button data-page="${data.page-1}" ${data.page<=1?'disabled':''}>上一页</button><button data-page="${data.page+1}" ${data.page*data.page_size>=data.total?'disabled':''}>下一页</button></div></div>`;}
export function bindPager(root,handler){root.querySelectorAll('[data-page]').forEach(b=>b.onclick=()=>handler(Number(b.dataset.page)).catch(e=>toast(e.message)));}
export function localTimeInput(){const t=new Date(Date.now()+8*3600000);return t.toISOString().slice(0,16);}
export function timeWithZone(value){return value?value+':00+08:00':null;}
export const icon=name=>{const paths={search:'m21 21-5-5M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0',refresh:'M20 7v5h-5M4 17v-5h5M6 6a8 8 0 0 1 13 3M18 18a8 8 0 0 1-13-3',home:'M3 10 12 3l9 7v11H3ZM9 21v-8h6v8',users:'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M15 3a4 4 0 0 1 0 8M22 21v-2a4 4 0 0 0-3-3.87M13 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0',import:'M12 3v12m-4-4 4 4 4-4M4 16v5h16v-5',spark:'m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5Z',check:'M8 3h8v4H8ZM6 5H4v16h16V5h-2M8 13l3 3 5-6',settings:'M12 8a4 4 0 1 1 0 8 4 4 0 0 1 0-8M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M5 19l2-2M17 7l2-2',clock:'M12 8v5l3 2M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0',plus:'M12 5v14M5 12h14'};return `<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="${paths[name]||paths.users}"></path></svg>`;};
