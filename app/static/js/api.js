export const session={user:null,csrf:''};
export async function api(path,options={}){
  const headers={'X-CRM-Request':'1',...(session.csrf?{'X-CSRF-Token':session.csrf}:{}),...options.headers};
  if(options.body && !(options.body instanceof FormData)){headers['Content-Type']='application/json';options.body=JSON.stringify(options.body);}
  const response=await fetch('/api'+path,{credentials:'same-origin',...options,headers});
  const payload=await response.json().catch(error=>{if(error.name==='AbortError')throw error;return {detail:'服务返回了无效响应'};});
  if(!response.ok){
    if(response.status===401 && session.user){session.user=null;window.dispatchEvent(new Event('session-expired'));}
    const detail=Array.isArray(payload.detail)?payload.detail.map(x=>`${x.loc.join('.')}: ${x.msg}`).join('；'):payload.detail;
    throw new Error(detail||'请求失败');
  }
  return payload;
}
export async function allCustomers(){
  const items=[];let page=1;
  while(true){const data=await api(`/customers?page=${page++}&page_size=100`);items.push(...data.items);if(items.length>=data.total)break;}
  return items;
}
