import {paletteFromPixels} from './theme.js';
let opened;
function db(){
 if(!opened) opened=new Promise((ok,no)=>{
   const req=indexedDB.open('boan-wallpapers-v1',1);
   req.onupgradeneeded=()=>req.result.createObjectStore('scenes');
   req.onsuccess=()=>ok(req.result);
   req.onerror=()=>{opened=undefined;no(req.error)};
 });
 return opened;
}
export async function wallpaperOp(mode,run){
 const database=await db();
 return new Promise((ok,no)=>{
   const transaction=database.transaction('scenes',mode);
   const req=run(transaction.objectStore('scenes'));
   transaction.oncomplete=()=>ok(req.result);
   transaction.onerror=()=>no(transaction.error);
   transaction.onabort=()=>no(transaction.error??Error('本地图片写入中断'));
 });
}
export const getWallpaper=id=>wallpaperOp('readonly',s=>s.get(id));
export const clearWallpaper=id=>wallpaperOp('readwrite',s=>s.delete(id));
export async function importWallpaper(id,file){
 if(!['image/jpeg','image/png','image/webp'].includes(file.type))throw Error('请选择 PNG、JPEG 或 WebP 图片');
 if(file.size>100*1024*1024)throw Error('图片超过 100 MiB');
 const img=await createImageBitmap(file);
 try{
   const canvas=document.createElement('canvas'),ctx=canvas.getContext('2d',{willReadFrequently:true});
   const scale=Math.min(1,3840/img.width,2160/img.height);
   canvas.width=Math.max(1,Math.round(img.width*scale));canvas.height=Math.max(1,Math.round(img.height*scale));
   ctx.drawImage(img,0,0,canvas.width,canvas.height);
   const blob=await new Promise((ok,no)=>canvas.toBlob(b=>b?ok(b):no(Error('图片转换失败')),'image/webp',.91));
   canvas.width=96;canvas.height=54;ctx.drawImage(img,0,0,96,54);
   const pixels=ctx.getImageData(0,0,96,54).data, colors=[];
   for(let i=0;i<pixels.length;i+=4)if(pixels[i+3]>127)colors.push((0xff000000|pixels[i]<<16|pixels[i+1]<<8|pixels[i+2])>>>0);
   const palette=paletteFromPixels(colors);
   await wallpaperOp('readwrite',s=>s.put({blob,palette},id));
   return palette;
 }finally{img.close()}
}

