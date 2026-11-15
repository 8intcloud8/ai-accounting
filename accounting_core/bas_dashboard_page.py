"""The BAS dashboard page. Data arrives as JSON in place of __DASHBOARD__; every
value is written with textContent, never as HTML."""

PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>BAS dashboard</title>
<style>
:root{--desk:#e9eef0;--win:#fff;--side:#f6f8f9;--ink:#101a24;--muted:#5d6b78;--faint:#8a97a3;--line:#e1e7ec;
--accent:#0f7a63;--accent-ink:#fff;--accent-soft:#e5f4ef;--todo:#b26b00;--todo-soft:#fff4e0;--block:#6b7785;--block-soft:#eef1f4;
--shadow:0 1px 2px #0b16200f,0 20px 50px -24px #0b162040;
--display:"Avenir Next","Segoe UI",system-ui,sans-serif;--body:-apple-system,"Segoe UI",system-ui,sans-serif}
@media(prefers-color-scheme:dark){:root{color-scheme:dark;--desk:#0b1117;--win:#131b23;--side:#0f161d;--ink:#e8eef3;--muted:#9eadb9;--faint:#6e7f8d;--line:#233040;
--accent:#3ccfa6;--accent-ink:#062018;--accent-soft:#103429;--todo:#f2b450;--todo-soft:#33260f;--block:#93a1ae;--block-soft:#1c2631;--shadow:0 1px 2px #0006,0 24px 60px -24px #000a}}
*{box-sizing:border-box}
body{margin:0;background:var(--desk);color:var(--ink);font:14px/1.5 var(--body);padding:24px max(16px,env(safe-area-inset-right,0px)) 48px max(16px,env(safe-area-inset-left,0px))}
main{max-width:860px;margin:0 auto;background:var(--win);border:1px solid var(--line);border-radius:16px;box-shadow:var(--shadow);padding:26px 28px;display:grid;gap:22px}
header{display:grid;gap:4px}
.eyebrow{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;color:var(--muted);font-size:13px}
h1{font:800 26px/1.15 var(--display);margin:0;letter-spacing:-.02em;text-wrap:balance}
.meta{color:var(--muted)}
.live{display:inline-flex;align-items:center;gap:7px;font-weight:600}
.live i{width:8px;height:8px;border-radius:50%;background:var(--faint);display:block}
.live.on i{background:var(--accent);box-shadow:0 0 0 4px var(--accent-soft)}
.bar{height:8px;background:var(--block-soft);border-radius:99px;overflow:hidden}
.bar i{display:block;height:100%;background:var(--accent);transition:width .4s}
.progress{display:grid;gap:8px}.progress small{color:var(--muted)}
.kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}
.kpi{border:1px solid var(--line);border-radius:12px;padding:12px 14px;display:grid;gap:2px}
.kpi strong{font:800 22px/1.1 var(--display);font-variant-numeric:tabular-nums}
.kpi span{color:var(--muted);font-size:12.5px}
.kpi.warn strong{color:var(--todo)}
.steps{border:1px solid var(--line);border-radius:14px;overflow:hidden}
.step{display:grid;grid-template-columns:30px minmax(0,1fr) auto;gap:14px;align-items:center;padding:13px 16px;border-top:1px solid var(--line)}
.step:first-child{border-top:0}
.n{width:30px;height:30px;border-radius:50%;display:grid;place-items:center;font:700 13px var(--display)}
.step h2{margin:0;font:700 14.5px var(--display)}
.step p{margin:1px 0 0;color:var(--muted);font-size:13px;overflow-wrap:anywhere}
.done .n,.ready .n{background:var(--accent);color:var(--accent-ink)}
.todo .n{background:var(--todo-soft);color:var(--todo)}
.blocked .n{background:var(--block-soft);color:var(--block)}
.step.next{background:color-mix(in srgb,var(--todo-soft) 55%,transparent)}
.act{display:flex;gap:8px;align-items:center;flex-wrap:wrap;justify-content:flex-end}
.chip{font:600 12px var(--body);padding:3px 10px;border-radius:99px;white-space:nowrap}
.chip.done,.chip.ready{background:var(--accent-soft);color:var(--accent)}
.chip.todo{background:var(--todo-soft);color:var(--todo)}
.chip.blocked{background:var(--block-soft);color:var(--block)}
button{font:600 13px var(--body);border-radius:9px;padding:7px 13px;cursor:pointer;border:1px solid var(--line);background:var(--win);color:var(--ink)}
button:hover{background:var(--side)}
button.primary{background:var(--accent);color:var(--accent-ink);border-color:transparent}
button:focus-visible{outline:3px solid color-mix(in srgb,var(--accent) 55%,transparent);outline-offset:2px}
.labels{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}
.label{background:var(--side);border-radius:12px;padding:12px 14px}
.label b{display:block;font:700 12px var(--body);color:var(--muted);letter-spacing:.04em}
.label strong{font:800 20px var(--display);font-variant-numeric:tabular-nums}
.label span{display:block;color:var(--muted);font-size:12px}
h3{margin:0 0 8px;font:700 13px var(--body);letter-spacing:.06em;text-transform:uppercase;color:var(--faint)}
.how{display:flex;justify-content:space-between;gap:12px;align-items:center;flex-wrap:wrap;background:var(--side);border-radius:12px;padding:12px 14px}
.how p{margin:0;color:var(--muted);max-width:60ch}
#toast{position:fixed;left:50%;bottom:24px;transform:translateX(-50%);background:var(--ink);color:var(--win);padding:9px 16px;border-radius:10px;font-weight:600;box-shadow:var(--shadow)}
#manual{width:100%;font:13px ui-monospace,Menlo,monospace;padding:8px;border-radius:8px;border:1px solid var(--line);background:var(--win);color:var(--ink)}
@media(max-width:640px){.kpis,.labels{grid-template-columns:repeat(2,minmax(0,1fr))}.step{grid-template-columns:30px minmax(0,1fr)}.act{grid-column:2;justify-content:flex-start}main{padding:18px 14px}}
</style></head><body>
<main>
  <header>
    <div class="eyebrow"><span id="business"></span><span class="live" id="live"><i></i><span id="liveText"></span></span></div>
    <h1 id="title"></h1>
    <div class="meta" id="meta"></div>
  </header>
  <div class="progress"><div class="bar" aria-hidden="true"><i id="bar"></i></div><small id="progress"></small></div>
  <div class="kpis" id="kpis"></div>
  <div class="steps" id="steps"></div>
  <section><h3>BAS figures so far</h3><div class="labels" id="labels"></div></section>
  <div class="how"><p>Buttons copy a ready message. Paste it into your Codex chat; this page updates as Codex works.</p><button class="primary" id="continue" type="button">Copy “continue my BAS”</button></div>
  <input id="manual" hidden readonly aria-label="Message to copy">
</main>
<div id="toast" role="status" hidden></div>
<script>
const boot=__DASHBOARD__;const $=id=>document.getElementById(id);
const live=location.protocol.startsWith('http')&&boot.token;
const month=d=>new Date(d+'T00:00:00').toLocaleDateString('en-AU',{day:'numeric',month:'long',year:'numeric'});
const money=n=>(n<0?'-$':'$')+Math.abs(n).toLocaleString('en-AU');
function node(tag,cls,text){const e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e}
let toastTimer;
async function copy(text){
  try{await navigator.clipboard.writeText(text);toast('Copied. Paste it into Codex.')}
  catch{const m=$('manual');m.hidden=false;m.value=text;m.select();toast('Select the text below and copy it.')}
}
function toast(text){const t=$('toast');t.textContent=text;t.hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>t.hidden=true,2600)}
function draw(d){
  $('business').textContent=d.business;
  $('title').textContent='BAS · '+month(d.start)+' – '+month(d.end);
  $('meta').textContent=[d.due?'Due '+month(d.due):'',d.basis&&d.basis!=='unknown'?d.basis[0].toUpperCase()+d.basis.slice(1)+' basis':''].filter(Boolean).join(' · ');
  $('bar').style.width=(d.done/d.steps.length*100)+'%';
  const next=d.steps.find(s=>s.request);
  $('progress').textContent=d.done+' of '+d.steps.length+' steps done'+(next?' · next: '+next.name.toLowerCase():'');
  const c=d.counts,k=$('kpis');k.replaceChildren();
  [['Bank transactions',c.transactions,false],['To classify',c.unclassified,c.unclassified>0],['Waiting for your approval',c.awaiting_approval,c.awaiting_approval>0],['Invoices to check',c.invoices_to_review,c.invoices_to_review>0]]
    .forEach(([label,value,warn])=>{const b=node('div','kpi'+(warn?' warn':''));b.append(node('strong','',value.toLocaleString('en-AU')),node('span','',label));k.append(b)});
  const box=$('steps');box.replaceChildren();
  d.steps.forEach(s=>{
    const row=node('div','step '+s.state+(s===next?' next':''));
    row.append(node('span','n',s.state==='done'?'✓':s.number));
    const mid=node('div');mid.append(node('h2','',s.name));
    const shown=s.lines.slice(0,3).join(' · ')+(s.lines.length>3?' · and '+(s.lines.length-3)+' more':'');
    if(shown)mid.append(node('p','',shown));row.append(mid);
    const act=node('div','act');
    act.append(node('span','chip '+s.state,{done:'Done',todo:s.needs_user?'Needs you':'To do',blocked:'Blocked',ready:'Ready'}[s.state]));
    if(s.request){const b=node('button',s===next?'primary':'','Copy for Codex');b.type='button';b.onclick=()=>copy(s.request);act.append(b)}
    row.append(act);box.append(row);
  });
  const L=$('labels');L.replaceChildren();
  [['G1','Total sales',d.labels.G1],['1A','GST on sales',d.labels['1A']],['1B','GST on purchases',d.labels['1B']],['9',d.labels['9']<0?'Refund':'To pay',d.labels['9']]]
    .forEach(([code,name,value])=>{const b=node('div','label');b.append(node('b','',code),node('strong','',money(value)),node('span','',name));L.append(b)});
  $('continue').onclick=()=>copy(d.continue_request);
  const at=new Date(d.read_at).toLocaleTimeString('en-AU',{hour:'numeric',minute:'2-digit'});
  $('live').className='live'+(live?' on':'');
  $('liveText').textContent=live?'Live · updated '+at:'Snapshot from '+at+' · reopen to refresh';
}
draw(boot.data);
if(live){setInterval(async()=>{
  try{const r=await fetch('/api/status',{headers:{'X-Dashboard-Token':boot.token}});if(r.ok)draw(await r.json());else throw 0}
  catch{$('live').className='live';$('liveText').textContent='Not updating · ask Codex to open the dashboard again'}
},boot.refresh*1000)}
</script></body></html>
"""
