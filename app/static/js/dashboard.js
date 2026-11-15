import {api,session} from './api.js';
import {esc,heading,panel,empty,date,pill,toast,canWrite,icon} from './ui.js';
import {customerForm} from './customers.js';
import {activityChart,donutChart,approvalChart} from './charts.js';
import {enhanceMotion} from './motion.js';

export async function dashboard(content){
 const data=await api('/dashboard');const charts=data.charts;
 const hour=Number(new Intl.DateTimeFormat('en-GB',{timeZone:'Asia/Shanghai',hour:'numeric',hour12:false}).format(new Date()));
 const greeting=hour<12?'上午好':hour<18?'下午好':'晚上好';
 const stat=(title,value,ico,foot,color='')=>`<section class="stat" data-reveal><div class="stat-top"><span class="stat-label">${title}</span><span class="stat-icon ${color}">${icon(ico)}</span></div><div class="stat-value" data-count="${value}">${value}</div><div class="stat-foot">${foot}</div></section>`;
 const messageTotal=charts.activity.reduce((n,d)=>n+d.messages,0);const newTotal=charts.activity.reduce((n,d)=>n+d.new_customers,0);
 content.innerHTML=heading('工作台',`${greeting}，${session.user.display_name}。从这里掌握客户与团队的进展。`,`${canWrite()?'<button id="new-customer" class="primary">＋ 新建客户</button>':''}`,'WORKSPACE / 工作概览')+
 `<div class="stats">${stat('客户总数',data.total_customers,'users','当前授权范围内的有效客户')}${stat('今日新增',data.new_today,'plus','按北京时间统计','blue')}${stat('待审核画像',data.pending_requests,'check','人工确认后，更新正式画像','amber')}${stat('待跟进客户',data.followup_count,'clock','超过7天未跟进，或尚未跟进')}</div>
 <div class="analytics-grid"><section class="panel activity-panel" data-reveal><div class="panel-head"><div><h2>沟通活跃度</h2><p>把每一次沟通，串成可追溯的客户进展</p></div><span class="period-chip">近14天</span></div><div class="panel-body"><div class="chart-metrics"><div><strong>${messageTotal}</strong><span>条沟通消息</span></div><div><strong>${newTotal}</strong><span>家新增客户</span></div><a class="chart-link" href="#import">导入沟通记录 →</a></div>${activityChart(charts.activity)}</div></section>
 <section class="panel distribution-panel" data-reveal><div class="panel-head"><div><h2>客户与审核状态</h2><p>当前有效客户及关联提案</p></div></div><div class="panel-body">${donutChart(Object.entries(charts.customer_status).map(([key,value])=>({label:{potential:'潜在客户',following:'跟进中',cooperating:'合作中',closed:'已结束'}[key],value})), '有效客户')}${approvalChart(charts.approval_status)}</div></section></div>
 <div class="worklist-grid">${panel('最近客户活动',data.activities.length?`<div class="table-wrap"><table><thead><tr><th>企业客户</th><th>状态</th><th>最近更新</th><th></th></tr></thead><tbody>${data.activities.map(c=>`<tr><td class="name"><a class="company-cell" href="#customer/${c.id}"><span class="customer-mark">${esc(c.name.replace(/^【.*?】/,'')[0]||c.name[0])}</span><span>${esc(c.name)}</span></a></td><td>${pill(c.status)}</td><td>${date(c.updated_at)}</td><td><a href="#customer/${c.id}">查看 →</a></td></tr>`).join('')}</tbody></table></div>`:empty('还没有客户','新建客户后，最近更新会出现在这里。'),'<a href="#customers">查看全部 →</a>')}
 ${panel('待跟进清单',data.todos.length?data.todos.map(c=>`<a class="row-item" href="#customer/${c.id}"><span class="todo-symbol">${icon('clock')}</span><div class="grow"><p>${esc(c.name)}</p><small>${date(c.last_followup_at)} · ${esc(c.industry||'行业待补充')}</small></div><span class="row-arrow">↗</span></a>`).join(''):empty('暂无待跟进事项','沟通记录已保持更新。'),`<span class="count-badge">${data.followup_count} 项</span>`)}</div>
 <div class="workspace-footer"><span class="connection"></span>数据仅来自当前授权范围 <span>AI 负责建议，人工负责确认</span></div>`;
 const button=content.querySelector('#new-customer');if(button)button.onclick=()=>customerForm(null,()=>dashboard(content)).catch(e=>toast(e.message));
 if(content.isConnected)enhanceMotion(content);
}
