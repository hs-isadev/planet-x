export function installAmbientAudio(toast) {
  const preference='parallax-ambient-audio';
  let context, volume, enabled=false, remembered=false, starting=false;
  try { remembered=localStorage.getItem(preference)==='on'; } catch {}
  const buttons=()=>document.querySelectorAll('[data-ambient-toggle]');
  function render(){
    for(const button of buttons()){
      button.textContent=starting?'Starting…':enabled?'Mute sound':'Play sound';
      button.setAttribute('aria-label','Ambient sound');
      button.setAttribute('aria-pressed',String(enabled));
      button.title=enabled?'Mute background sound':'Play background sound';
      button.disabled=starting;
    }
  }
  function create(){
    const Audio=window.AudioContext || window.webkitAudioContext;
    if(!Audio)throw Error('Ambient audio is unavailable in this browser.');
    context=new Audio();
    volume=context.createGain();volume.gain.value=0;
    const sampleRate=16000;
    const length=16*sampleRate;
    const overlap=sampleRate;
    const buffer=context.createBuffer(2,length,sampleRate);
    const channels=[buffer.getChannelData(0),buffer.getChannelData(1)];
    const slow=[0,0], fast=[0,0];
    const lowCut=1-Math.exp(-2*Math.PI*240/sampleRate);
    const highCut=1-Math.exp(-2*Math.PI*880/sampleRate);
    // Filter stereo noise into a soft airflow texture and crossfade the loop seam.
    for(let i=0;i<length+overlap;i++){
      const shared=Math.random()*2-1;
      const phase=2*Math.PI*i/length;
      const swell=.78-.16*Math.cos(phase)-.09*Math.sin(3*phase);
      for(let channel=0;channel<channels.length;channel++){
        const noise=.72*shared+.28*(Math.random()*2-1);
        slow[channel]+=lowCut*(noise-slow[channel]);
        fast[channel]+=highCut*(noise-fast[channel]);
        const sample=(fast[channel]-slow[channel])*swell;
        const data=channels[channel];
        if(i<length)data[i]=sample;
        else {
          const first=i-length;
          const blend=.5-.5*Math.cos(Math.PI*first/(overlap-1));
          data[first]=sample*(1-blend)+data[first]*blend;
        }
      }
    }
    const source=context.createBufferSource();
    source.buffer=buffer;
    source.loop=true;
    source.connect(volume).connect(context.destination);
    source.start();
  }
  async function enable(){
    if(starting)return;
    starting=true;
    render();
    try{
      if(!context)create();
      await context.resume();
      enabled=true;remembered=false;
      try{localStorage.setItem(preference,'on');}catch{}
    }catch(error){
      remembered=false;
      toast(error.message);
    }finally{
      starting=false;
      update();
    }
  }
  function update(){
    if(volume){
      volume.gain.cancelScheduledValues(context.currentTime);
      const audible=enabled&&!document.hidden;
      volume.gain.setTargetAtTime(audible ? .075 : 0,context.currentTime,audible ? .5 : .17);
    }
    render();
  }
  document.addEventListener('click',event=>{
    const button=event.target.closest('[data-ambient-toggle]');
    if(button){
      if(enabled){
        enabled=false;remembered=false;
        try{localStorage.setItem(preference,'off');}catch{}
        update();
      }else enable();
    }else if(event.isTrusted&&remembered&&!enabled)enable();
  });
  document.addEventListener('visibilitychange',update);
  render();
}
