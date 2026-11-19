<script>
import {onDestroy} from 'svelte';
import {demo,request} from './workbench.js';
export let input='',engine='yt-dlp',route='direct',port,mode='video',quality='auto';
let options=[],message='',generation=0,timer;
function refresh(text,core,outlet,proxyPort,mediaMode){
 clearTimeout(timer);const seq=++generation;options=[];quality='auto';message='';
 if(mediaMode==='audio'||!/(BV[a-zA-Z0-9]{10}|b23\.tv\/[^\s]+)/.test(text))return;
 message='读取画质…';
 timer=setTimeout(async()=>{
   try{
     const result=demo?{engine:core,options:core==='BBDown'?[{id:'bb:480P 清晰',label:'480P 清晰 · 示例'}]:
        [{id:'v:30080',label:'1080p · 示例'},{id:'v:30032',label:'480p · 示例'}]}:
        await request('bilibili/formats','POST',{url:text.trim()});
     if(seq!==generation)return;
     options=result.engine===core?result.options:[];message='';
   }catch(e){if(seq===generation)message=e.message}
 },450);
}
$: refresh(input,engine,route,port,mode);
onDestroy(()=>{generation++;clearTimeout(timer)});
</script>
<div class="bili-options">
 <label>内容<select aria-label="内容" bind:value={mode}><option value="video">视频＋音频</option><option value="audio">仅音频</option></select></label>
 {#if mode==='video'}<label>清晰度<select aria-label="清晰度" bind:value={quality} title={engine==='BBDown'?'按核心返回的画质名称优先选择':'选择当前视频的具体画质'}><option value="auto">自动 · 最佳可用</option>{#each options as o}<option value={o.id}>{o.label}</option>{/each}</select></label>{/if}
 {#if message}<small role="status">{message} {#if !message.includes('…')}<button on:click={()=>refresh(input,engine,route,port,mode)}>重试</button>{/if}</small>{/if}
</div>

