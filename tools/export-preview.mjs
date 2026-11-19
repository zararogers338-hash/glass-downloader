import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
const index=readFileSync('dist/index.html','utf8');
const js=index.match(/src="(\/assets\/[^"]+\.js)"/)[1];
const css=index.match(/href="(\/assets\/[^"]+\.css)"/)[1];
const preview=index.replace(/<script type="module"[^>]*><\/script>/,'').replace(/<link rel="stylesheet"[^>]+>/,
  ()=>'<style>'+readFileSync('dist'+css,'utf8')+'</style>').replace('</body>',()=>'<script type="module">'+readFileSync('dist'+js,'utf8').replaceAll('</script','<\\/script')+'</script></body>');
mkdirSync('deliverables/concept',{recursive:true});
writeFileSync('deliverables/concept/launcher-v2.html',preview);

