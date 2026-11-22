const $=id=>document.getElementById(id);
export const clockMarkup=`
 <div class="sky-clock">
  <output id="sky-clock-readout" aria-label="Simulation time"></output>
  <button id="sky-clock-dial" type="button" aria-label="Wind time. Drag, scroll, or use the arrow keys." title="Drag to wind time">
   <span class="clock-orbit" aria-hidden="true"></span>
   <span class="clock-orbit-mark clock-orbit-top" aria-hidden="true">00</span>
   <span class="clock-orbit-mark clock-orbit-right" aria-hidden="true">06</span>
   <span class="clock-orbit-mark clock-orbit-bottom" aria-hidden="true">12</span>
   <span class="clock-orbit-mark clock-orbit-left" aria-hidden="true">18</span>
   <span id="sky-clock-orbit-marker" aria-hidden="true"></span>
   <span class="clock-inner-dial" aria-hidden="true">
    <img src="/assets/sky/clock-face.webp" alt="" width="548" height="548" draggable="false">
    <span id="sky-hour-hand" class="clock-hand"></span>
    <span id="sky-minute-hand" class="clock-hand"></span>
    <span id="sky-second-hand" class="clock-hand"></span>
   </span>
  </button>
  <small class="clock-winding-hint">Drag the dial to wind time</small>
  <label>Date &amp; time <input id="sky-datetime" type="datetime-local" step="60"></label>
 </div>`;

const localValue=time=>new Date(time.getTime()-time.getTimezoneOffset()*60000).toISOString().slice(0,16);
export function installSkyClock(getTime,setTime){
 const dial=$('sky-clock-dial'),input=$('sky-datetime');
 const readout=$('sky-clock-readout'),orbitMarker=$('sky-clock-orbit-marker');
 const hourHand=$('sky-hour-hand'),minuteHand=$('sky-minute-hand'),secondHand=$('sky-second-hand');
 const readTime=new Intl.DateTimeFormat(undefined,{hour:'2-digit',minute:'2-digit',hourCycle:'h23'});
 let drag=null,lastMinute=null,shownTime=null;
 function render(time, dt=1/60){
  if(shownTime===null || drag || Math.abs(time-shownTime)>86400000)shownTime=+time;
  else shownTime+=(+time-shownTime)*(1-Math.exp(-dt*18));
  const displayed=new Date(shownTime);
  const seconds=displayed.getSeconds()+displayed.getMilliseconds()/1000;
  const minute=displayed.getHours()*60+displayed.getMinutes()+seconds/60;
  hourHand.style.rotate=minute*.5+'deg';
  minuteHand.style.rotate=minute%60*6+'deg';
  secondHand.style.rotate=seconds*6+'deg';
  orbitMarker.style.rotate=minute*.25+'deg';
  const formatted=localValue(time);
  if(formatted===lastMinute)return;
  lastMinute=formatted;
  readout.value=readTime.format(time);
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
  shownTime=null;
  if(Number.isFinite(time.getTime())){setTime(time);render(time);}
 };
 render(getTime());
 return render;
}
