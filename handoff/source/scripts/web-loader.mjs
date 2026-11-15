// Resolve the browser import map for Node-only geometry/behavior checks.
import {pathToFileURL} from 'node:url';
import path from 'node:path';
export function resolve(specifier,context,nextResolve){
 if(specifier==='three')return {url:pathToFileURL(path.resolve('web/vendor/three.module.js')).href,shortCircuit:true};
 if(specifier.startsWith('three/addons/'))return {url:pathToFileURL(path.resolve('web/vendor/addons',specifier.slice(13))).href,shortCircuit:true};
 return nextResolve(specifier,context);
}
