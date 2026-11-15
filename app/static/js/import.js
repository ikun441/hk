import {api,allCustomers} from './api.js';
import {esc,heading,panel,empty,field,input,textarea,select,customerOptions,formHandler,toast,modal,closeModal,canWrite,timeWithZone,localTimeInput} from './ui.js';
import {analyzeCustomer} from './profiles.js';

export async function renderImport(root){
  if(!canWrite()){root.innerHTML=heading('聊天导入','只读账号可以在客户详情中查看沟通记录。')+empty('当前账号为只读','请联系管理员分配录入权限。');return;}
  const customers=await allCustomers();
  root.innerHTML=heading('聊天导入','将沟通记录整理为独立消息，供团队查阅和画像分析。','<a href="/api/imports/template" download><button>↓ 下载 Excel 模板</button></a>','CONVERSATIONS / 沟通记录')+`<div class="notice">仅处理已取得合法依据的业务聊天。上传后先预览和校验，人工确认后入库；重复消息会自动跳过。</div><div class="tabs"><button data-mode="single" class="active">单条录入</button><button data-mode="text">多条文本粘贴</button><button data-mode="excel">Excel 批量导入</button></div><div id="import-form"></div><div id="preview"></div>`;
  const modes=root.querySelectorAll('[data-mode]');
  function switchMode(mode){
    modes.forEach(b=>b.classList.toggle('active',b.dataset.mode===mode));const formRoot=root.querySelector('#import-form');root.querySelector('#preview').innerHTML='';
    if(mode==='single'){
      formRoot.innerHTML=panel('记录一条沟通',`<form class="panel-body"><div class="form-grid">${field('企业客户',select('customer_id',customerOptions(customers),'','required'),true)}${field('说话人',select('speaker',[['customer','客户'],['employee','员工']]))}${field('消息时间（北京时间）',input('sent_at',localTimeInput(),'datetime-local','required'))}${field('消息内容',textarea('content','','required maxlength="20000" placeholder="请输入真实聊天内容"'),true)}${field('来源备注',input('source','manual','text','maxlength="200"'),true)}</div><p class="error"></p><div class="actions"><button type="submit" class="primary">保存消息</button></div></form>`);
      formHandler(formRoot.querySelector('form'),async data=>{const id=data.customer_id;delete data.customer_id;data.sent_at=timeWithZone(data.sent_at);const result=await api(`/customers/${id}/messages`,{method:'POST',body:data});toast(result.duplicate?'已存在相同消息，未重复保存':'消息已保存');formRoot.querySelector('textarea').value='';});
    }else if(mode==='text'){
      formRoot.innerHTML=panel('粘贴多条聊天',`<form class="panel-body">${textForm(customers)}<p class="error"></p><div class="actions"><button type="submit" class="primary">解析并预览</button></div></form>`);
      formHandler(formRoot.querySelector('form'),async data=>{data.customer_id=Number(data.customer_id);const batch=await api('/imports/text',{method:'POST',body:data});renderPreview(root.querySelector('#preview'),batch);});
    }else{
      formRoot.innerHTML=panel('导入 Excel 聊天记录',`<form class="panel-body"><p class="hint">使用系统模板，每行一条消息。同一文件可包含多个客户；客户同名时请填写客户 ID。最多 2000 行、5MB，不接受公式单元格。</p>${field('选择文件',input('file','','file','required accept=".xlsx"'),true)}<p class="error"></p><div class="actions"><button type="submit" class="primary">上传并预览</button></div></form>`);
      formHandler(formRoot.querySelector('form'),async()=>{const body=new FormData();body.append('file',formRoot.querySelector('[type=file]').files[0]);const batch=await api('/imports/excel',{method:'POST',body});renderPreview(root.querySelector('#preview'),batch);});
    }
  }
  modes.forEach(b=>b.onclick=()=>switchMode(b.dataset.mode));switchMode('single');
}
function textForm(customers,id){return `<div class="form-grid">${id?input('customer_id',id,'hidden'):field('选择客户',select('customer_id',customerOptions(customers),'','required'),true)}${field('聊天文本',textarea('text','','required placeholder="2026-11-15 09:30 客户: 请发一下服务费用明细\n2026-11-15 09:32 员工: 好的，我整理后发给您。"'),true,'每行格式：YYYY-MM-DD HH:MM 客户/员工: 消息。时间按北京时间解析；格式不明确的行需人工修正。')}</div>`;}
export async function openTextImport(customerId,onSaved){
  const m=modal('批量粘贴聊天记录',`<form>${textForm([],customerId)}<p class="error"></p><div class="actions"><button type="submit" class="primary">解析并预览</button></div></form><div id="paste-preview"></div>`,true);
  formHandler(m.querySelector('form'),async data=>{data.customer_id=Number(data.customer_id);const batch=await api('/imports/text',{method:'POST',body:data});renderPreview(m.querySelector('#paste-preview'),batch,onSaved);});
}
export function renderPreview(root,batch,onSaved){
  const errorCount=batch.rows.filter(r=>r.error).length;
  root.innerHTML=panel('导入预览与人工校验',`<form id="confirm-import"><div class="panel-body"><p class="hint">批次 ${esc(batch.id)} · ${batch.rows.length} 行 · ${errorCount} 行待修正。可直接编辑单元格；确认时将重新校验，符合条件的行会入库，其余行保留错误报告。</p></div><div class="table-wrap"><table class="preview-table"><thead><tr><th>原始行</th><th>客户 ID</th><th>时间</th><th>说话人</th><th>消息内容</th><th>来源</th><th>校验结果</th></tr></thead><tbody>${batch.rows.map(r=>`<tr class="${r.error?'invalid':''}" data-row="${esc(r.row)}"><td>${esc(r.row)}</td><td>${input('customer_id',r.customer_id,'number','class="customer-id" min="1"')}</td><td>${input('sent_at',r.sent_at,'text','placeholder="2026-11-15 09:30"')}</td><td>${select('speaker',[['','请选择'],['customer','客户'],['employee','员工']],r.speaker)}</td><td>${textarea('content',r.content)}</td><td>${input('source',r.source)}</td><td class="error-text">${esc(r.error||(r.duplicate?'重复消息，将跳过':'校验通过'))}</td></tr>`).join('')}</tbody></table></div><div class="panel-body"><p class="error"></p><div class="actions"><a href="/api/imports/${batch.id}/errors" download>下载错误行报告</a><button type="submit" class="primary">确认导入有效行</button></div></div></form><div id="import-result"></div>`);
  formHandler(root.querySelector('form'),async()=>{
    const rows=[...root.querySelectorAll('tbody tr')].map(tr=>{const row={row:Number(tr.dataset.row)};tr.querySelectorAll('[name]').forEach(el=>row[el.name]=el.value);return row;});
    const result=await api(`/imports/${batch.id}/confirm`,{method:'POST',body:{rows}});
    root.querySelector('form').hidden=true;
    root.querySelector('#import-result').innerHTML=`<div class="panel-body"><h3>导入已完成</h3><p class="hint">成功 ${result.inserted} 条 · 重复跳过 ${result.duplicates} 条 · 失败 ${result.failed} 条</p>${result.failed?`<a href="/api/imports/${batch.id}/errors" download>下载失败行报告</a><div class="evidence">${result.rows.filter(r=>r.error).map(r=>`第 ${esc(r.row)} 行：${esc(r.error)}`).join('<br>')}</div>`:''}<div class="toolbar">${result.customer_ids.map(id=>`<button type="button" data-analyze="${id}">分析客户 #${id}</button><a href="#customer/${id}">查看客户 #${id}</a>`).join('')}</div><p class="hint">重复提交该批次不会重复入库。失败行可修正后另建批次导入。</p></div>`;
    root.querySelectorAll('[data-analyze]').forEach(b=>b.onclick=()=>analyzeCustomer(Number(b.dataset.analyze),[],onSaved||(()=>Promise.resolve())).catch(e=>toast(e.message)));
    toast('导入处理完成');if(onSaved)await onSaved();
  });
}
