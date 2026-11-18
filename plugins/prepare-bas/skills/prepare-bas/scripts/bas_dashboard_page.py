"""The BAS dashboard page. Data arrives as JSON in place of __DASHBOARD__; every
value is written with textContent, never as HTML. Saved as a file it reloads itself,
so an open page follows the books as Codex works."""

PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>BAS dashboard</title>
<style>
:root{--desk:#eef1f3;--win:#fff;--side:#f5f7f8;--ink:#101a24;--muted:#5d6b78;--faint:#8a97a3;--line:#e3e8ec;
--accent:#0f7a63;--accent-ink:#fff;--accent-soft:#e5f4ef;--todo:#b26b00;--todo-soft:#fff4e0;--late:#b42318;--late-soft:#fdecea;
--block:#6b7785;--block-soft:#e9edf0;--shadow:0 1px 2px #0b16200f,0 18px 44px -24px #0b162040;
--display:"Avenir Next","Segoe UI",system-ui,sans-serif;--body:-apple-system,"Segoe UI",system-ui,sans-serif}
@media(prefers-color-scheme:dark){:root{color-scheme:dark;--desk:#0b1117;--win:#131b23;--side:#0f161d;--ink:#e8eef3;--muted:#9eadb9;--faint:#6e7f8d;--line:#233040;
--accent:#3ccfa6;--accent-ink:#062018;--accent-soft:#103429;--todo:#f2b450;--todo-soft:#33260f;--late:#ff8a80;--late-soft:#3a1714;--block:#93a1ae;--block-soft:#1c2631;--shadow:0 1px 2px #0006,0 24px 60px -24px #000a}}
*{box-sizing:border-box}
body{margin:0;background:var(--desk);color:var(--ink);font:14.5px/1.5 var(--body);padding:28px 16px 48px}
main{max-width:760px;margin:0 auto;display:grid;gap:14px}
.card{background:var(--win);border:1px solid var(--line);border-radius:16px;box-shadow:var(--shadow);padding:18px 20px}
.row{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}
.eyebrow{font:700 11px var(--body);letter-spacing:.08em;text-transform:uppercase;color:var(--faint)}
header.card{display:grid;gap:4px}
h1{margin:0;font:800 26px/1.15 var(--display);letter-spacing:-.02em}
.chip{font:600 12.5px var(--body);padding:3px 10px;border-radius:99px;background:var(--block-soft);color:var(--block)}
.chip.warn{background:var(--todo-soft);color:var(--todo)}.chip.late{background:var(--late-soft);color:var(--late)}
.note{color:var(--faint);font-size:12.5px}
.live{display:inline-flex;align-items:center;gap:7px;color:var(--faint);font-size:12.5px}
.live i{width:8px;height:8px;border-radius:50%;background:var(--accent);box-shadow:0 0 0 4px var(--accent-soft)}
#next{display:grid;gap:8px;background:linear-gradient(160deg,var(--accent-soft),var(--win) 65%);border-color:color-mix(in srgb,var(--accent) 35%,var(--line))}
#next .eyebrow{color:var(--accent)}
#next.you{background:linear-gradient(160deg,var(--todo-soft),var(--win) 65%);border-color:color-mix(in srgb,var(--todo) 35%,var(--line))}
#next.you .eyebrow{color:var(--todo)}
#next h2{margin:0;font:800 21px/1.25 var(--display);letter-spacing:-.01em}
#next p{margin:0;color:var(--muted)}
.how{color:var(--faint);font-size:12.5px}
button{font:600 13.5px var(--body);border-radius:10px;padding:9px 16px;cursor:pointer;border:1px solid var(--line);background:var(--win);color:var(--ink)}
button:hover{background:var(--side)}
button.primary{background:var(--accent);color:var(--accent-ink);border-color:transparent}
button:focus-visible,a:focus-visible{outline:3px solid color-mix(in srgb,var(--accent) 55%,transparent);outline-offset:2px}
.pair{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.hero strong{display:block;font:800 36px/1.05 var(--display);letter-spacing:-.03em;font-variant-numeric:tabular-nums;margin:6px 0 2px}
.labels{display:grid;grid-template-columns:repeat(2,1fr);gap:8px;border-top:1px dashed var(--line);margin-top:12px;padding-top:10px}
.labels b{display:block;font:700 10.5px var(--body);color:var(--faint);letter-spacing:.05em}
.labels strong{font:700 15px var(--display);font-variant-numeric:tabular-nums}
.big{font:800 36px/1.05 var(--display);letter-spacing:-.03em;margin:6px 0 2px;font-variant-numeric:tabular-nums}
.stack{display:flex;height:12px;border-radius:99px;overflow:hidden;background:var(--block-soft);margin:12px 0 10px}
.stack i{display:block;height:100%}
.k1{background:var(--accent)}.k2{background:var(--todo)}.k3{background:var(--block)}
.legend{display:grid;gap:4px;font-size:13px;color:var(--muted)}
.legend span{display:flex;align-items:center;gap:8px}.legend b{color:var(--ink);min-width:3ch;text-align:right;font-variant-numeric:tabular-nums}
.legend em{width:10px;height:10px;border-radius:3px}
.how2{margin:4px 0 0;color:var(--muted);max-width:52ch}
a.open{display:inline-block;margin-top:12px;color:var(--accent);font-weight:700;text-decoration:none}
a.open:hover{text-decoration:underline}
ul.todo{list-style:none;margin:10px 0 0;padding:0;display:grid}
ul.todo li{padding:9px 0;border-top:1px solid var(--line);display:flex;gap:10px;align-items:baseline}
ul.todo li:first-child{border-top:0}
ul.todo li::before{content:"";width:7px;height:7px;border-radius:50%;background:var(--todo);flex:none;transform:translateY(-1px)}
#toast{position:fixed;left:50%;bottom:24px;transform:translateX(-50%);background:var(--ink);color:var(--win);padding:9px 16px;border-radius:10px;font-weight:600;box-shadow:var(--shadow)}
#manual{width:100%;font:13px ui-monospace,Menlo,monospace;padding:8px;border-radius:8px;border:1px solid var(--line);background:var(--win);color:var(--ink)}
@media(max-width:640px){.pair{grid-template-columns:1fr}h1{font-size:22px}.hero strong,.big{font-size:30px}}
</style></head><body>
<main>
  <header class="card">
    <div class="row"><span class="eyebrow" id="business"></span><span class="live"><i></i><span id="liveText"></span></span></div>
    <h1 id="title"></h1>
    <div class="row"><span class="chip" id="due"></span><span class="note" id="basis"></span></div>
  </header>
  <section class="card" id="next" aria-live="polite">
    <span class="eyebrow" id="who">Next</span><h2 id="question"></h2><p id="detail"></p>
    <div class="row"><button class="primary" id="go" type="button">Copy for Codex</button><span class="how">Paste it into your Codex chat.</span></div>
  </section>
  <div class="pair">
    <section class="card hero"><span class="eyebrow" id="moneyLabel">Amount to pay</span><strong id="net"></strong><span class="note" id="netNote"></span>
      <div class="labels" id="labels"></div><div class="labels" id="basTotals"></div><span class="note">BAS total before existing ATO credits or payments</span></section>
    <section class="card"><span class="eyebrow">Bank transactions</span><div class="big" id="txTotal"></div>
      <div class="stack" id="stack" aria-hidden="true"></div><div class="legend" id="legend"></div><div class="legend" id="purposes" style="margin-top:12px"></div>
      </section>
  </div>
  <section class="card check" id="check"><div class="row"><div><span class="eyebrow">Check any number</span>
    <p class="how2">Every figure here is in <b>BAS workbook.xlsx</b>, next to this page: the BAS sheet shows how each is worked out, and the GST items sheet lists every line behind it.</p></div>
    <a class="open" href="BAS workbook.xlsx">Open BAS workbook.xlsx →</a></div></section>
  <section class="card"><div class="row"><span class="eyebrow">Still to do</span><span class="note" id="todoCount"></span></div><ul class="todo" id="todo"></ul></section>
  <input id="manual" hidden readonly aria-label="Message to copy">
</main>
<div id="toast" role="status" hidden></div>
<script>
const boot=__DASHBOARD__;const $=id=>document.getElementById(id);
const live=location.protocol.startsWith('http')&&boot.token;
const month=d=>new Date(d+'T00:00:00').toLocaleDateString('en-AU',{day:'numeric',month:'short',year:'numeric'});
const money=n=>(n<0?'-$':'$')+Math.abs(n).toLocaleString('en-AU');
const days=d=>Math.round((new Date(d+'T00:00:00')-new Date(new Date().toDateString()))/864e5);
function node(tag,cls,text){const e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e}
let toastTimer;
async function copy(text){
  try{await navigator.clipboard.writeText(text);toast('Copied. Paste it into Codex.')}
  catch{const m=$('manual');m.hidden=false;m.value=text;m.select();toast('Select the text below and copy it.')}
}
function toast(text){const t=$('toast');t.textContent=text;t.hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>t.hidden=true,2600)}
const ask=q=>q.replace(/^Shall I /,'').replace(/ now\?$|\?$/,'').replace(/^./,c=>c.toUpperCase());
function draw(d){
  $('business').textContent=d.business;
  $('title').textContent=`BAS ${month(d.start)} – ${month(d.end)}`;
  const left=d.due?days(d.due):null,due=$('due');
  due.className='chip'+(left===null?'':left<0?' late':left<=14?' warn':'');
  due.textContent=left===null?'':left<0?`Overdue ${-left} day${left===-1?'':'s'} · due ${month(d.due)}`:left===0?'Due today':`Due in ${left} day${left===1?'':'s'} · ${month(d.due)}`;
  $('basis').textContent=d.basis&&d.basis!=='unknown'?d.basis[0].toUpperCase()+d.basis.slice(1)+' basis':'';
  const you=d.next.who==='user';$('next').className='card'+(you?' you':'');
  $('who').textContent=you?'Needs you':'Next';$('question').textContent=ask(d.next.question);$('detail').textContent=d.next.detail;
  $('go').onclick=()=>copy(d.next.request);
  const net=(d.labels['1A']??0)-(d.labels['1B']??0);$('moneyLabel').textContent=net<0?'GST refund':'GST to pay';$('net').textContent=money(Math.abs(net));
  $('netNote').textContent=d.labels_final?'Ready for the BAS':'Estimate so far';
  $('labels').replaceChildren(...[['G1 Sales',d.labels.G1],['1A GST on sales',d.labels['1A']],['1B GST credits',d.labels['1B']],['W2 Tax withheld',d.labels.W2??0]].map(([k,v])=>{const f=node('div');f.append(node('b','',k),node('strong','',money(v??0)));return f}));
  $('basTotals').replaceChildren(...[['PAYG withheld (4)',d.payg_recorded?d.labels['4']:null],[d.payg_recorded?(d.labels['9']<0?'Draft BAS refund':'Draft BAS payable'):'GST subtotal',d.payg_recorded?Math.abs(d.labels['9']):net]].map(([k,v])=>{const f=node('div');f.append(node('b','',k),node('strong','',v===null?'Not recorded':money(v)));return f}));
  const t=d.transactions;$('txTotal').textContent=t.total.toLocaleString('en-AU');
  $('stack').replaceChildren(...[['k1',t.classified],['k2',t.proposed],['k3',t.uncategorised]].map(([k,v])=>{const i=node('i',k);i.style.flexGrow=v;return i}));
  $('legend').replaceChildren(...[['k1',t.classified,'categorised'],['k2',t.proposed,'waiting for your OK'],['k3',t.uncategorised,'still need a category']].map(([k,v,label])=>{const s=node('span');s.append(node('em',k),node('b','',v.toLocaleString('en-AU')),label);return s}));
  $('purposes').replaceChildren(...Object.entries(d.purpose_counts||{}).map(([label,v])=>{const s=node('span');s.append(node('b','',v.toLocaleString('en-AU')),label);return s}));
  $('check').hidden=live;
  const todo=[...new Set(d.todo)];$('todoCount').textContent=todo.length?`${todo.length} item${todo.length===1?'':'s'}`:'';
  $('todo').replaceChildren(...(todo.length?todo:['Nothing left. Ready for the BAS draft.']).map(x=>node('li','',x)));
  const at=new Date(d.read_at).toLocaleTimeString('en-AU',{hour:'numeric',minute:'2-digit'});
  $('liveText').textContent=(live?'Live':'This page updates by itself')+' · '+at;
}
draw(boot.data);
if(live){setInterval(async()=>{
  try{const r=await fetch('/api/status',{headers:{'X-Dashboard-Token':boot.token}});if(r.ok)draw(await r.json());else throw 0}
  catch{$('liveText').textContent='Not updating · ask Codex to open the dashboard again'}
},boot.refresh*1000)}
else{setTimeout(()=>location.reload(),boot.refresh*1000)}  // Codex rewrites this file after every change.
</script></body></html>
"""
