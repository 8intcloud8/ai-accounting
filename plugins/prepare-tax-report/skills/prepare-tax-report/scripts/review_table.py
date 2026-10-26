"""Local, read-only CSV table with source links and saved correction requests."""

import csv
import hashlib
import json
import mimetypes
import re
import secrets
from datetime import datetime
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

MAX_BYTES = 12 * 1024 * 1024
MAX_ROWS = 10000
SOURCE_FIELDS = {"source", "source_path", "file", "document_path", "statement"}


def load_table(csv_path, workspace, title=None):
    """Snapshot a bounded workspace CSV; never change the accounting database."""
    workspace = Path(workspace).resolve(strict=True)
    source = Path(csv_path).resolve(strict=True)
    if (
        not source.is_relative_to(workspace / "output")
        or source.suffix.lower() != ".csv"
    ):
        raise ValueError("Choose a review CSV inside this workspace's output folder")
    with source.open("rb") as handle:
        raw = handle.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("Review CSV exceeds 12 MB; export a smaller period")
    reader = csv.DictReader(raw.decode("utf-8-sig").splitlines(keepends=True))
    columns = reader.fieldnames
    if (
        not columns
        or any(not c or len(c) > 200 for c in columns)
        or len(set(columns)) != len(columns)
    ):
        raise ValueError("CSV needs unique, non-empty column names")
    rows = []
    links = {}
    for index, row in enumerate(reader):
        if index >= MAX_ROWS:
            raise ValueError("Review CSV exceeds 10,000 rows; export a smaller period")
        if None in row or any(value is None for value in row.values()):
            raise ValueError("CSV row does not match its header")
        display = {}
        for column, value in row.items():
            shown = value or "Unknown"
            if value and column.endswith("_cents"):
                if (
                    not re.fullmatch(r"-?[0-9]{1,19}", value)
                    or not -(2**63) <= int(value) < 2**63
                ):
                    raise ValueError("Money columns require bounded integer cents")
                shown = f"{Decimal(int(value)) / 100:,.2f}"
            elif value and (
                column.endswith("_date")
                or column in ("date", "period_start", "period_end")
            ):
                try:
                    shown = datetime.strptime(value, "%Y-%m-%d").strftime("%d %b %Y")
                except ValueError:
                    pass
            display[column] = shown
            if column in SOURCE_FIELDS and value:
                candidate = Path(value)
                candidate = (
                    candidate if candidate.is_absolute() else workspace / candidate
                )
                try:
                    target = candidate.resolve(strict=True)
                    if target.is_file() and target.is_relative_to(
                        workspace / "documents"
                    ):
                        links[f"{index}:{column}"] = target
                except OSError:
                    pass
        rows.append({"index": index, "values": row, "display": display})
    return {
        "title": title or source.stem.replace("-", " ").replace("_", " ").title(),
        "csv": str(source),
        "workspace": str(workspace),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "columns": columns,
        "rows": rows,
        "links": links,
    }


def save_request(table, request):
    """Save an evidence-bound request; this is never an approval or ledger write."""
    if not isinstance(request, dict) or request.get("action") not in (
        "check",
        "correct",
    ):
        raise ValueError("Choose check or correct")
    index = request.get("row")
    if type(index) is not int or not 0 <= index < len(table["rows"]):
        raise ValueError("Unknown review row")
    reason = request.get("reason")
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 4000:
        raise ValueError("Explain what should be checked or corrected")
    changes = request.get("changes", {})
    if not isinstance(changes, dict) or any(
        key not in table["columns"] or not isinstance(value, str) or len(value) > 4000
        for key, value in changes.items()
    ):
        raise ValueError("Correction fields must match the original CSV")
    protected = {
        c
        for c in table["columns"]
        if c == "id" or c.endswith("_id") or c in SOURCE_FIELDS
    }
    if protected.intersection(changes):
        raise ValueError("Record identity and source paths cannot be edited")
    if request["action"] == "correct" and not changes:
        raise ValueError("Choose a field and proposed value")
    if request["action"] == "check" and changes:
        raise ValueError("A check request cannot contain corrections")
    current = Path(table["csv"])
    if hashlib.sha256(current.read_bytes()).hexdigest() != table["sha256"]:
        raise ValueError("CSV has changed. Open a fresh review before saving a request")
    stamp = datetime.now().astimezone()
    folder = Path(table["workspace"]) / "output" / stamp.date().isoformat()
    folder.mkdir(parents=True, exist_ok=True)
    if not folder.resolve().is_relative_to(Path(table["workspace"]) / "output"):
        raise ValueError("Review output folder escapes the workspace")
    path = (
        folder
        / f"review-request-{stamp.strftime('%H%M%S')}-{secrets.token_hex(6)}.json"
    )
    payload = {
        "status": "requested_not_applied",
        "created_at": stamp.isoformat(),
        "csv": table["csv"],
        "csv_sha256": table["sha256"],
        "row_index": index,
        "original": table["rows"][index]["values"],
        "action": request["action"],
        "changes": changes,
        "reason": reason.strip(),
    }
    with path.open("x") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")
    path.chmod(0o600)
    return {"saved_request": str(path), "status": "requested_not_applied"}


