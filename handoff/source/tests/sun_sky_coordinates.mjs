import assert from 'node:assert/strict';
import {icrsDirection,skyCoordinates} from '../web/sun-sky.js';
const close=(a,b)=>assert.ok(Math.abs(a-b)<1e-8,a+' vs '+b);
const equinox=icrsDirection(0,0);
close(equinox.x,1);close(equinox.y,0);close(equinox.z,0);
const pole=icrsDirection(270,66.560708889);
close(pole.x,0);close(pole.y,1);close(pole.z,0);
for(const [ra,dec] of [[359.98,82.5],[133.79512917,-7.24514722],[90,-89.1],[248.16761083,66.75497942]]){
 const result=skyCoordinates(icrsDirection(ra,dec));close(result.ra,ra);close(result.dec,dec);
}
console.log('PASS: ICRS coordinates round-trip through the Sun view axes and reference directions.');
