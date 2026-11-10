import {chromium} from '@playwright/test';
const b=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true,args:['--no-sandbox','--enable-unsafe-swiftshader']});
const p=await b.newPage({viewport:{width:390,height:844}});
await p.goto('http://127.0.0.1:8000/?ra=133.79512916666667&dec=-7.245147222222222&fov=8');
await p.waitForFunction(()=>window.parallax?.observations.image,null,{timeout:20000});
console.log(await p.evaluate(()=>Object.fromEntries(['workspace','observations','science-frame','science'].map(id=>{let e=document.getElementById(id),s=getComputedStyle(e);return[id,{rect:e.getBoundingClientRect().toJSON(),display:s.display,height:s.height,width:s.width,flex:s.flex}]}))));
console.log(await p.locator('.observation-body').evaluate(e=>({rect:e.getBoundingClientRect().toJSON(),display:getComputedStyle(e).display,hidden:e.hidden,children:e.children.length})));
await b.close();
