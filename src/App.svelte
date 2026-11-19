<script>
import {onMount,tick} from 'svelte';
import {fade,fly} from 'svelte/transition';
import {Compass, List, Settings as Gear, ArrowDown, ArrowUp, ChevronLeft, ChevronRight, Link as LinkIcon, LayoutGrid, Activity, X, Download, Play, Pause, Square, Layers, Coffee} from 'lucide-svelte';
import {channels,byId,demo,asset,connect,request,previewJob,defaultSettings,persistPreview,rate,size,eta,percent,isActive,states,defaults,engName,routeName} from './workbench.js';
import palettes from './palettes.json';
import {getWallpaper,clearWallpaper,importWallpaper} from './wallpaper.js';
import BiliOptions from './BiliOptions.svelte';
import speedProfiles from '../speed-profiles.json';
import {stripScroll,swipeScene} from './channel-gestures.js';
import Transfers from './Transfers.svelte';
import SettingsPage from './Settings.svelte';
let selected=byId.general,page='home',drawer='',focus='',input='',busy=false,note='',alertTimer;
let repoChoices=[],repoDialog,batchDialog,batchText='',batchReport='',batchBusy=false;
let choosing=false, taskTab='current', pendingOp='',batchOp='',batchStop=false,stopSingle=false, cancelDialog,cancelJob, drafts={};
let mediaMode='video',mediaQuality='auto',speedPending=false;
let state={jobs:[],system:{},settings:defaultSettings,output:'',components:{}},status='正在连接';
let follow=true,reduced=false,serial=0,field,sceneW=1440,sceneH=900,dialog,returnFocus;
let skins={},alive=true;
const order=channels;
const names={general:'文件直链',huggingface:'模型与数据集',modelscope:'模型与数据集',bilibili:'视频与分集',github:'版本发布',arxiv:'论文与预印本',magnet:'种子与磁力',video:'音视频',tor:'洋葱网络',java:'开发工具包',cpp:'编译工具链',python:'解释器与软件包',linux:'发行版镜像'};
const story={huggingface:'快门响之前',modelscope:'晚班车到站前',bilibili:'晴空下的 2233',github:'发布前的最后一行',arxiv:'读到这里',magnet:'第一颗种子',video:'第一帧',tor:'洋葱与番茄',python:'雪夜打包',java:'杯沿的热气',cpp:'指向何处',linux:'冰原来信'};
const placeholders={huggingface:'模型名、组织/模型或文件链接',modelscope:'组织/模型名或文件链接',github:'仓库名、作者/仓库或 Release 链接',bilibili:'BV 号或粘贴 B 站分享文本',arxiv:'论文编号或 PDF 链接',java:'JDK 版本号或安装包链接',python:'包名、Python 版本或安装包链接',linux:'Ubuntu 24.04 或镜像链接',cpp:'LLVM 版本号或工具链链接'};
$: conf=state.settings;
$: primary=state.jobs.find(j=>j.state==='running')||state.jobs.find(isActive);
$: displayed=taskTab==='current'?state.jobs.filter(j=>isActive(j)||j.state==='paused').slice(0,2):state.jobs.filter(j=>j.state==='completed').slice(0,2);
$: totalDown=state.jobs.reduce((a,j)=>a+(j.speed||0),0);
$: totalUp=state.jobs.some(j=>j.channel==='magnet' && isActive(j) && j.upload==null)?null:state.jobs.reduce((a,j)=>a+(j.upload||0),0);
$: pal=follow?(skins[selected.id]?.palette||palettes[selected.scene]):palettes['arxiv-tea-print'];
$: colorStyle=Object.entries(pal).map(([k,v])=>'--'+k+':'+v).join(';');
$: level=conf.speed_profile||'high';
$: scale=Math.max(sceneW/1672,sceneH/941);
$: hx=sceneW/2+(.609-.5)*1672*scale;
$: hy=sceneH/2+(.559-.5)*941*scale;
onMount(()=>{
 follow=localStorage.getItem('boan-follow')!=='off';
 reduced=matchMedia('(prefers-reduced-motion:reduce)').matches;
 for(const c of channels)refreshSkin(c.id).catch(()=>{});
 const disconnect=connect(s=>state=s,s=>status=s);
 return ()=>{alive=false;disconnect();for(const s of Object.values(skins))URL.revokeObjectURL(s.url)};
});
async function refreshSkin(id){
 const row=await getWallpaper(id);if(!alive)return;
 const old=skins[id]?.url;const next={...skins};
 if(row)next[id]={palette:row.palette,url:URL.createObjectURL(row.blob)};else delete next[id];
 skins=next;if(old){await tick();URL.revokeObjectURL(old)}
}
async function setSkin(id,file){
 if(file)await importWallpaper(id,file);else await clearWallpaper(id);
 await refreshSkin(id);
}
function followTheme(x){follow=x;localStorage.setItem('boan-follow',x?'on':'off')}
function flash(s){note=s;clearTimeout(alertTimer);alertTimer=setTimeout(()=>note='',4200)}
function go(p){++serial;page=p;drawer='';if(p==='queue'&&!focus)focus=primary?.id||state.jobs[0]?.id||'';}
async function choose(c){
 const seq=++serial;
 if(selected.id!==c.id){const img=new Image();img.src=skins[c.id]?.url||asset(c,'wallpaper');try{await img.decode()}catch{flash('壁纸载入失败');return}}
 if(seq!==serial)return;
 drafts[selected.id]=input;selected=c;input=drafts[c.id]||'';
 choosing=false;go('home');
 await tick();
 document.querySelector('.sidechannels [aria-current="true"]')?.scrollIntoView({block:'nearest',inline:'nearest'});
}
function stepChannel(n){choose(order[(order.indexOf(selected)+n+order.length)%order.length])}
function mediaFields(c,bulk=false){return c.id==='bilibili'?{media:{mode:mediaMode,quality:bulk||mediaMode==='audio'?'auto':mediaQuality}}:{}}
async function setSpeed(value){
 if(speedPending||!speedProfiles[value])return;speedPending=true;
 try{
   if(demo){const settings={...conf,speed_profile:value};persistPreview(settings);state={...state,settings}}
   else{await request('settings','PATCH',{speed_profile:value});state=await request('state')}
 }catch(e){flash(e.message)}finally{speedPending=false}
}
function queueView(j){focus=j?.id||'';go('queue')}
async function add(url=input){
 if(!url.trim()){field?.focus();flash(placeholders[selected.id]||'请粘贴'+selected.hint);return}
 if(busy)return;
 busy=true;stopSingle=false;const target=selected;pendingOp=crypto.randomUUID();
 try{
   let job;
   if(demo){job={...previewJob(url.trim(),selected,conf),...mediaFields(selected)};state={...state,jobs:[job,...state.jobs]}}
   else{job=await request('jobs','POST',{url:url.trim(),submission_id:pendingOp,...mediaFields(target),channel:target.id==='general'?undefined:target.id});state=await request('state')}
   if(!stopSingle){focus=job.id;if(selected.id===target.id && (input===url||!input))input='';flash(demo?'已加入演示队列':'已加入下载队列')}
 }catch(e){if(!stopSingle){if(e.choices?.length){await choose(target);repoChoices=e.choices;repoDialog.showModal()}else flash(e.message)}}finally{busy=false;pendingOp=''}
}
async function stopAdding(batch=false){
 const id=batch?batchOp:pendingOp;
 if(batch)batchStop=true;else stopSingle=true;
 try{if(id&&!demo)await request('submissions/'+id+'/stop','POST');flash(batch?'已停止添加，之前入队的任务继续下载':'已中断解析')}
 catch(err){flash(err.message)}
}
function openBatch(text=''){batchText=text;batchReport='';batchDialog.showModal()}
function pasted(e){
 const text=e.clipboardData?.getData('text/plain')||'';
 const lines=text.trim().split(/\r?\n/).map(v=>v.trim()).filter(Boolean);
 if(lines.length>1 && lines.every(v=>/^(https?:\/\/|magnet:\?|BV[a-zA-Z0-9]{10})/.test(v)||/^[\w.-]+\/[\w.-]+$/.test(v))){
   e.preventDefault();openBatch(lines.join('\n'));
 }
}
async function submitBatch(){
 if(batchBusy)return;
 const lines=[...new Set(batchText.trim().split(/\r?\n/).map(v=>v.trim()).filter(Boolean))];
 if(!lines.length||lines.length>100){batchReport='一次可添加 1–100 条';return}
 batchBusy=true;batchStop=false;const target=selected;const failed=[];let count=0;let firstError='';
 try{for(const [i,url] of lines.entries()){
   if(batchStop){failed.push(...lines.slice(i));break}
   batchOp=crypto.randomUUID();
   try{if(demo){const j={...previewJob(url,target,conf),...mediaFields(target,true)};state={...state,jobs:[j,...state.jobs]}}
      else await request('jobs','POST',{url,submission_id:batchOp,...mediaFields(target,true),channel:target.id==='general'?undefined:target.id});
      if(batchStop){failed.push(...lines.slice(i));break}
      count++;batchReport='已处理 '+count+' / '+lines.length
   }catch(e){failed.push(url);if(!firstError&&!batchStop)firstError=e.choices?.length?'有重名，请填写完整作者/名称':e.message}
   finally{batchOp=''}
 }
 batchText=failed.join('\n');batchReport='已提交 '+count+' 项'+(failed.length?'；剩余 '+failed.length+' 项 '+firstError:'');
 if(!demo)state=await request('state');
 if(!failed.length){batchDialog.close();flash(batchReport)}
 }catch(e){batchReport=e.message}finally{batchBusy=false}
}
async function act(j,a){
 if(a==='cancel'){cancelJob=j;cancelDialog.showModal();return}
 if(a==='confirmCancel')a='cancel';
 try{if(demo){state={...state,jobs:['delete','remove'].includes(a)?state.jobs.filter(x=>x.id!==j.id):state.jobs.map(x=>x.id===j.id?{...x,state:a==='cancel'?'cancelled':a==='pause'?'paused':'running',speed:0,upload:0}:x)}}
 else{await request('jobs/'+j.id+'/'+a,'POST');state=await request('state')}return true}catch(e){flash(e.message);return false}
}
async function saveSettings(s){
 if(demo){
   if(![s.upload_kib,s.download_kib].every(n=>Number.isInteger(n)&&n>=0&&n<=1048576)||![s.mihomo_port,s.tor_port].every(p=>Number.isInteger(p)&&p>0&&p<65536)||!(s.connections>=1&&s.connections<=8)||!(s.parallel_tasks>=1&&s.parallel_tasks<=16)||!(s.retries>=0&&s.retries<=5))throw Error('请检查端口、连接数、重试次数和限速值');
   const next={...conf,...s};persistPreview(next);state={...state,settings:structuredClone(next)};
 }else{await request('settings','PATCH',s);state=await request('state')}
}
async function focusInput(){choosing=false;go('home');await tick();field?.focus()}
function showAll(){returnFocus=document.activeElement;dialog.showModal()}
function onKey(e){
 if(document.querySelector('dialog[open]'))return;
 if(e.key==='Escape'){if(busy)stopAdding();else if(choosing)choosing=false;else if(drawer)drawer='';else if(page!=='home')go('home')}
 if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='l'){e.preventDefault();focusInput()}
 if(page==='home'&&e.altKey&&['ArrowLeft','ArrowRight'].includes(e.key)){e.preventDefault();choose(order[(order.indexOf(selected)+(e.key==='ArrowRight'?1:-1)+order.length)%order.length])}
}
</script>
<svelte:window on:keydown={onKey}/>
<div class="app" style={colorStyle}>
<aside class="rail">
<button class="brand" title="泊岸 · 频道主页" on:click={()=>go('home')} aria-label="泊岸"><svg viewBox="0 0 32 32" fill="currentColor"><path d="m4 20 13-16-2 16zm13 0 2-12 8 12zM4 23h23l-5 4H9z"/></svg></button>
<div class="railnav"><button class:current={page==='home'} on:click={()=>go('home')} title="频道主页"><Compass/><small>频道</small></button><button class:current={page==='queue'} on:click={()=>go('queue')} title="传输列表"><List/><small>传输</small></button></div>
<div class="sidechannels" aria-label="下载区">{#each order as c}<button class:selected-channel={selected.id===c.id&&page==='home'} aria-current={selected.id===c.id&&page==='home'} title={c.name} aria-label={'切换到'+c.name} on:click={()=>choose(c)}><img src={skins[c.id]?.url||asset(c,'preview')} alt="" draggable="false"/><small>{c.name}</small></button>{/each}</div>
<button class:current={choosing&&page==='home'} class="railtool" on:click={()=>{go('home');choosing=!choosing}} aria-label="频道选台" title="频道选台"><LayoutGrid/></button><button class:current={page==='settings'} class="railtool" on:click={()=>go('settings')} aria-label="设置" title="设置"><Gear/></button></aside>
<main>
{#if page==='home'}
<div class="scene" use:swipeScene={stepChannel} bind:clientWidth={sceneW} bind:clientHeight={sceneH}>
{#key selected.id}<div class="wallpaper" style={'background-image:url("'+(skins[selected.id]?.url||asset(selected,'wallpaper'))+'")'} in:fade={{duration:reduced?0:400}} out:fade={{duration:reduced?0:250}}></div>{/key}
<div class="shade"></div>
<div class="scenehead"><span class="wordmark">泊岸</span><span class="divider"></span><span>频道</span><div class="grow"></div>{#if demo}<span class="previewflag">交互样稿</span>{/if}<button class="monitorbtn" aria-expanded={drawer==='monitor'} on:click={()=>drawer=drawer==='monitor'?'':'monitor'}><Activity size={16}/>系统状态</button></div>
{#if !choosing}<div class="entry"><div class="scene-copy">{#key selected.id}<div in:fly={{duration:reduced?0:300,x:reduced?0:13}}><div class="eyebrow light"><i></i>{names[selected.id]}</div><h1 class:long={selected.name.length>9}>{selected.name}</h1>{#if story[selected.id]}<p class="scene-title">{story[selected.id]}</p>{/if}</div>{/key}</div>
<form id="resource-entry" class="quickform" on:submit|preventDefault={()=>add()}><LinkIcon size={17}/><input bind:this={field} aria-label="资源链接" on:paste={pasted} bind:value={input} placeholder={placeholders[selected.id]||'粘贴'+selected.hint}/><kbd>↵</kbd></form>
{#if selected.id==='bilibili'}<BiliOptions {input} engine={defaults(selected,conf).engine} route={defaults(selected,conf).route} port={conf.mihomo_port} bind:mode={mediaMode} bind:quality={mediaQuality}/>{/if}
{#if selected.quick}<button class="quickjdk" on:click={()=>add(selected.quick.url)}><Coffee size={14}/>{selected.quick.label}</button>{/if}</div>
{#if selected.quick && !skins[selected.id]}<button class="hotspot" style={'left:'+hx+'px;top:'+hy+'px'} title={selected.quick.label} aria-label="点咖啡杯下载 JDK" on:click={()=>add(selected.quick.url)}></button>{/if}
<div class="launcherbase">
<section class="dispatch"><div class="dispatchhead"><button class:under={taskTab==='current'} on:click={()=>taskTab='current'}>当前传输</button><button class:under={taskTab==='history'} on:click={()=>taskTab='history'}>最近完成</button><span class="grow"></span><button title="进入任务列表" aria-label="进入任务列表" on:click={()=>go('queue')}><ChevronRight size={16}/></button></div>
{#each displayed as j (j.id)}<div class="dispatchrow"><button class="playing" on:click={()=>queueView(j)}><span class="ring" style={'--progress:'+percent(j)+'%'}><b>{j.total||j.state==='completed'?percent(j)+'%':'…'}</b></span><span class="playingcopy"><strong title={j.name}>{j.name}</strong><small>{states[j.state]} · {j.state==='running'?rate(j.speed)+' · 剩余 '+eta(j):size(j.done)}</small></span></button>
{#if isActive(j)||j.state==='paused'}<button class="transportbtn" title={j.state==='paused'?'继续此任务':'暂停此任务'} aria-label={j.state==='paused'?'继续此任务':'暂停此任务'} on:click={()=>act(j,j.state==='paused'?'resume':'pause')}>{#if j.state==='paused'}<Play size={15}/>{:else}<Pause size={15}/>{/if}</button>{/if}</div>
{:else}<div class="quietline">{taskTab==='current'?'队列空闲':'还没有已完成的任务'}</div>{/each}</section>
<div class="launch-controls"><button class="switch-channel" on:click={()=>choosing=true}><Layers size={14}/>切换频道</button><div class="launchtogether">{#if busy}<button class="launchcta" on:click={()=>stopAdding()}><Square size={20}/>停止解析</button>{:else}<button class="launchcta" type="submit" form="resource-entry" title="开始下载" aria-label="开始下载"><span class="launchicon"><ArrowDown size={19}/></span>开始下载</button>{/if}<button class="batchround" title="批量添加" aria-label="批量添加" on:click={()=>openBatch()}><List size={21}/></button></div></div>
</div>
{:else}<div class="selector-panel" in:fly={{duration:reduced?0:260,y:reduced?0:14}}><div class="selector-caption"><div class="eyebrow light">{names[selected.id]}</div><h2>{selected.name}</h2></div><div class="decktop"><b>选择频道</b><div class="deckline"></div><button class="allbtn" on:click={showAll}>全部频道 <LayoutGrid size={13}/></button><span class="grow"></span><button aria-label="收起选台" on:click={()=>choosing=false}><X size={15}/></button></div>
<div class="dock scroll-dock" use:stripScroll>{#each order as c}<button class:selected-tile={c.id===selected.id} aria-pressed={c.id===selected.id} on:click={()=>choose(c)}><div class="poster" style={'background-image:url("'+(skins[c.id]?.url||asset(c,'preview'))+'")'}><div class="cutmark"></div></div><span>{c.name}</span></button>{/each}</div></div>{/if}
{#if drawer==='monitor'}<div class="monitor"><div class="line"><strong>系统状态</strong><span class="grow"></span><button class="iconbtn" aria-label="关闭监控" on:click={()=>drawer=''}><X size={16}/></button></div>
{#each [['CPU',state.system.cpu],['内存',state.system.memory],['GPU',state.system.gpu]] as m}<div class="met"><span>{m[0]}</span><b>{m[1]==null?'未采集':m[1]+'%'}</b></div>{#if m[1]!=null}<progress max="100" value={m[1]}></progress>{/if}{/each}
<div class="met"><span>磁盘写入</span><b>{rate(state.system.disk_write)}</b></div><div class="met"><span>磁盘可用</span><b>{size(state.system.disk_free)}</b></div></div>{/if}
</div>
{:else if page==='queue'}<Transfers jobs={state.jobs} bind:focus {act} add={focusInput} reveal={async j=>{if(demo){flash('演示任务没有本地文件');return}try{await request('jobs/'+j.id+'/folder','POST')}catch(e){flash(e.message)}}}/>
{:else}<SettingsPage settings={conf} initialChannel={selected.id} save={saveSettings} {follow} setFollow={followTheme} components={state.components} {palettes} {skins} {setSkin} rescan={async()=>{if(!demo)state={...state,components:await request('components/rescan','POST')}}}/>{/if}
<footer><span class="line"><i class:offline={!demo&&status!=='已连接'}></i>{demo?'演示数据':status}</span><span class="footsep"></span><span><ArrowDown size={13}/>{rate(totalDown)}</span><span><ArrowUp size={13}/>{rate(totalUp)}</span><label class="speed-switch" title="每任务限速。HTTP 核心即时生效，外部核心在启动或继续任务时应用。"><span>限速</span><select aria-label="速度档位" value={level} disabled={speedPending} on:change={e=>setSpeed(e.currentTarget.value)}>{#each Object.entries(speedProfiles) as [id,v]}<option value={id}>{v.name} · {v.down?(v.down/1024)+' MiB/s':'配置上限'}</option>{/each}</select></label><span class="grow"></span><span>{engName[defaults(selected,conf).engine]}</span><span class="footsep"></span><span>{routeName[defaults(selected,conf).route]}</span></footer>
</main>
{#if note}<div class="toast" role="status">{note}</div>{/if}
<dialog bind:this={batchDialog} on:cancel={e=>{if(batchBusy){e.preventDefault();stopAdding(true)}}}><div class="line"><h2>批量添加 · {selected.name}</h2><span class="grow"></span><button class="iconbtn" disabled={batchBusy} on:click={()=>batchDialog.close()} aria-label="关闭批量添加"><X size={18}/></button></div><p class="subtle">每行一个资源，使用当前频道的默认设置。{selected.id==='bilibili'?'批量沿用音频／视频模式，视频逐条自动选择画质。':''}</p><textarea class="batchinput" rows="7" aria-label="批量资源" bind:value={batchText}></textarea><div class="line"><span class="subtle" role="status">{batchReport}</span><span class="grow"></span>{#if batchBusy}<button class="solid" on:click={()=>stopAdding(true)}>停止后续添加</button>{/if}<button class="solid" disabled={batchBusy} on:click={submitBatch}>{batchBusy?'正在添加':'加入队列'}</button></div></dialog>
<dialog class="confirm-stop" bind:this={cancelDialog}><h2>取消这个任务？</h2><p>{cancelJob?.name}</p><p class="subtle">取消会结束传输并清理任务的临时分片。要稍后继续，请使用暂停。</p><div class="line"><span class="grow"></span><button class="neutralbtn" on:click={()=>cancelDialog.close()}>返回</button><button class="solid" on:click={()=>{const job=cancelJob;cancelDialog.close();act(job,'confirmCancel')}}>确认取消</button></div></dialog>
<dialog bind:this={repoDialog}><div class="line"><h2>选择仓库</h2><span class="grow"></span><button class="iconbtn" aria-label="关闭仓库选择" on:click={()=>repoDialog.close()}><X size={18}/></button></div><p class="subtle">按作者确认要下载的仓库。</p><div class="repochoices">{#each repoChoices as repo}<button on:click={()=>{repoDialog.close();input=repo;add(repo)}}>{repo}<ArrowDown size={15}/></button>{/each}</div></dialog>
<dialog bind:this={dialog} on:close={()=>returnFocus?.focus()}><div class="line"><h2>全部频道</h2><div class="grow"></div><button class="iconbtn" aria-label="关闭全部频道" on:click={()=>dialog.close()}><X size={18}/></button></div><div class="allgrid">{#each order as c}<button on:click={()=>{dialog.close();choose(c)}}><img src={(skins[c.id]?.url||asset(c,'preview'))} alt=""/><strong>{c.name}</strong></button>{/each}</div></dialog>
</div>

