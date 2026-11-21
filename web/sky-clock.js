const $=id=>document.getElementById(id);
const numerals=['XII','I','II','III','IV','V','VI','VII','VIII','IX','X','XI'];
const marks=Array.from({length:60},(_,i)=>`<line x1="80" x2="80" y1="9" y2="${i%5?13:17}" transform="rotate(${i*6} 80 80)" class="${i%5?'minor':'major'}"/>`).join('');
const hours=numerals.map((n,i)=>`<text x="${80+51*Math.sin(i*Math.PI/6)}" y="${84-51*Math.cos(i*Math.PI/6)}">${n}</text>`).join('');

export const clockMarkup=`
 <div class="sky-clock">
  <button id="sky-clock-dial" type="button" aria-label="Wind time. Drag, scroll, or use the arrow keys." title="Drag to wind time">
   <svg viewBox="0 0 160 160" aria-hidden="true">
    <circle cx="80" cy="80" r="77" class="clock-case"/>
    <circle cx="80" cy="80" r="69" class="clock-face"/>
    ${marks}${hours}
    <line id="sky-hour-hand" class="hour" x1="80" y1="86" x2="80" y2="45"/>
    <line id="sky-minute-hand" class="minute" x1="80" y1="88" x2="80" y2="26"/>
    <circle cx="80" cy="80" r="4" class="clock-pin"/>
   </svg>
  </button>
  <output id="sky-clock-readout"></output>
  <label>Date &amp; time <input id="sky-datetime" type="datetime-local" step="60"></label>
 </div>`;

const localValue=time=>new Date(time.getTime()-time.getTimezoneOffset()*60000).toISOString().slice(0,16);
export function installSkyClock(getTime,setTime){
 const dial=$('sky-clock-dial'),input=$('sky-datetime');
 let drag=null,lastMinute=null;
 function render(time){
  const minute=time.getHours()*60+time.getMinutes();
  $('sky-hour-hand').setAttribute('transform',`rotate(${minute*.5} 80 80)`);
  $('sky-minute-hand').setAttribute('transform',`rotate(${minute%60*6} 80 80)`);
  const formatted=localValue(time);
  if(formatted===lastMinute)return;
  lastMinute=formatted;
  $('sky-clock-readout').value=time.toLocaleTimeString(undefined,{hour:'2-digit',minute:'2-digit'});
  if(document.activeElement!==input)input.value=formatted;
 }
 function wind(minutes){
  const time=new Date(getTime().getTime()+minutes*60000);
  setTime(time);render(time);
 }
 const angle=event=>{
  const r=dial.getBoundingClientRect();
  return Math.atan2(event.clientY-r.top-r.height/2,event.clientX-r.left-r.width/2);
 };
 dial.onpointerdown=event=>{
  if(event.button!==0)return;
  dial.setPointerCapture(event.pointerId);
  drag={angle:angle(event),time:getTime().getTime(),rotation:0};
 };
 dial.onpointermove=event=>{
  if(!drag||!dial.hasPointerCapture(event.pointerId))return;
  const next=angle(event);
  drag.rotation+=Math.atan2(Math.sin(next-drag.angle),Math.cos(next-drag.angle));
  drag.angle=next;
  // One physical turn covers a full day. Draw the hands from actual simulation time.
  const time=new Date(drag.time+drag.rotation*86400000/(Math.PI*2));
  setTime(time);render(time);
 };
 dial.onlostpointercapture=()=>{drag=null;};
 dial.addEventListener('wheel',event=>{event.preventDefault();wind(Math.sign(event.deltaY)*60);},{passive:false});
 dial.onkeydown=event=>{
  if(!['ArrowLeft','ArrowRight','ArrowDown','ArrowUp'].includes(event.key))return;
  event.preventDefault();event.stopPropagation();
  wind((event.shiftKey?180:30)*(['ArrowLeft','ArrowDown'].includes(event.key)?-1:1));
 };
 input.onchange=()=>{
  const time=new Date(input.value);
  if(Number.isFinite(time.getTime())){setTime(time);render(time);}
 };
 render(getTime());
 return render;
}
