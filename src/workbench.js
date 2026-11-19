import channels from '../channels.json';
import kernelList from '../engines.json';
export const kernels=Object.fromEntries(kernelList.map(k=>[k.id,k]));
export { channels };
export const byId = Object.fromEntries(channels.map(c=>[c.id,c]));
export const engName = Object.fromEntries(kernelList.map(k=>[k.id,k.name]));
export const routeName = {direct:'直连',mihomo:'Mihomo',tor:'Tor'};
export const states = {running:'下载中',verifying:'校验中',completed:'已完成',paused:'已暂停',queued:'等待中',failed:'失败',cancelled:'已取消',pausing:'暂停中',cancelling:'取消中'};
export const isActive = j=>['running','queued','verifying'].includes(j.state);
export function size(n) {
  if(n==null) return '—';
  const units=['B','KiB','MiB','GiB','TiB'];
  let i=0; while(n>=1024 && i<4){n/=1024;i++}
  return Number(n.toFixed(i===0?0:2)).toString()+' '+units[i];
}
export const rate=n=>n==null?'—':size(n)+'/s';
export const percent=j=>j.state==='completed'?100:j.total?Math.min(99,Math.round(100*j.done/j.total)):0;
export function eta(j) {
  if(!j.total || !j.speed || j.state!=='running') return '—';
  const s=Math.ceil((j.total-j.done)/j.speed);return s>=60?Math.floor(s/60)+' 分 '+s%60+' 秒':s+' 秒';
}
export function engines(id){
  const kind=['magnet','video','bilibili','tor'].includes(id)?id:'files';
  return kernelList.filter(k=>k.kinds.includes(kind)).map(k=>k.id);
}
export function defaults(c,conf){
  const p=conf.profiles[c.id]||{};
  return {route:p.route||(c.id==='tor'?'tor':c.id==='magnet'?'direct':conf.default_route),engine:p.engine||c.engine,source:p.source||'original'};
}
const MiB=1048576;
export const defaultSettings={speed_profile:"high",profiles:{},resume_on_start:false,connections:4,parallel_tasks:3,retries:2,download_dir:'~/Downloads/GlassDownloader',default_route:'direct',upload_kib:128,download_kib:0,mihomo_port:7890,tor_port:9050};
function makeSample(){
  const now=Date.now()/1000;
  const rows=[
    ['model-00001-of-00004.safetensors','huggingface','running',5120],
    ['ubuntu-desktop-amd64.iso','magnet','running',6410],
    ['Qwen3-8B-Q4_K_M.gguf','modelscope','paused',4900],
    ['rustdesk-x86_64.exe','github','completed',24.5],
    ['attention-is-all-you-need.pdf','arxiv','completed',3.15],
    ['python-amd64.exe','python','completed',29.2]
  ];
  return rows.map(([name,channel,state,mb],i)=>{
    const total=Math.round(mb*MiB),done=Math.round(total*(state==='completed'?1:[.62,.24,.38][i])),count=i===0?8:1;
    const segments=[];let remainder=done;
    for(let n=0;n<count;n++){
      const start=Math.floor(n*total/count),end=Math.floor((n+1)*total/count)-1;
      const fraction=[1,.66,.48,.72,.54,.4,.66,.50][n];
      const bytes=i===0 && n<count-1?Math.floor((end-start+1)*fraction):Math.min(remainder,end-start+1);remainder-=bytes;
      segments.push({start,end,done:bytes,route:i===0 && [1,3,6].includes(n)?'mihomo':'direct',speed:i===0&&n>0?Math.round([0,6,7,7.8,8,7,4,8.8][n]*MiB):0,state:bytes===end-start+1?'done':bytes?'active':'waiting'});
    }
    return {id:'sample-'+i,name,channel,state,total,done,speed:i===0?Math.round(48.6*MiB):i===1?Math.round(3.1*MiB):0,
      upload:i===1?96*1024:0,route:'direct',engine:byId[channel].engine,created:now-i*7800,
      segments:channel==='magnet'?[]:segments,url:'',sha256:'',path:'',error:'',sample:true};
  });
}
function load(key,otherwise){try{return JSON.parse(localStorage.getItem(key))??otherwise}catch{return otherwise}}
export const demo = location.protocol==='file:' || new URLSearchParams(location.search).get('preview')==='1';
export function asset(c,kind){return demo && location.protocol==='file:'?'../../scene-packs/'+c.scene+'/'+kind+'.webp':'/scenes/'+c.id+'/'+kind}
export function tokenFromWindow(){
 const f=new URLSearchParams(location.hash.slice(1)), t=f.get('token');
 if(t){sessionStorage.setItem('glass-session',t); history.replaceState(null,'',location.pathname+location.search)}
 return t||sessionStorage.getItem('glass-session')||'';
}
let token='';
export async function request(path, method='GET',data){
 const res=await fetch('/api/v1/'+path,{method,headers:{'Authorization':'Bearer '+token,...(data?{'Content-Type':'application/json'}:{})},body:data?JSON.stringify(data):undefined});
 if(!res.ok){let body={};try{body=await res.json()}catch{}const err=Error(body.error||('请求失败 '+res.status));err.choices=body.choices;throw err}
 return res.json();
}
export function connect(update,status){
 let ws,timer,closed=false;
 if(demo){
   const conf=load('boan-preview-settings',defaultSettings);
   update({jobs:makeSample(),system:{cpu:24,memory:46,disk_write:46.2*MiB,disk_free:284*1024*MiB,gpu:null},
     output:'~/Downloads/GlassDownloader',settings:{...defaultSettings,...conf},components:{http:true,httpx:true,curl:true,aria2:true,'yt-dlp':true,BBDown:true,ffmpeg:true},version:'0.1.0'});
   status('演示模式');return ()=>{};
 }
 token=tokenFromWindow();
 async function open(){
   if(closed)return;
   try{
     update(await request('state'));if(closed)return;
     ws=new WebSocket('ws://'+location.host+'/events');ws.onopen=()=>ws.send(token);
     ws.onmessage=e=>{if(!closed){update(JSON.parse(e.data));status('已连接')}};
     ws.onclose=()=>{if(!closed){status('正在重连');timer=setTimeout(open,1800)}};
   }catch(err){if(!closed){status(token?'连接失败':'请通过 start.cmd 启动');if(token)timer=setTimeout(open,2500)}}
 }
 open();return ()=>{closed=true;clearTimeout(timer);ws?.close()};
}
export function persistPreview(conf){localStorage.setItem('boan-preview-settings',JSON.stringify(conf))}
export function previewJob(url,c,config){
 let name;
 if(['huggingface','github','modelscope'].includes(c.id)&&/^[\w.-]+(?:\/[\w.-]+)?$/.test(url))name=url+(c.id==='github'?'.zip':'');
 else if(c.id==='java'&&/^(?:jdk\s*)?\d{1,2}$/i.test(url))name='Temurin '+url+' · Windows x64';
 else if(c.id==='python'&&/^[\w.-]+(?:==[\w.+-]+)?$/.test(url))name=url;
 else if(c.id==='linux'&&/^ubuntu\s+\d{2}\.\d{2}/i.test(url))name=url+' Desktop ISO';
 else if(c.id==='cpp'&&/^llvm\s+\d+\.\d+\.\d+$/i.test(url))name=url+' · Windows x64';
 else if(c.id==='bilibili'&&(/BV[A-Za-z0-9]{10}/.test(url)||url.includes('b23.tv/')))name=url.match(/BV[A-Za-z0-9]{10}/)?.[0]||'哔哩哔哩视频';
 else if(c.id==='arxiv'&&/^(?:arXiv:)?\d{4}\.\d{4,5}(?:v\d+)?$/i.test(url))name=url+'.pdf';
 else{let addr;try{addr=new URL(url)}catch{throw Error('请输入资源名称或有效链接')}if(!['http:','https:','magnet:'].includes(addr.protocol))throw Error('请输入 HTTP(S) 或磁力链接');name=decodeURIComponent(addr.pathname.split('/').pop()||c.name)}
 const opts=defaults(c,config);
 return {...opts,id:crypto.randomUUID(),name,channel:c.id,state:'queued',
 total:null,done:0,speed:0,upload:0,created:Date.now()/1000,segments:[],sample:true,url,path:'',sha256:'',error:''};
}

