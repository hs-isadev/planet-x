import fs from 'node:fs';
import path from 'node:path';
import {spawnSync} from 'node:child_process';

// Force browser ES-module grammar: Node's default .js syntax check can accept
// code that its ES-module loader subsequently rejects.
const files=fs.readdirSync('web').filter(name=>name.endsWith('.js'));
for(const name of files){
 const result=spawnSync(process.execPath,['--experimental-default-type=module','--check',path.join('web',name)],{stdio:'inherit'});
 if(result.status!==0)process.exit(result.status||1);
}
await import('../web/observations.js');
console.log(`PASS: ${files.length} frontend modules parse as ES modules; observation dependencies import successfully.`);
