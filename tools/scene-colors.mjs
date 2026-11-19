import {readFileSync, writeFileSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import {paletteFromPixels} from '../src/theme.js';

const scenes = [...new Set(JSON.parse(readFileSync('channels.json','utf8')).map(c=>c.scene))];
const colors = {};
for (const id of scenes) {
  const sample = execFileSync('python', ['-c',
    "from PIL import Image;import sys;im=Image.open(sys.argv[1]).convert('RGB').resize((96,54));sys.stdout.buffer.write(im.tobytes())",
    'scene-packs/'+id+'/preview.webp']);
  const pixels=[];
  for(let i=0;i<sample.length;i+=3) pixels.push((0xff000000 | sample[i]<<16 | sample[i+1]<<8 | sample[i+2])>>>0);
  colors[id]=paletteFromPixels(pixels);
}
writeFileSync('src/palettes.json',JSON.stringify(colors,null,2)+'\n');

