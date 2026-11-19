// Isolated end-to-end check. Never touches the user's queue or downloads.
import assert from 'node:assert/strict';
import http from 'node:http';
import {spawn} from 'node:child_process';
import {createHash} from 'node:crypto';
import {mkdtempSync, readFileSync} from 'node:fs';
import {join,resolve} from 'node:path';
import {tmpdir} from 'node:os';
import {chromium} from 'playwright-core';
const tmp=mkdtempSync(join(tmpdir(),'boan-check-'));
const file=Buffer.alloc(12*1024*1024,0xa9);
const expected=createHash('sha256').update(file).digest('hex');
const requests=[];
const fixture=http.createServer((req,res)=>{
 const [s,e]=(req.headers.range?.slice(6).split('-')||['0',String(file.length-1)]).map(Number);
 requests.push([s,e]);res.setHeader('ETag','"boan-check"');res.setHeader('Content-Length',e-s+1);res.setHeader('Content-Type','application/octet-stream');
 if(req.headers.range){res.statusCode=206;res.setHeader('Content-Range','bytes '+s+'-'+e+'/'+file.length)}
 let i=s;const timer=setInterval(()=>{const stop=Math.min(i+65536,e+1);res.write(file.subarray(i,stop));i=stop;if(i>e){clearInterval(timer);res.end()}},65);
 res.on('close',()=>clearInterval(timer));
});
await new Promise(r=>fixture.listen(0,'127.0.0.1',r));
const child=spawn(process.platform==='win32'?'.venv/Scripts/python.exe':'.venv/bin/python',['launch.py','--headless','--port','0','--data',join(tmp,'data'),'--output',join(tmp,'out')],{windowsHide:true});
let browser;
try{
 const origin=await new Promise((ok,no)=>{let line='';const t=setTimeout(()=>no(Error('Service start timeout')),10000);child.once('exit',code=>{clearTimeout(t);no(Error('Service exit '+code))});child.stdout.on('data',d=>{line+=d;const m=line.match(/http:\/\/127\.0\.0\.1:\d+/);if(m){clearTimeout(t);ok(m[0])}})});
 const token=readFileSync(join(tmp,'data/api-token'),'ascii');
 const h={Authorization:'Bearer '+token};
 assert.equal((await fetch(origin+'/api/v1/state')).status,401);
 assert.equal((await fetch(origin+'/api/v1/state',{headers:{...h,Origin:'https://example.org'}})).status,403);
 browser=await chromium.launch({channel:process.env.BROWSER_CHANNEL||'msedge',headless:true});
 const page=await browser.newPage({viewport:{width:1440,height:850}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(origin+'/#token='+token);await page.getByText('已连接',{exact:true}).waitFor();
 await page.getByRole('heading',{name:'通用下载',exact:true}).waitFor();
 await page.getByLabel('速度档位').selectOption('low');
 await page.waitForFunction(()=>!document.querySelector('.speed-switch select').disabled);
 assert.equal((await (await fetch(origin+'/api/v1/state',{headers:h})).json()).settings.speed_profile,'low');
 await page.getByLabel('速度档位').selectOption('high');
 await page.waitForFunction(()=>!document.querySelector('.speed-switch select').disabled);
 await page.getByRole('button',{name:'设置',exact:true}).click();
 await page.getByLabel('频道',{exact:true}).selectOption('huggingface');await page.getByLabel('出口线路').selectOption('mihomo');await page.getByRole('button',{name:'保存设置'}).click();
 await page.getByRole('status').filter({hasText:'已保存'}).waitFor();
 const planReq=async(url)=>(await fetch(origin+'/api/v1/plan',{method:'POST',headers:{...h,'Content-Type':'application/json'},body:JSON.stringify({url})})).json();
 assert.equal((await planReq('https://huggingface.co/org/repo/resolve/main/model.bin')).route,'mihomo');
 await page.getByLabel('出口线路').selectOption('');
 await Promise.all([page.waitForResponse(r=>r.url().endsWith('/api/v1/settings')&&r.status()===200),page.getByRole('button',{name:'保存设置'}).click()]);
 await page.getByTitle('频道主页',{exact:true}).click();
 await page.getByRole('button',{name:'切换到魔搭',exact:true}).click();await page.getByRole('heading',{name:'魔搭',exact:true}).waitFor();
 await page.getByLabel('资源链接').fill('http://127.0.0.1:'+fixture.address().port+'/fixture.bin');
 await page.getByRole('button',{name:'开始下载',exact:true}).click();await page.locator('.playingcopy strong',{hasText:'fixture.bin'}).waitFor();
 const getJobs=async()=>(await fetch(origin+'/api/v1/jobs',{headers:h})).json();
 await page.waitForTimeout(400);
 await page.locator('.playing').click();await page.getByTitle('暂停任务').click();await page.getByTitle('继续任务',{exact:true}).waitFor();
 const paused=(await getJobs())[0];assert.equal(paused.state,'paused');assert.equal(paused.segments.length,4);assert.ok(paused.done>0);
 await page.getByTitle('继续任务',{exact:true}).click();await page.waitForFunction(()=>document.querySelector('tbody')?.textContent.includes('已完成'),{},{timeout:30000});
 const job=(await getJobs())[0];assert.equal(job.sha256,expected);assert.equal(createHash('sha256').update(readFileSync(job.path)).digest('hex'),expected);
 assert.ok(requests.some(([a])=>a>0 && a%(file.length/4)!==0),'resumed range');
 await page.locator('.whole-file').waitFor();
 await page.getByRole('button',{name:'进度',exact:true}).click();
 await page.locator('.blue-map i').first().waitFor();
 await page.getByRole('checkbox',{name:'选择 fixture.bin'}).check();
 await page.getByRole('button',{name:'删除所选任务'}).click();
 await page.getByRole('button',{name:'确认删除'}).click();
 await page.getByText('尚无任务，粘贴链接即可添加下载。').waitFor();
 assert.equal((await getJobs()).length,0);
 assert.equal(createHash('sha256').update(readFileSync(job.path)).digest('hex'),expected);
 assert.deepEqual(errors,[]);console.log('PASS: authenticated REST + WebSocket, settings, channel switch, UI enqueue, four ranges, pause/resume, disk SHA-256');
}finally{await browser?.close();child.kill();fixture.closeAllConnections();fixture.close()}

