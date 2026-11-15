import assert from 'node:assert/strict';
import {planetTerrain,environments} from '../web/planet-terrain.js';
for(const body of Object.keys(environments)){
 const a=planetTerrain(body,23,-40),b=planetTerrain(body,23,-40);
 assert.equal(a.heights_m.length,a.n*a.n);assert(a.heights_m.every(Number.isFinite));assert.deepEqual(a.heights_m,b.heights_m);
 assert.match(a.source,/not measured/);
 if(a.gas)assert(a.heights_m.every(v=>v===0));else assert(Math.max(...a.heights_m)>Math.min(...a.heights_m));
}
console.log('PASS: repeatable finite terrain for solid worlds; gas giants remain atmospheric simulations.');