def create_server(table, port=0):
    """Expose only this snapshot and its allowlisted sources on loopback."""
    token = secrets.token_urlsafe(32)
    public = {k: v for k, v in table.items() if k not in ("links", "workspace")}
    public["links"] = list(table["links"])
    data = (
        json.dumps(public, ensure_ascii=True)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )
    page = HTML.replace("__TABLE_DATA__", data).encode()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass  # Never log URL capabilities or financial records.

        def send(self, status, body, mime="application/json", extra=None):
            if isinstance(body, str):
                body = body.encode()
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; img-src 'self'; form-action 'none'; base-uri 'none'; frame-ancestors 'self'",
            )
            for key, value in (extra or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

        def authorized(self):
            expected = f"127.0.0.1:{self.server.server_port}"
            return self.headers.get("Host") == expected

        def do_GET(self):
            url = urlsplit(self.path)
            args = parse_qs(url.query)
            if not self.authorized() or not secrets.compare_digest(
                args.get("token", [""])[0].encode(), token.encode()
            ):
                self.send(403, '{"error":"Open the review link supplied by Codex"}')
                return
            if url.path == "/":
                self.send(200, page, "text/html; charset=utf-8")
            elif url.path == "/source":
                target = table["links"].get(args.get("id", [""])[0])
                if (
                    not target
                    or not target.exists()
                    or not target.resolve().is_relative_to(
                        Path(table["workspace"]) / "documents"
                    )
                ):
                    self.send(404, '{"error":"Source unavailable"}')
                    return
                mime = (
                    mimetypes.guess_type(target.name)[0] or "application/octet-stream"
                )
                safe = (
                    mime == "application/pdf"
                    or mime.startswith("image/")
                    and mime != "image/svg+xml"
                )
                if target.stat().st_size > 40 * 1024 * 1024:
                    self.send(413, '{"error":"Source exceeds viewer size limit"}')
                    return
                self.send(
                    200,
                    target.read_bytes(),
                    mime,
                    {"Content-Disposition": "inline" if safe else "attachment"},
                )
            else:
                self.send(404, '{"error":"Not found"}')

        def do_POST(self):
            origin = f"http://127.0.0.1:{self.server.server_port}"
            if (
                not self.authorized()
                or self.headers.get("Origin") != origin
                or not secrets.compare_digest(
                    self.headers.get("X-Review-Token", "").encode(), token.encode()
                )
            ):
                self.send(403, '{"error":"Request origin rejected"}')
                return
            if self.path != "/requests":
                self.send(404, '{"error":"Not found"}')
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if (
                    not 0 < length <= 32000
                    or self.headers.get("Content-Type") != "application/json"
                ):
                    raise ValueError("Invalid request size or content type")
                result = save_request(table, json.loads(self.rfile.read(length)))
                self.send(201, json.dumps(result))
            except (ValueError, TypeError, OSError) as exc:
                self.send(400, json.dumps({"error": str(exc)}))

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    server.review_url = f"http://127.0.0.1:{server.server_port}/?token={token}"
    return server


def serve(csv_path, workspace, title=None, port=0):
    table = load_table(csv_path, workspace, title)
    server = create_server(table, port)
    print(
        json.dumps(
            {
                "review_url": server.review_url,
                "rows": len(table["rows"]),
                "csv": str(csv_path),
            }
        ),
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


HTML = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Accounting review</title>
<style>
:root{color-scheme:light dark;--bg:#f7f8fa;--panel:#fff;--text:#17212f;--muted:#566174;--line:#d8dfe8;--brand:#175b51;--soft:#e8f5ee;--warn:#fff3d2;--warntext:#714c00;--focus:#276add}*{box-sizing:border-box}body{margin:0;font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:var(--bg);color:var(--text)}header,main{padding:24px;max-width:1600px;margin:auto}header{padding-bottom:16px}.eyebrow{font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--brand);font-weight:650}h1{margin:5px 0;font-size:25px;line-height:1.25;font-weight:650}.subtitle,.hint{color:var(--muted)}.summary{display:flex;gap:10px;flex-wrap:wrap;margin-top:18px}.chip{background:var(--panel);padding:6px 12px;border:1px solid var(--line);border-radius:999px}.chip.warn,.badge.warn{background:var(--warn);color:var(--warntext)}main{padding-top:0}.toolbar{display:flex;align-items:end;gap:12px;flex-wrap:wrap;margin:8px 0 14px}label{display:block;font-weight:600;font-size:12px}input,select,textarea,button{font:inherit;color:inherit}input,select,textarea{border:1px solid var(--line);border-radius:7px;padding:9px 11px;background:var(--panel)}input[type=search]{min-width:260px}button,.source{border:1px solid var(--line);border-radius:6px;padding:7px 10px;background:var(--panel);cursor:pointer;white-space:nowrap}button:hover,.source:hover{background:var(--soft)}button:disabled{opacity:.5;cursor:default}button:focus-visible,input:focus-visible,select:focus-visible,textarea:focus-visible,a:focus-visible{outline:3px solid var(--focus);outline-offset:2px}.primary{background:var(--brand);color:#fff;border-color:var(--brand)}.table-wrap{overflow:auto;border:1px solid var(--line);border-radius:10px;background:var(--panel);max-height:68vh}table{border-collapse:separate;border-spacing:0;width:100%;font-size:13px}th{position:sticky;top:0;background:var(--panel);z-index:1;border-bottom:1px solid var(--line);text-align:left;padding:0}th button{border:0;border-radius:0;text-align:left;width:100%;padding:13px 12px;background:transparent}td{padding:12px;border-bottom:1px solid var(--line);vertical-align:top;max-width:330px;min-width:115px;overflow-wrap:anywhere}tr:last-child td{border-bottom:0}tr:hover td{background:color-mix(in srgb,var(--soft) 35%,var(--panel))}.money{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}.badge{display:inline-block;padding:3px 8px;border-radius:5px;background:var(--soft);white-space:normal}.unknown{color:var(--warntext);font-style:italic}.issue{color:var(--warntext);background:var(--warn);padding:4px 7px;border-radius:4px}.actions{min-width:180px;white-space:nowrap;position:sticky;right:0;background:var(--panel);box-shadow:-1px 0 var(--line)}.issue-cell{min-width:230px;max-width:320px}summary{cursor:pointer;color:var(--warntext)}details[open] summary{margin-bottom:8px}th:last-child{position:sticky;right:0;z-index:2;padding:12px;background:var(--panel)}footer{overflow-wrap:anywhere}.actions button{margin-right:5px}.source{color:var(--brand);text-decoration:none;display:inline-block}footer{margin-top:12px;color:var(--muted);font-size:12px}.status{margin-top:12px;padding:12px;border-radius:7px;background:var(--soft);overflow-wrap:anywhere}.status.error{background:var(--warn);color:var(--warntext)}dialog{width:min(540px,94vw);border:1px solid var(--line);border-radius:12px;background:var(--panel);color:var(--text);padding:24px}dialog::backdrop{background:#0007}dialog h2{margin-top:0;font-size:20px}dialog label{margin:14px 0 5px}dialog input,dialog textarea,dialog select{width:100%}dialog textarea{min-height:100px}.dialog-actions{display:flex;justify-content:end;gap:8px;margin-top:18px}.detail{max-height:130px;overflow:auto;padding:8px;background:var(--bg);border-radius:5px;white-space:pre-wrap}.pagination{display:flex;align-items:center;gap:12px;justify-content:space-between;margin-top:12px}.pagebuttons{display:flex;gap:8px}.hidden{display:none!important}@media(prefers-color-scheme:dark){:root{--bg:#11171d;--panel:#1a222c;--text:#e9edf2;--muted:#a9b5c6;--line:#384555;--brand:#80d4bc;--soft:#203c35;--warn:#3d321b;--warntext:#f1cf85;--focus:#8bb5ff}.primary{background:#24735e;color:#fff;border-color:#24735e}}@media(max-width:600px){header,main{padding:16px}main{padding-top:0}input[type=search]{min-width:0;width:100%}.toolbar label{flex:1}.table-wrap{max-height:65vh}}
</style></head><body>
<header><div class="eyebrow">Accounting · review</div><h1 id="title"></h1><div class="subtitle">Check documents, inspect issues and request corrections.</div><div class="summary"><span class="chip" id="count"></span><span class="chip warn" id="issues"></span><span class="chip" id="requests">0 requests saved this session</span></div></header>
<main><div class="toolbar"><label>Search<input id="search" type="search" placeholder="Supplier, description, invoice…"></label><label>Show<select id="filter" aria-label="Show"><option value="all">All rows</option><option value="issues">Rows with issues</option><option value="requested">Requests saved this session</option></select></label><label>Columns<select id="columns" aria-label="Columns"><option value="summary">Review columns</option><option value="all">All source columns</option></select></label></div>
<div class="table-wrap"><table aria-label="Accounting review records"><thead id="head"></thead><tbody id="body"></tbody></table></div><div class="pagination"><span id="visible" aria-live="polite"></span><div class="pagebuttons"><button id="prev">Previous</button><button id="next">Next</button></div></div><div id="notice" role="status" aria-live="polite" class="status hidden"></div><footer>Amounts are displayed in the row’s currency. Unknown currency stays unknown. Saving a request does not change accounting records.<br>CSV export: <span id="filename"></span></footer></main>
<dialog id="dialog" aria-labelledby="dialog-title"><form id="form"><h2 id="dialog-title"></h2><div id="record" class="detail"></div><div id="correction"><label for="field">Field to correct</label><select id="field"></select><label for="current" id="current-label">Current value</label><input id="current" readonly><label for="proposed" id="proposed-label">Proposed value</label><input id="proposed"></div><label for="reason">What should Codex check?</label><textarea id="reason" required maxlength="4000" placeholder="Describe the issue or evidence supporting your correction"></textarea><div id="form-error" role="alert"></div><div class="dialog-actions"><button type="button" id="cancel">Cancel</button><button type="submit" class="primary" id="save">Save request</button></div></form></dialog>
<script id="table-data" type="application/json">__TABLE_DATA__</script>
<script>
'use strict';
const table=JSON.parse(document.getElementById('table-data').textContent);
const $=id=>document.getElementById(id), token=new URL(location.href).searchParams.get('token');
const state={search:'',filter:'all',all:false,sort:null,descending:false,page:0,selected:null,action:null,requested:new Set(),saved:0};
const hidden=new Set(['invoice_id','transaction_id','allocation_id','business_id','record_sha256','imported_at','request_json','result_json','inputs_json','rule_json','email_message_id']);
const allAud=table.rows.length>0&&table.rows.every(row=>row.values.currency==='AUD');
if(allAud)hidden.add('currency');
const sourceFields=new Set(['source','source_path','file','document_path','statement']);
const label=key=>key==='issues'||key==='__review_task'?'What needs review':sourceFields.has(key)?'Document':key.replace(/_cents$/,'').replace(/_/g,' ').replace(/\b\w/g,c=>c.toUpperCase())+(key.endsWith('_cents')?' (amount)':'');
function reviewTasks(row){const tasks=[];for(const key of ['issues','blockers']){const raw=row.values[key];if(!raw||raw==='[]')continue;try{const parsed=JSON.parse(raw);if(Array.isArray(parsed))tasks.push(...parsed.map(String));else tasks.push(raw)}catch{tasks.push(raw)}}if(!row.values.currency&&table.columns.includes('currency'))tasks.push('Confirm the invoice currency.');for(const [key,value] of Object.entries(row.values)){if(key.endsWith('_cents')&&!value)tasks.push('Check '+label(key).replace(' (amount)','').toLowerCase()+' against the original document.');}if(!tasks.length){if(/needs_review|unresolved/.test(row.values.review_status||row.values.status||''))tasks.push('Codex must identify the unresolved fields before asking you to approve.');if(row.values.gst_status==='pending')tasks.push('Resolve business-use evidence and GST entitlement before claiming a credit.');if(/provisional|user_stated/.test(row.values.allocation_status||''))tasks.push('Provide usage evidence supporting the business-use percentage.');if(row.values.automatically_confirmed==='False'||row.values.automatically_confirmed==='false')tasks.push('Confirm that this invoice and bank payment belong together.');if(row.values.status==='draft'&&!tasks.length)tasks.push('Draft result: resolve the supporting review tasks before approval.');}return [...new Set(tasks)]}
const warn=row=>reviewTasks(row).length>0;
const clearMessage=row=>table.columns.includes('review_status')?'No extraction issues flagged':'No issues listed';
const node=(tag,text,cls)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e};
$('title').textContent=table.title;document.title=table.title+' · Accounting review';$('count').textContent=table.rows.length+' rows';$('issues').textContent=table.rows.filter(warn).length+' rows need attention';$('filename').textContent=table.csv;document.querySelector('.subtitle').textContent=(allAud?'All amounts in AUD. ':'')+'Review only the tasks listed below. Questions and corrections are optional when no issues are flagged.';
function cell(row,key){const td=node('td');if(key==='issues'||key==='__review_task'){const tasks=reviewTasks(row);td.className='issue-cell';td.textContent=tasks.length?tasks.join(' · '):clearMessage(row);if(tasks.length)td.classList.add('issue');return td}const value=row.values[key];if(key.endsWith('_cents'))td.className='money';if(sourceFields.has(key)){if(table.links.includes(row.index+':'+key)){const a=node('a','Open document','source');a.href='/source?token='+encodeURIComponent(token)+'&id='+encodeURIComponent(row.index+':'+key);a.target='_blank';a.rel='noopener noreferrer';td.append(a)}else td.append(node('span',value?'Source unavailable':'Unknown','unknown'));return td}
if(!value){td.append(node('span','Unknown','unknown'));return td}
let text=row.display[key];if(key.endsWith('_cents')&&row.values.currency==='AUD')text='$'+text;
if(kStatus(key)){td.append(node('span',text.replace(/_/g,' '),'badge'+(/pending|unresolved|provisional|needs_review|draft/.test(value)?' warn':'')))}else if((key==='issues'||key==='blockers')&&value!=='[]'){try{const list=JSON.parse(value);text=Array.isArray(list)?list.join(' · '):value}catch{}const detail=node('details');const summary=node('summary',text.length>75?text.slice(0,75)+'…':text);detail.append(summary,node('div',text,'issue'));td.classList.add('issue-cell');td.append(detail)}else td.textContent=(key==='issues'&&text==='[]')?'—':text;return td}
function kStatus(key){return key.includes('status')}
function render(){let rows=table.rows.filter(r=>(state.filter!=='issues'||warn(r))&&(state.filter!=='requested'||state.requested.has(r.index))&&Object.values(r.values).join(' ').toLowerCase().includes(state.search));if(state.sort){const key=state.sort;rows.sort((a,b)=>{let aVal=a.values[key],bVal=b.values[key];let n=key.endsWith('_cents')&&aVal&&bVal?(BigInt(aVal)<BigInt(bVal)?-1:BigInt(aVal)>BigInt(bVal)?1:0):aVal.localeCompare(bVal,undefined,{numeric:true});return state.descending?-n:n})}const columns=table.columns.filter(c=>state.all||!hidden.has(c));if(!columns.includes('issues'))columns.push('__review_task');$('head').replaceChildren();const tr=node('tr');for(const key of columns){const th=node('th');th.scope='col';th.setAttribute('aria-sort',state.sort===key?(state.descending?'descending':'ascending'):'none');const b=node('button',label(key)+(state.sort===key?(state.descending?' ↓':' ↑'):''));b.onclick=()=>{state.descending=state.sort===key?!state.descending:false;state.sort=key;render()};th.append(b);tr.append(th)}tr.append(node('th','Actions'));$('head').append(tr);$('body').replaceChildren();const pageRows=rows.slice(state.page*50,(state.page+1)*50);for(const row of pageRows){const tr=node('tr');for(const key of columns)tr.append(cell(row,key));const actions=node('td',undefined,'actions');const check=node('button',state.requested.has(row.index)?'Request saved':warn(row)?'Review issue':'Ask a question');check.onclick=()=>openRequest(row,'check');const correct=node('button','Propose correction');correct.onclick=()=>openRequest(row,'correct');actions.append(check,correct);tr.append(actions);$('body').append(tr)}if(!pageRows.length){const td=node('td','No rows match these filters.');td.colSpan=columns.length+1;const tr=node('tr');tr.append(td);$('body').append(tr)}$('visible').textContent=rows.length?`${state.page*50+1}–${Math.min((state.page+1)*50,rows.length)} of ${rows.length} rows`:'0 rows';$('prev').disabled=state.page===0;$('next').disabled=(state.page+1)*50>=rows.length}
function updateCurrent(){const key=$('field').value,money=key.endsWith('_cents');$('current-label').textContent=money?'Current amount ('+(state.selected.values.currency||'currency unknown')+')':'Current value';$('proposed-label').textContent=money?'Proposed amount ('+(state.selected.values.currency||'currency unknown')+')':'Proposed value';$('current').value=money?(state.selected.values[key]?state.selected.display[key]:''):state.selected.values[key]||'';$('proposed').value=$('current').value.replace(money?/,/g:/$^/g,'');$('proposed').inputMode=money?'decimal':'text'}
function proposedValue(){const key=$('field').value,value=$('proposed').value.trim();if(!key.endsWith('_cents')||value==='')return value;if(!/^-?[0-9]+(?:\.[0-9]{1,2})?$/.test(value))throw new Error('Enter an amount with at most two decimal places.');const negative=value.startsWith('-'),parts=value.replace(/^-/,'').split('.'),cents=BigInt(parts[0])*100n+BigInt((parts[1]||'').padEnd(2,'0'));return (negative?-cents:cents).toString()}
function openRequest(row,action){state.selected=row;state.action=action;$('dialog-title').textContent=action==='check'?(warn(row)?'Review the listed issue':'Ask an optional question'):'Propose a correction';$('record').textContent=['Row '+(row.index+1),...Object.entries(row.values).filter(([k])=>['invoice_id','id','supplier','contact','description','invoice_number','date'].includes(k)).map(([k,v])=>label(k)+': '+v)].join('\n')+'\n\n'+(reviewTasks(row).length?'What needs review:\n'+reviewTasks(row).join('\n'):clearMessage(row)+'. No action is required unless you spotted something.');$('correction').classList.toggle('hidden',action!=='correct');$('field').replaceChildren();for(const key of table.columns.filter(c=>c!=='id'&&!c.endsWith('_id')&&!sourceFields.has(c))){const o=node('option',label(key));o.value=key;$('field').append(o)}$('reason').value=action==='check'&&warn(row)?'Please check: '+reviewTasks(row).join(' '):'';$('form-error').textContent='';updateCurrent();$('dialog').showModal();$('reason').focus()}
$('field').onchange=updateCurrent;$('cancel').onclick=()=>$('dialog').close();$('form').onsubmit=async event=>{event.preventDefault();$('save').disabled=true;$('form-error').textContent='';try{const changes=state.action==='correct'?{[$('field').value]:proposedValue()}:{};const response=await fetch('/requests',{method:'POST',headers:{'Content-Type':'application/json','X-Review-Token':token},body:JSON.stringify({action:state.action,row:state.selected.index,reason:$('reason').value,changes})});const result=await response.json();if(!response.ok)throw new Error(result.error||'Request was not saved');state.requested.add(state.selected.index);state.saved++;$('requests').textContent=state.saved+' requests saved this session';$('notice').className='status';$('notice').textContent='Request saved. Ask Codex to review and apply it: '+result.saved_request;$('dialog').close();render()}catch(error){$('form-error').textContent=error.message}finally{$('save').disabled=false}};
$('search').oninput=event=>{state.search=event.target.value.toLowerCase();state.page=0;render()};$('filter').onchange=event=>{state.filter=event.target.value;state.page=0;render()};$('columns').onchange=event=>{state.all=event.target.value==='all';render()};$('prev').onclick=()=>{state.page--;render()};$('next').onclick=()=>{state.page++;render()};render();
</script></body></html>"""
