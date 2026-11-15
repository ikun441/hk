import {dashboard} from './dashboard.js';
import {renderLogin} from './login.js';
import {enhanceMotion,loadingView} from './motion.js';
import {api,session} from './api.js';
import {esc,labels,icon,heading,panel,empty,date,pill,toast,formHandler,modal,closeModal,input,field,canAdmin,canWrite} from './ui.js';
import {renderCustomers,renderDetail,customerForm} from './customers.js';
import {renderImport} from './import.js';
import {renderProfiles} from './profiles.js';
import {renderApprovals} from './approvals.js';
import {renderAdmin} from './admin.js';
const routes=[['dashboard','工作台','home'],['customers','客户管理','users'],['import','聊天导入','import'],['profiles','AI画像中心','spark'],['approvals','审核中心','check'],['admin','系统管理','settings']];
let navigationId=0;
const root=document.querySelector('#root');

function loginScreen(message=''){renderLogin(root,user=>user.must_change_password?passwordScreen():shell(),message);}
function passwordScreen(){
  root.innerHTML=`<div class="login-form"><form id="password"><div class="eyebrow">ACCOUNT SECURITY</div><h2>设置新的登录密码</h2><p class="subtitle">首次登录或重置密码后，需要先修改临时密码。</p>${passwordFields()}<p class="error"></p><button type="submit" class="primary">修改密码并重新登录</button></form></div>`;
  formHandler(root.querySelector('form'),async data=>{await changePassword(data);loginScreen('密码已修改，请使用新密码登录。');});
}
function passwordFields(){return field('原密码',input('old_password','','password','required autocomplete="current-password"'))+field('新密码',input('new_password','','password','required minlength="12" maxlength="256" autocomplete="new-password"'))+field('确认新密码',input('confirm_password','','password','required minlength="12" autocomplete="new-password"'));}
async function changePassword(data){if(data.new_password!==data.confirm_password)throw new Error('两次新密码不一致');delete data.confirm_password;await api('/auth/password',{method:'POST',body:data});session.user=null;session.csrf='';}
function shell(){
  root.innerHTML=`<div class="shell"><aside class="sidebar"><div class="brand"><span class="brand-icon">企</span><div><strong>企客</strong><small>CUSTOMER WORKSPACE</small></div></div><div class="nav-label">工作空间</div><nav class="nav" aria-label="主导航">${routes.filter(r=>r[0]!=='admin'||canAdmin()).map(([key,label,ico])=>`<button data-route="${key}">${icon(ico)}${label}</button>`).join('')}</nav><div class="sidebar-foot"><span class="connection"></span><span id="workspace-name">企业内部工作空间</span><br>企客 CRM · MVP 0.1</div></aside><div class="main"><header class="topbar"><button class="mobile-menu" aria-label="展开导航" aria-expanded="false">☰</button><span class="breadcrumb">工作空间 &nbsp; / &nbsp; <span id="breadcrumb">工作台</span></span><div class="account"><span class="avatar">${esc(session.user.display_name.slice(0,1))}</span><div>${esc(session.user.display_name)}<small>${esc(labels[session.user.role])}</small></div><button class="text password-button" id="change-password">修改密码</button><button class="text" id="logout">退出</button></div></header><main id="content" class="content"></main></div></div>`;
  root.querySelectorAll('[data-route]').forEach(b=>b.onclick=()=>{location.hash=b.dataset.route;root.querySelector('.sidebar').classList.remove('open');root.querySelector('.mobile-menu').setAttribute('aria-expanded','false');});
  root.querySelector('.mobile-menu').onclick=()=>{const open=root.querySelector('.sidebar').classList.toggle('open');root.querySelector('.mobile-menu').setAttribute('aria-expanded',String(open));};
  root.querySelector('#logout').onclick=async()=>{try{await api('/auth/logout',{method:'POST'});}catch(e){toast(e.message);}session.user=null;session.csrf='';loginScreen();};
  root.querySelector('#change-password').onclick=()=>{const m=modal('修改登录密码',`<form>${passwordFields()}<p class="error"></p><div class="actions"><button class="primary" type="submit">保存并重新登录</button></div></form>`);formHandler(m.querySelector('form'),async data=>{await changePassword(data);closeModal();loginScreen('密码已修改，请重新登录。');});};
  api('/workspace').then(data=>{const el=document.querySelector('#workspace-name');if(el)el.textContent=data.company_name;}).catch(()=>{});
  navigate();
}
async function navigate(){
  if(!session.user||session.user.must_change_password)return;
  const id=++navigationId;const route=(location.hash.slice(1)||'dashboard');const key=route.startsWith('customer/')?'customers':route;
  const content=document.querySelector('#content');if(!content)return;
  document.querySelectorAll('[data-route]').forEach(b=>b.classList.toggle('active',b.dataset.route===key));
  document.querySelector('#breadcrumb').textContent=routes.find(r=>r[0]===key)?.[1]||'工作台';
  content.firstElementChild?._dispose?.();
  content.setAttribute('aria-busy','true');
  content.innerHTML=loadingView();
  // Detached render target prevents a slow previous request from replacing a newer page.
  const target=document.createElement('div');target.className='page-stage';
  try{
    if(route.startsWith('customer/'))await renderDetail(target,Number(route.split('/')[1]));
    else await ({dashboard,customers:renderCustomers,import:renderImport,profiles:renderProfiles,approvals:renderApprovals,admin:renderAdmin}[route]||dashboard)(target);
    if(id===navigationId){content.replaceChildren(target);content.setAttribute('aria-busy','false');enhanceMotion(target);document.title=`${document.querySelector('#breadcrumb').textContent} · 企客 CRM`;}
  }catch(error){if(id===navigationId){content.setAttribute('aria-busy','false');content.innerHTML=`<div class="error">${esc(error.message)}</div>`;}}
}
window.addEventListener('hashchange',navigate);
window.addEventListener('session-expired',()=>{++navigationId;closeModal();loginScreen('会话已过期，请重新登录。');});
try{const result=await api('/auth/me');session.user=result.user;session.csrf=result.csrf_token;if(session.user.must_change_password)passwordScreen();else shell();}catch{loginScreen();}
