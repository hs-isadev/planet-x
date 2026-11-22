export function installAmbientAudio(toast) {
  const preference='parallax-ambient-audio';
  let context, volume, enabled=false, remembered=false, starting=false;
  try { remembered=localStorage.getItem(preference)==='on'; } catch {}
  const buttons=()=>document.querySelectorAll('[data-ambient-toggle]');
  function render(){
    for(const button of buttons()){
      button.textContent=starting?'Starting…':enabled?'Mute hum':'Play hum';
      button.setAttribute('aria-label','Ambient sound');
      button.setAttribute('aria-pressed',String(enabled));
      button.title=enabled?'Mute background hum':'Play background hum';
      button.disabled=starting;
    }
  }
  function create(){
    const Audio=window.AudioContext || window.webkitAudioContext;
    if(!Audio)throw Error('Ambient audio is unavailable in this browser.');
    context=new Audio();
    volume=context.createGain();volume.gain.value=0;
    const motion=context.createGain();motion.gain.value=.88;
    volume.connect(motion).connect(context.destination);
    // A soft fundamental and consonant upper tones that laptop speakers can reproduce.
    for(const [frequency,level] of [[110,.19],[164.81,.27],[220,.31],[220.37,.10],[329.63,.10],[440,.03]]){
      const oscillator=context.createOscillator();
      oscillator.frequency.value=frequency;
      const mix=context.createGain();mix.gain.value=level;
      oscillator.connect(mix).connect(volume);oscillator.start();
    }
    const sway=context.createOscillator(),depth=context.createGain();
    sway.frequency.value=.09;depth.gain.value=.095;
    sway.connect(depth).connect(motion.gain);
    sway.start();
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
      volume.gain.setTargetAtTime(audible ? .145 : 0,context.currentTime,audible ? .5 : .17);
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
