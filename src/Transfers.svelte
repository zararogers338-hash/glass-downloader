<script>
import {Search, ArrowDownUp, X, Pause, Play, Trash2, File, Plus, Square} from 'lucide-svelte';
import {byId,engName,routeName,states,size,rate,eta,isActive,percent} from './workbench.js';
export let jobs=[], focus='', act, add, reveal;
let deleteDialog, deleting=false, targets=[],deleteError='',mapWidth=650;
$: columns=Math.max(12,Math.floor(mapWidth/15));
function askDelete(ids){
 targets=[...new Set(ids)].filter(id=>jobs.some(j=>j.id===id));deleteError='';
 if(targets.length)deleteDialog.showModal();
}
async function confirmDelete(){
 deleting=true;const failed=[];
 try{for(const id of targets){const j=jobs.find(x=>x.id===id);if(j && !await act(j,'delete'))failed.push(id)}
   checked=checked.filter(id=>!targets.includes(id)||failed.includes(id));
   if(targets.includes(focus)&&!failed.includes(focus))focus='';
   targets=failed;if(failed.length)deleteError='部分任务删除失败，请重试';else deleteDialog.close();
 }finally{deleting=false}
}
let search='',filter='all',sort='new',tab='常规', checked=[], isolate='';
$: rows=jobs.filter(j=>(filter==='all'||(filter==='active'?isActive(j):j.state===filter))&&j.name.toLowerCase().includes(search.toLowerCase())).sort((a,b)=>sort==='size'?b.total-a.total:sort==='name'?a.name.localeCompare(b.name):b.created-a.created);
$: selected=jobs.find(j=>j.id===focus);
const routeInfo={direct:['D1','直连','#e9c997'],mihomo:['M2','Mihomo','#99badf'],tor:['T3','Tor','#b9a5d8']};
function groups(j){return [...new Set(j.segments.map(s=>s.route||j.route))]}
function cells(j,count){
 if(j.state==='completed')return Array.from({length:count},()=>({route:j.route,fill:1}));
 const total=j.revision?j.segment_total:j.total;
 if(!total || !j.segments.length)return [];
 return Array.from({length:count},(_,i)=>{
   const a=i*total/count,b=(i+1)*total/count;
   let fill=0, route=j.route;
   for(const s of j.segments){
     const covered=Math.max(0,Math.min(b,s.start+s.done)-Math.max(a,s.start));
     if(covered){fill+=covered; route=s.route||j.route}
   }
   return {fill:Math.min(1,fill/(b-a)),route};
 });
}
function toggle(id){checked=checked.includes(id)?checked.filter(k=>k!==id):[...checked,id]}
async function batch(action){for(const id of checked){const j=jobs.find(x=>x.id===id);if(j&&(action==='pause'?isActive(j):['failed','paused'].includes(j.state)))await act(j,action)}checked=[]}
</script>
<section class="content queue">
<div class="page-heading"><div><h1>传输列表</h1></div><button class="solid" on:click={add}><Plus size={17}/>添加下载</button></div>
<div class="tools"><div class="tabs">
{#each [['all','全部'],['active','进行中'],['completed','已完成']] as t}<button class:chosen={filter===t[0]} on:click={()=>filter=t[0]}>{t[1]}</button>{/each}
</div><span class="grow"></span><label class="search"><Search size={15}/><input bind:value={search} aria-label="搜索文件" placeholder="搜索文件"/></label><label class="sort"><ArrowDownUp size={15}/><select bind:value={sort} aria-label="排序"><option value="new">最近添加</option><option value="size">大小</option><option value="name">名称</option></select></label></div>
{#if checked.length}<div class="batch">已选 {checked.length} 项 <button on:click={()=>batch('pause')}>暂停</button><button on:click={()=>batch('resume')}>继续</button><button on:click={()=>askDelete(checked)}>删除所选任务</button></div>{/if}
<div class="tablewrap"><table><thead><tr><th class="ck"><input aria-label="选择全部可见任务" type="checkbox" checked={rows.length>0&&rows.every(r=>checked.includes(r.id))} on:change={e=>checked=e.currentTarget.checked?rows.map(j=>j.id):[]}/></th><th>文件名</th><th>大小</th><th>状态</th><th>下载 ↓</th><th>上传 ↑</th><th>添加时间</th></tr></thead>
<tbody>{#each rows as j (j.id)}
<tr class:highlight={focus===j.id} on:click={()=>{focus=j.id;tab='常规';isolate=''}}>
<td class="ck"><input aria-label={'选择 '+j.name} type="checkbox" checked={checked.includes(j.id)} on:click|stopPropagation={()=>toggle(j.id)}/></td>
<td><button class="filebtn" on:click={()=>focus=j.id}><File size={18}/><span><strong>{j.name}</strong><small>{byId[j.channel]?.name||j.channel} · {engName[j.engine]}</small></span></button></td>
<td class="num">{size(j.total)}</td><td><span class:active={isActive(j)}>{states[j.state]}</span>{#if isActive(j)&&j.total}<small class="inlinepct">{percent(j)}%</small>{/if}</td><td class="num">{rate(j.speed)}</td><td class="num">{rate(j.upload??(j.channel==='magnet'?null:0))}</td>
<td>{new Date(j.created*1000).toLocaleDateString('zh-CN',{month:'short',day:'numeric'})}</td></tr>
{:else}<tr><td colspan="7" class="empty">{jobs.length?'没有匹配的文件':'尚无任务，粘贴链接即可添加下载。'}</td></tr>{/each}</tbody></table></div>
{#if selected}<div class="inspector"><div class="detailbar"><div class="tabs">{#each ['常规','进度','链路'] as t}<button class:chosen={tab===t} on:click={()=>tab=t}>{t}</button>{/each}</div><span class="grow"></span>
{#if isActive(selected)}<button class="iconbtn" title="暂停任务" on:click={()=>act(selected,'pause')}><Pause size={16}/></button>{:else if ['paused','failed'].includes(selected.state)}<button class="iconbtn" title="继续任务" on:click={()=>act(selected,'resume')}><Play size={16}/></button>{/if}
{#if isActive(selected)||['paused','failed'].includes(selected.state)}<button class="actiontext" title="取消任务" on:click={()=>act(selected,'cancel')}><Square size={13}/>取消任务</button>{/if}
<button class="actiontext" title="删除任务" on:click={()=>askDelete([selected.id])}><Trash2 size={15}/>删除任务</button><button class="iconbtn" title="收起详情" on:click={()=>focus=''}><X size={16}/></button></div>
<h3>{selected.name}</h3>
{#if selected.state==='paused'}<p class="subtle">{selected.resumable===true?'已保留分段。继续时会先核对服务器文件版本。':selected.resumable===false?'服务器未提供可验证的断点；继续时会重新传当前文件。':'任务已暂停。继续时由核心检查断点。'}</p>{/if}
{#if selected.revision}<p class="subtle">仓库快照 · {selected.revision.slice(0,10)} · {selected.files_done} / {selected.file_count} 个文件 {selected.current_file?' · '+selected.current_file:''}</p>{/if}
{#if tab==='进度'}<div class="mapmeta"><span>{size(selected.done)} / {size(selected.total)}</span><strong>{selected.total||selected.state==='completed'?percent(selected)+'%':'—'}</strong><span class="grow"></span><span>剩余 {eta(selected)}</span></div>
{#if selected.state==='completed'||(selected.segments.length && selected.total)}<div class="piece-map blue-map" bind:clientWidth={mapWidth} style={'grid-template-columns:repeat('+columns+',minmax(0,1fr))'} aria-label="按文件偏移排列的分段进度">{#each cells(selected,columns*5) as c,i}<i title={'区间 '+(i+1)+' · '+Math.round(c.fill*100)+'%'} style={'--piece:#5493ae'+';--filled:'+c.fill*100+'%;opacity:'+(isolate && c.route !== isolate ? 0.28 : 1)}></i>{/each}</div>
<div class="key"><span class="key-unit">文件头 → 文件尾</span>{#each groups(selected) as r}<button class="route-key" aria-pressed={isolate===r} title={'高亮'+routeInfo[r][1]+'分块'} on:click={()=>isolate=isolate===r?'':r}><i style="background:#5493ae"></i>{routeInfo[r][0]} · {routeInfo[r][1]}</button>{/each}<span><i class="waitbit"></i>待传输</span></div>
{:else}<p class="subtle">此任务尚无可用的分块遥测。</p>{/if}
{:else if tab==='链路'}<div class="paths"><div class="path"><span>连接</span><span>出口</span><span>文件区间</span><span>下载速率</span></div>{#each selected.segments as s,i}<div class="path"><b style={'color:'+routeInfo[s.route||selected.route][2]}>{routeInfo[s.route||selected.route][0]} / {String(i+1).padStart(2,'0')}</b><span>{routeName[s.route||selected.route]}</span><span>{size(s.start)} → {size(s.end==null?null:s.end+1)}</span><span>{rate(isActive(selected)?s.speed:0)}</span></div>{:else}<p class="subtle">外部核心未提供逐连接数据。</p>{/each}</div>
{:else}<div class="mapmeta"><span>{size(selected.done)} / {size(selected.total)}</span><span class="grow"></span><strong>{selected.total||selected.state==='completed'?percent(selected)+'%':'大小未知'}</strong></div><progress class="whole-file" aria-label="整条文件进度" max="100" value={selected.state==='completed'||selected.total?percent(selected):undefined}></progress>
<dl><dt>添加时间</dt><dd>{new Date(selected.created*1000).toLocaleString('zh-CN')}</dd><dt>核心 / 线路</dt><dd>{engName[selected.engine]} / {routeName[selected.route]}</dd>{#if selected.media}<dt>媒体选项</dt><dd>{selected.media.mode==='audio'?'仅音频':'视频＋音频'}{selected.media.mode==='video'?' · '+(selected.media.quality==='auto'?'自动画质':selected.media.quality):''}</dd>{/if}<dt>文件位置</dt><dd>{selected.path||'完成后显示'} {#if selected.path}<button class="route-key" on:click={()=>reveal(selected)}>打开目录 ↗</button>{/if}</dd><dt>SHA-256</dt><dd>{selected.sha256||'暂无'}</dd>{#if selected.error}<dt>错误</dt><dd>{selected.error}</dd>{/if}</dl>{/if}</div>{/if}
</section>


<dialog class="confirm-stop" bind:this={deleteDialog} on:cancel={e=>{if(deleting)e.preventDefault()}}><h2>删除 {targets.length} 个下载任务？</h2><p>{targets.length===1?(jobs.find(j=>j.id===targets[0])?.name||''):''}</p><p class="subtle">活动任务会停止，任务记录和未完成分片会清理。已下载完成的文件会保留。</p><p role="status">{deleteError}</p><div class="line"><span class="grow"></span><button class="neutralbtn" disabled={deleting} on:click={()=>deleteDialog.close()}>返回</button><button class="solid" disabled={deleting} on:click={confirmDelete}>{deleting?'删除中':'确认删除'}</button></div></dialog>
