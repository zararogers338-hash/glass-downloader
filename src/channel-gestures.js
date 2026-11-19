// Native touch scrolling for the strip, plus desktop wheel and mouse dragging.
export function stripScroll(node){
 let start=null,drag=false,blockClick=false;
 const wheel=e=>{
   if(e.ctrlKey||Math.abs(e.deltaX)>Math.abs(e.deltaY)||!e.deltaY)return;
   node.scrollLeft+=e.deltaY*(e.deltaMode===1?18:e.deltaMode===2?node.clientWidth:1);e.preventDefault();
 };
 const down=e=>{if(e.pointerType==='mouse'&&e.button===0){start=[e.clientX,node.scrollLeft];drag=false;blockClick=false}};
 const move=e=>{
   if(!start)return;const dx=e.clientX-start[0];
   if(!drag&&Math.abs(dx)<6)return;
   drag=true;node.scrollLeft=start[1]-dx;e.preventDefault();
 };
 const up=()=>{if(start)blockClick=drag;start=null;drag=false};
 const click=e=>{if(blockClick){e.preventDefault();e.stopImmediatePropagation();blockClick=false}};
 node.addEventListener('wheel',wheel,{passive:false});node.addEventListener('pointerdown',down);
 window.addEventListener('pointermove',move);window.addEventListener('pointerup',up);window.addEventListener('pointercancel',up);
 node.addEventListener('click',click,true);
 node.querySelector('[aria-pressed=true]')?.scrollIntoView({block:'nearest',inline:'nearest'});
 return {destroy(){node.removeEventListener('wheel',wheel);node.removeEventListener('pointerdown',down);
 window.removeEventListener('pointermove',move);window.removeEventListener('pointerup',up);window.removeEventListener('pointercancel',up);node.removeEventListener('click',click,true)}};
}

export function swipeScene(node,step){
 const excluded='button,input,select,label,dialog,textarea,.selector-panel,.monitor,.dispatch,.bili-options';
 let start,delta=0,last=0,switched=false;
 const down=e=>{start=e.button===0&&!e.target.closest(excluded)?[e.clientX,e.clientY,e.pointerId]:null};
 const cancel=()=>{start=null};
 const up=e=>{if(!start||e.pointerId!==start[2])return;const dx=e.clientX-start[0],dy=e.clientY-start[1];start=null;
   if(Math.abs(dx)>55 && Math.abs(dx)>1.5*Math.abs(dy))step(dx<0?1:-1)};
 const wheel=e=>{if(e.ctrlKey||e.target.closest(excluded))return;
   const x=e.shiftKey?e.deltaY:e.deltaX;
   if(!x||(!e.shiftKey&&Math.abs(x)<Math.abs(e.deltaY)*1.35))return;
   e.preventDefault();const now=performance.now();if(now-last>160){delta=0;switched=false}last=now;
   if(!switched){delta+=x;if(Math.abs(delta)>42){step(Math.sign(delta));switched=true}}
 };
 node.addEventListener('pointerdown',down);window.addEventListener('pointerup',up);window.addEventListener('pointercancel',cancel);node.addEventListener('wheel',wheel,{passive:false});
 return {destroy(){node.removeEventListener('pointerdown',down);window.removeEventListener('pointerup',up);window.removeEventListener('pointercancel',cancel);node.removeEventListener('wheel',wheel)}};
}
