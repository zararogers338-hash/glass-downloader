<script>
import {channels,byId,engName,routeName,engines,kernels} from './workbench.js';
import { Palette, SlidersHorizontal, Cable, HardDriveDownload, Check } from 'lucide-svelte';
export let settings, initialChannel, save, follow, setFollow, components, palettes, skins, setSkin, rescan;
let scope=initialChannel, tab='channel', draft=structuredClone(settings), msg='',saving=false;
$: c=byId[scope];
$: profile=draft.profiles[scope]||{};
function setKey(k,v){
 const next={...profile,[k]:v||null};
 if(k==='engine'){
   const route=next.route||(scope==='tor'?'tor':scope==='magnet'?'direct':draft.default_route);
   if(!kernels[v].routes.includes(route))next.route=kernels[v].routes[0];
 }
 draft={...draft,profiles:{...draft.profiles,[scope]:next}};msg='';
}
async function commit(){saving=true;try{const {speed_profile,...values}=draft;await save(values);msg='已保存，新建任务将使用这些设置。'}catch(e){msg=e.message}finally{saving=false}}
async function changeSkin(file){try{await setSkin(scope,file);msg=file?'已应用壁纸和提取的配色。':'已恢复内置壁纸。'}catch(e){msg=e.message}}
</script>
<section class="content settings">
 <div class="page-heading"><div><h1>设置</h1></div><button class="solid" on:click={commit} disabled={saving}><Check size={16}/> 保存设置</button></div>
 <div class="settingsframe"><div class="settingsnav">
 {#each [['channel','频道策略',SlidersHorizontal],['kernel','下载核心',HardDriveDownload],['network','网络与上行',Cable],['skin','外观',Palette]] as item}
 <button class:chosen={tab===item[0]} on:click={()=>tab=item[0]}><svelte:component this={item[2]} size={17}/>{item[1]}</button>
 {/each}</div><div class="settingsbody">
 {#if tab==='channel'}
 <h2>频道策略</h2><p class="subtle">保存的来源、核心和线路随频道使用，已在传输的任务沿用创建时的设置。</p>
 <label class="field">频道<select aria-label="频道" bind:value={scope}>{#each channels as x}<option value={x.id}>{x.name}</option>{/each}</select></label>
 <label class="field">下载源<select value={profile.source||'original'} on:change={e=>setKey('source',e.currentTarget.value)}><option value="original">链接原站</option>{#if scope==='huggingface'}<option value="hf-mirror">HF Mirror · 公开文件</option>{/if}</select></label>
 <label class="field">默认核心<select value={profile.engine||c.engine} on:change={e=>setKey('engine',e.currentTarget.value)}>{#each engines(scope) as k}<option value={k} disabled={!components[k]}>{engName[k]}{components[k]?'':' · 未检测到'}</option>{/each}</select></label>
 <div class="kernelhint">{kernels[profile.engine||c.engine].summary}</div>
 <label class="field">出口线路<select value={profile.route||''} on:change={e=>setKey('route',e.currentTarget.value)}>
 {#if scope==='magnet'}<option value="">频道默认 · 直连</option>{:else if scope==='tor'}<option value="">频道默认 · Tor</option>{:else}
 <option value="" disabled={!kernels[profile.engine||c.engine].routes.includes(draft.default_route)}>继承默认出口</option>
 {#each kernels[profile.engine||c.engine].routes as r}<option value={r}>{routeName[r]}</option>{/each}{/if}</select></label>
 {:else if tab==='kernel'}
 <div class="line"><h2>下载核心</h2><span class="grow"></span><button class="solid" on:click={async()=>{try{await rescan();msg='已重新检测'}catch(e){msg=e.message}}}>重新检测</button></div>
 {#each Object.values(kernels) as k}<div class="kernelrow"><span><strong>{k.name}</strong><small>{k.summary}</small></span><span>{components[k.id]?'可用':'未检测到'}</span></div>{/each}
 {:else if tab==='network'}
 <h2>网络与上行</h2><p class="subtle">本地代理只供当前下载器使用。磁力频道使用直连，洋葱频道使用 Tor。</p>
 <label class="field">默认出口<select bind:value={draft.default_route}><option value="direct">直连</option><option value="mihomo">Mihomo</option></select></label>
 <label class="field">Mihomo HTTP 端口<input type="number" min="1" max="65535" bind:value={draft.mihomo_port}/></label>
 <label class="field">Tor SOCKS 端口<input type="number" min="1" max="65535" bind:value={draft.tor_port}/></label>
 <label class="field">HTTP 分段连接上限<input type="number" min="1" max="8" bind:value={draft.connections}/></label>
 <label class="field">同时下载的任务数<input type="number" min="1" max="16" bind:value={draft.parallel_tasks}/></label>
 <label class="field">启动时恢复上次运行中的任务<input type="checkbox" bind:checked={draft.resume_on_start}/></label>
 <label class="field">HTTP 临时错误重试次数<input type="number" min="0" max="5" bind:value={draft.retries}/></label>
 <label class="field">新任务保存目录<input type="text" bind:value={draft.download_dir}/></label>
 <label class="field">单任务下载上限（KiB/s）<input type="number" min="0" max="1048576" bind:value={draft.download_kib}/></label>
 <label class="field">BT 单任务上行上限（KiB/s）<input type="number" min="0" max="1048576" bind:value={draft.upload_kib}/></label>
 <p class="subtle">0 表示不限速。仅在下载期间上传，默认完成后停止做种。</p>
 {:else}
 <h2>壁纸配色</h2><p class="subtle">从频道插画取色，用于主按钮、焦点和界面底色。线路编号和告警色跨频道保持一致。</p>
 <label class="field">频道<select aria-label="频道" bind:value={scope}>{#each channels as x}<option value={x.id}>{x.name}</option>{/each}</select></label>
 <label class="field">本地壁纸<input type="file" accept="image/jpeg,image/png,image/webp" on:change={e=>{const file=e.currentTarget.files[0];if(file)changeSkin(file);e.currentTarget.value=''}}/></label>
 {#if skins[scope]}<button class="solid" on:click={()=>changeSkin(null)}>恢复内置壁纸</button>{/if}
 <label class="field">跟随频道壁纸<input type="checkbox" checked={follow} on:change={e=>setFollow(e.currentTarget.checked)}/></label>
 <div class="swatches">{#each ['seed','accent','panel','surface','ink'] as k}<span style={'background:'+(skins[scope]?.palette||palettes[c.scene])[k]} title={k+' '+(skins[scope]?.palette||palettes[c.scene])[k]}></span>{/each}</div>
 {/if}
 {#if msg}<p role="status" class="feedback">{msg}</p>{/if}
 </div></div></section>

