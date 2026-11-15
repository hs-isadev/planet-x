export function installGuide(getContext){
 const button=document.createElement('button');button.id='guide-toggle';button.textContent='Ask the AI guide';button.setAttribute('aria-expanded','false');button.setAttribute('aria-controls','guide-panel');document.body.append(button);
 const panel=document.createElement('aside');panel.id='guide-panel';panel.hidden=true;panel.setAttribute('aria-label','Parallax AI guide');
 panel.innerHTML='<div class="guide-heading"><div><small>GROQ / APP GUIDE</small><h2>Explore with a guide</h2></div><button id="guide-close" aria-label="Close guide">×</button></div><p class="micro">Questions and the current target, exposure and review status are sent to Groq. Attach a Laya report to share its summary and selected comparisons. Images stay local.</p><p id="guide-status" class="micro" role="status"></p><details id="guide-setup" hidden><summary>Enable the guide locally</summary><p>Set GROQ_API_KEY in the server environment, then restart python start.py. Optional: set GROQ_MODEL. Keep the key out of this chat and your source files.</p><a href="https://console.groq.com/keys" target="_blank" rel="noreferrer">Create a Groq key ↗</a></details><div id="guide-log" role="log" aria-live="polite"></div><div class="guide-suggestions"><button type="button">What can I do in this view?</button><button type="button">Why is Laya not reviewing?</button><button type="button">How do I compare the same wavelength?</button></div><form id="guide-form"><label class="check" id="guide-report-control" hidden><input id="guide-include-report" type="checkbox">Attach Laya analysis report</label><label for="guide-question">Your question</label><textarea id="guide-question" rows="3" maxlength="4000" placeholder="Ask about this target or a feature…" required></textarea><div class="guide-actions"><button type="button" id="guide-clear">Clear chat</button><button type="submit" id="guide-send" class="primary">Send</button></div></form>';
 document.body.append(panel);const $=id=>document.getElementById(id);let history=[],controller,generation=0,selectedReview;
 function updateReportControl(){
  const context=getContext();
  $('guide-report-control').hidden=!(selectedReview||context.review_id&&context.review_available);
  if($('guide-report-control').hidden)$('guide-include-report').checked=false;
 }
 window.addEventListener('explain-laya-report',event=>{
  selectedReview=event.detail.reviewId;
  show(true);
  $('guide-include-report').checked=true;
  $('guide-question').value='Explain this Laya analysis report. What do the possible shifts, brightness changes and artifacts suggest, and what should I check next?';
 });
 function show(open){panel.hidden=!open;button.setAttribute('aria-expanded',String(open));if(open){updateReportControl();$('guide-question').focus();}else button.focus();}
 button.onclick=()=>show(panel.hidden);$('guide-close').onclick=()=>show(false);
 panel.addEventListener('keydown',e=>{if(e.key==='Escape'){e.stopPropagation();show(false);}});
 function append(role,text){const row=document.createElement('p');row.className='guide-message '+role;const label=document.createElement('strong');label.textContent=role==='user'?'You':'Guide';const body=document.createElement('span');body.textContent=text;row.append(label,body);$('guide-log').append(row);row.scrollIntoView({block:'nearest'});}
 async function check(){try{const r=await fetch('/api/guide/status');if(!r.ok)throw Error();const s=await r.json();$('guide-status').textContent=s.configured?'Ready · '+s.model:'Groq is not configured yet. The rest of the app works normally.';$('guide-setup').hidden=s.configured;if(!s.configured)$('guide-setup').open=true;}catch{$('guide-status').textContent='Guide service unavailable. Restart the server after updating.';}}
 $('guide-clear').onclick=()=>{generation++;controller?.abort();history=[];selectedReview=null;$('guide-include-report').checked=false;updateReportControl();$('guide-log').replaceChildren();$('guide-question').value='';$('guide-send').disabled=false;check();};
 $('guide-form').onsubmit=async event=>{
  event.preventDefault();if(controller)return;const question=$('guide-question').value.trim();if(!question)return;
  const token=generation;append('user',question);$('guide-question').value='';$('guide-send').disabled=true;$('guide-status').textContent='Asking Groq…';controller=new AbortController();const timer=setTimeout(()=>controller?.abort(),45000);
  const messages=[...history.slice(-10),{role:'user',content:question}];
  const {review_available,...context}=getContext();
  const include=$('guide-include-report').checked;
  if(include&&selectedReview)context.review_id=selectedReview;
  context.include_review_report=include;
  try{const r=await fetch('/api/guide/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({messages,context}),signal:controller.signal});const result=await r.json();if(!r.ok)throw Error(result.detail||'Guide request failed.');if(token!==generation)return;history=[...messages,{role:'assistant',content:result.reply}];append('assistant',result.reply);$('guide-status').textContent='Groq · '+result.model;}
  catch(e){if(token!==generation)return;$('guide-status').textContent=e.name==='AbortError'?'The guide request timed out. You can retry.':e.message;$('guide-question').value=question;}
  finally{clearTimeout(timer);controller=null;if(token===generation)$('guide-send').disabled=false;}
 };
 panel.querySelectorAll('.guide-suggestions button').forEach(b=>b.onclick=()=>{$('guide-question').value=b.textContent;$('guide-question').focus();});check();
}
