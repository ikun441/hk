export const reducedMotion=()=>window.matchMedia('(prefers-reduced-motion: reduce)').matches;
export function enhanceMotion(root){
 if(reducedMotion())return;
 root.querySelectorAll('.stat-value[data-count]').forEach(el=>{
  if(el.dataset.animated)return;el.dataset.animated='true';const value=Number(el.dataset.count);const start=performance.now();
  function step(now){if(!el.isConnected)return;const t=Math.min(1,(now-start)/600);el.textContent=String(Math.round(value*(1-Math.pow(1-t,3))));if(t<1)requestAnimationFrame(step);}
  requestAnimationFrame(step);
 });
 root.querySelectorAll('[data-reveal]').forEach((el,i)=>{if(el.dataset.revealed)return;el.dataset.revealed='true';el.animate([{opacity:0,transform:'translateY(14px)'},{opacity:1,transform:'translateY(0)'}],{duration:420,delay:Math.min(i*45,180),easing:'cubic-bezier(.16,1,.3,1)',fill:'backwards'});});
}
export function loadingView(label='正在加载工作空间'){
 return `<div class="loading-shell" role="status" aria-label="${label}"><span class="sr-only">${label}</span><div class="skeleton skeleton-title"></div><div class="skeleton-stats">${Array.from({length:4},()=>'<div class="skeleton skeleton-card"></div>').join('')}</div><div class="skeleton-charts"><div class="skeleton skeleton-plot"></div><div class="skeleton skeleton-plot"></div></div></div>`;
}
export function bindLoginMotion(container){
 const stage=container.querySelector('.login-scene');const toggle=container.querySelector('#toggle-motion');let paused=false;
 if(toggle)toggle.onclick=()=>{paused=!paused;container.classList.toggle('motion-paused',paused);toggle.setAttribute('aria-pressed',String(paused));toggle.textContent=paused?'继续动画':'暂停动画';};
 if(!stage)return;
 stage.addEventListener('pointermove',e=>{if(reducedMotion()||paused)return;const rect=stage.getBoundingClientRect();stage.style.setProperty('--scene-x',`${(e.clientX-rect.left-rect.width/2)*.018}px`);stage.style.setProperty('--scene-y',`${(e.clientY-rect.top-rect.height/2)*.018}px`);});
 stage.addEventListener('pointerleave',()=>{stage.style.setProperty('--scene-x','0px');stage.style.setProperty('--scene-y','0px');});
}
