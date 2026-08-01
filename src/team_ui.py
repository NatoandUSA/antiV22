"""Team Operations OS — the web layer (sidebar SaaS dashboard).

Mounted under ``/team/ops`` by src/web.py's build_app(). The eight sections are
Team Home, Task Board, My Tasks, Proactive Working Log, Review Queue, Team
Analytics, Staff Directory and Settings.

All the rules live in src/team_ops.py; this file only renders and routes. It is
an internal execution board: no Etsy login, no Seller API, nothing published.
"""
import csv
import io
import json
from datetime import timedelta
from urllib.parse import urlencode

from src import team_ops as T

NAV = [("/team/ops", "🏠", "Team Home", "all"),
       ("/team/ops/board", "🗂️", "Task Board", "all"),
       ("/team/ops/my", "✅", "My Tasks", "all"),
       ("/team/ops/reports", "📝", "Daily Reports", "all"),
       ("/team/ops/review", "🔍", "Review Queue", "manager"),
       ("/team/ops/analytics", "📊", "Team Analytics", "manager"),
       ("/team/ops/staff", "👥", "Staff Directory", "all"),
       ("/team/ops/settings", "⚙️", "Settings", "owner"),
       ("/team/ops/system-health", "🩺", "System Health", "owner")]

# Alternate paths that belong to a nav entry, so the sidebar still highlights.
NAV_ALIASES = {"/team/ops/my-tasks": "/team/ops/my",
               "/team/ops/logs": "/team/ops/reports",
               "/team/ops/daily-reports": "/team/ops/reports",
               "/team/ops/working-log": "/team/ops/reports"}

# Shown wherever someone could mistake the new board for the old one.
NEW_BADGE = ('<span class="sysbadge new">New Team Ops task system</span>')
LEGACY_NOTE = ('<div class="rollout"><b>New Team Ops task system.</b> '
               '<span>Legacy task system remains active during rollout — the old '
               'board is still at <a href="/me/tasks">/me/tasks</a> and '
               '<a href="/admin/tasks">/admin/tasks</a>. Nothing is migrated '
               'automatically.</span></div>')

BOARD_COLUMNS = [("TODO", "To-do"), ("IN_PROGRESS", "In Progress"),
                 ("REVIEW", "Review"), ("FIX_REQUESTED", "Fix Requested"),
                 ("DONE", "Done")]

CSS = """
<style>
.tops{display:flex;gap:0;min-height:100vh;font-size:.9rem}
.tops *{box-sizing:border-box}
.tops-nav{flex:0 0 210px;background:var(--surface);border-right:1px solid var(--line);
padding:18px 12px;position:sticky;top:0;align-self:flex-start;height:100vh;overflow-y:auto}
.tops-brand{font-family:var(--mono);font-size:.64rem;letter-spacing:.14em;
text-transform:uppercase;color:var(--accent);font-weight:700;padding:0 10px 12px}
.tops-nav a{display:flex;align-items:center;gap:9px;padding:9px 11px;border-radius:9px;
color:var(--ink-soft);font-weight:600;font-size:.86rem;margin-bottom:2px}
.tops-nav a:hover{background:var(--row);color:var(--ink)}
.tops-nav a.on{background:var(--accent-bg);color:var(--accent)}
.tops-nav .navsep{border-top:1px solid var(--line);margin:14px 4px 10px}
.tops-main{flex:1;min-width:0;padding:22px 26px 60px;max-width:1500px}
.tops-head{display:flex;align-items:flex-start;justify-content:space-between;
gap:14px;flex-wrap:wrap;margin-bottom:16px}
.tops-head h1{font-size:1.35rem;margin:0}
.tops-head p{margin:3px 0 0;color:var(--ink-soft);font-size:.84rem}
.tops-actions{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.tbtn{display:inline-block;padding:8px 13px;border:1px solid var(--line-strong);
border-radius:8px;background:var(--surface);color:var(--ink);font-weight:600;
font-size:.82rem;cursor:pointer;font-family:inherit}
.tbtn:hover{border-color:var(--accent);color:var(--accent)}
.tbtn.primary{background:var(--accent);border-color:var(--accent);color:#fff}
.tbtn.primary:hover{filter:brightness(1.08);color:#fff}
.tbtn.danger{color:var(--stop);border-color:var(--stop)}
.tbtn.sm{padding:4px 9px;font-size:.74rem}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(255px,1fr));gap:12px}
.card{background:var(--surface);border:1px solid var(--line);border-radius:12px;
padding:13px 15px;box-shadow:var(--shadow)}
.card h3{margin:0 0 8px;font-size:.8rem;text-transform:uppercase;letter-spacing:.05em;
color:var(--ink-soft);display:flex;justify-content:space-between;align-items:center}
.card h3 .n{background:var(--accent-bg);color:var(--accent);border-radius:20px;
padding:1px 8px;font-size:.76rem}
.card.crit h3 .n{background:#99271F;color:#fff}
.card.warn h3 .n{background:#B45309;color:#fff}
.card ul{margin:0;padding:0;list-style:none}
.card li{padding:6px 0;border-top:1px solid var(--line);font-size:.83rem}
.card li:first-child{border-top:0}
.card .none{color:var(--ink-faint);font-size:.82rem;margin:2px 0 0}
.kpis{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:10px;margin-bottom:16px}
.kpi{background:var(--surface);border:1px solid var(--line);border-radius:11px;padding:11px 13px}
.kpi .n{font-size:1.5rem;font-weight:800;line-height:1.1;font-variant-numeric:tabular-nums}
.kpi .l{font-size:.73rem;color:var(--ink-soft);text-transform:uppercase;letter-spacing:.04em}
.kpi.bad .n{color:var(--stop)}.kpi.good .n{color:var(--ok)}
.filters{display:flex;gap:7px;flex-wrap:wrap;align-items:end;background:var(--surface);
border:1px solid var(--line);border-radius:11px;padding:11px 13px;margin-bottom:14px}
.filters label{display:flex;flex-direction:column;gap:3px;font-size:.7rem;
text-transform:uppercase;letter-spacing:.04em;color:var(--ink-soft);font-weight:700}
.filters input,.filters select{padding:7px 9px;border:1px solid var(--line-strong);
border-radius:7px;background:var(--paper);color:var(--ink);font-size:.83rem;font-family:inherit}
.board{display:flex;gap:11px;overflow-x:auto;padding-bottom:12px;align-items:flex-start}
.bcol{flex:0 0 268px;background:var(--row);border:1px solid var(--line);border-radius:12px;padding:9px}
.bcol h3{margin:0 0 9px;font-size:.75rem;text-transform:uppercase;letter-spacing:.06em;
color:var(--ink-soft);display:flex;justify-content:space-between}
.tcard{background:var(--surface);border:1px solid var(--line);border-left:3px solid var(--line-strong);
border-radius:9px;padding:9px 10px;margin-bottom:8px;display:block;color:inherit}
.tcard:hover{border-color:var(--accent)}
.tcard.d-overdue{border-left-color:#99271F}
.tcard.d-soon{border-left-color:#B45309}
.tcard.d-ontrack{border-left-color:#1E6B54}
.tcard.d-fix{border-left-color:#7C3AED}
.tcard b{display:block;font-size:.85rem;line-height:1.3;margin-bottom:5px}
.tcrow{display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-top:5px}
.av{width:21px;height:21px;border-radius:50%;background:var(--accent-bg);color:var(--accent);
font-size:.63rem;font-weight:800;display:inline-flex;align-items:center;justify-content:center;flex:none}
.tag{font-size:.68rem;font-weight:700;border-radius:5px;padding:1px 6px;
background:var(--row);color:var(--ink-soft);border:1px solid var(--line)}
.tag.p-URGENT{background:#99271F;color:#fff;border-color:#99271F}
.tag.p-HIGH{background:#B45309;color:#fff;border-color:#B45309}
.tag.p-MEDIUM{background:#3B6E8F;color:#fff;border-color:#3B6E8F}
.tag.d-overdue{background:#99271F;color:#fff;border-color:#99271F}
.tag.d-soon{background:#B45309;color:#fff;border-color:#B45309}
.tag.d-fix{background:#7C3AED;color:#fff;border-color:#7C3AED}
.tag.d-ontrack{background:transparent;color:var(--ok);border-color:var(--ok)}
.tag.st{background:var(--accent-bg);color:var(--accent);border-color:var(--accent-bg)}
.tpick{display:block;font-size:.68rem;color:var(--ink-faint);margin:0 0 3px 2px;cursor:pointer}
.tpick input{vertical-align:middle;margin-right:4px}
.cprev{font-size:.74rem;color:var(--ink-faint);margin-top:5px;font-style:italic;
overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.ckbar{height:4px;background:var(--line);border-radius:3px;margin-top:6px;overflow:hidden}
.ckbar i{display:block;height:100%;background:var(--ok)}
table.grid{width:100%;border-collapse:collapse;font-size:.81rem;background:var(--surface)}
table.grid th{background:var(--row);text-align:left;padding:7px 8px;font-size:.7rem;
text-transform:uppercase;letter-spacing:.04em;color:var(--ink-soft);
border-bottom:1px solid var(--line-strong);white-space:nowrap}
table.grid td{padding:5px 8px;border-bottom:1px solid var(--line);vertical-align:middle}
table.grid tr:hover td{background:var(--row)}
table.grid td.ed{cursor:text}
table.grid td.ed:hover{outline:1px dashed var(--accent);outline-offset:-2px}
table.grid td.locked{color:var(--ink-faint);cursor:not-allowed}
.gwrap{overflow-x:auto;border:1px solid var(--line);border-radius:11px}
/* daily-report grid: status colour, one-click links, review verdict */
.stx{display:inline-block;font-size:.7rem;font-weight:700;border-radius:20px;
padding:2px 9px;white-space:nowrap;border:1px solid transparent}
.stx.s-draft{background:var(--row);color:var(--ink-soft);border-color:var(--line-strong)}
.stx.s-completed{background:#1E6B54;color:#fff}
.stx.s-listed{background:#3B6E8F;color:#fff}
.stx.s-waiting-review{background:#B45309;color:#fff}
.stx.s-blocked{background:#99271F;color:#fff}
.ulink{display:inline-block;font-size:.72rem;font-weight:700;color:var(--accent);
background:var(--surface);border:1px solid var(--line-strong);border-radius:20px;
padding:2px 9px;white-space:nowrap;text-decoration:none}
.ulink:hover{border-color:var(--accent);background:var(--accent-bg)}
.uempty{font-size:.72rem;color:var(--ink-faint)}
.pen{border:0;background:none;color:var(--ink-faint);cursor:pointer;
font-size:.72rem;padding:2px 4px;font-family:inherit}
.pen:hover{color:var(--accent)}
.rv{display:inline-block;font-size:.7rem;font-weight:700;border-radius:20px;
padding:2px 9px;white-space:nowrap;border:1px solid transparent}
.rv.approved{background:#1E6B54;color:#fff}
.rv.improve{background:#B45309;color:#fff}
.rv.rejected{background:#99271F;color:#fff}
.rv.pending{background:var(--row);color:var(--ink-soft);border-color:var(--line-strong)}
.acts{display:flex;gap:5px;flex-wrap:nowrap;align-items:center}
.tbtn.ok{color:#1E6B54;border-color:#1E6B54}
.tbtn.ok:hover{background:#1E6B54;color:#fff}
.tbtn.imp{color:#B45309;border-color:#B45309}
.tbtn.imp:hover{background:#B45309;color:#fff}
.tbtn.danger:hover{background:var(--stop);border-color:var(--stop);color:#fff}
.tbtn.ic{color:var(--ink-faint);border-color:var(--line)}
.tbtn.ic:hover{color:var(--accent);border-color:var(--accent)}
.saved{color:var(--ok);font-size:.72rem;font-weight:700;margin-left:8px}
.alert{display:flex;gap:11px;align-items:flex-start;padding:10px 13px;border-radius:10px;
border:1px solid var(--line);background:var(--surface);margin-bottom:8px;border-left-width:4px}
.alert.critical{border-left-color:#99271F}
.alert.warning{border-left-color:#B45309}
.alert.info{border-left-color:#3B6E8F}
.alert b{font-size:.85rem}
.alert p{margin:2px 0 0;font-size:.79rem;color:var(--ink-soft)}
.fgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:11px}
.fgrid label,.fstack label{display:flex;flex-direction:column;gap:4px;font-size:.72rem;
font-weight:700;text-transform:uppercase;letter-spacing:.04em;color:var(--ink-soft)}
.fgrid input,.fgrid select,.fgrid textarea,.fstack input,.fstack select,.fstack textarea{
padding:8px 10px;border:1px solid var(--line-strong);border-radius:8px;background:var(--paper);
color:var(--ink);font-size:.86rem;font-family:inherit;font-weight:400;text-transform:none;letter-spacing:0}
.fstack{display:flex;flex-direction:column;gap:11px}
.fwide{grid-column:1/-1}
.panel{background:var(--surface);border:1px solid var(--line);border-radius:12px;
padding:15px 17px;margin-bottom:14px;box-shadow:var(--shadow)}
.panel h2{margin:0 0 11px;font-size:.98rem}
.ck{display:flex;align-items:center;gap:8px;padding:5px 0;font-size:.84rem;border-top:1px solid var(--line)}
.ck:first-of-type{border-top:0}
.ck input{width:16px;height:16px}
.ck .req{color:var(--stop);font-weight:700;font-size:.7rem}
.tl{list-style:none;margin:0;padding:0}
.tl li{padding:7px 0 7px 15px;border-left:2px solid var(--line);font-size:.81rem;position:relative}
.tl li:before{content:'';position:absolute;left:-4px;top:12px;width:6px;height:6px;
border-radius:50%;background:var(--line-strong)}
.tl .who{font-weight:700}.tl .when{color:var(--ink-faint);font-size:.73rem}
.msg{padding:9px 13px;border-radius:9px;margin-bottom:12px;font-size:.85rem}
.msg.ok{background:#1E6B54;color:#fff}
.msg.err{background:#99271F;color:#fff}
.rollout{display:flex;gap:8px;flex-wrap:wrap;align-items:baseline;background:var(--accent-bg);
border:1px solid var(--accent);border-radius:10px;padding:9px 13px;margin-bottom:13px;font-size:.81rem}
.rollout b{color:var(--accent)}
.rollout span{color:var(--ink-soft)}
.sysbadge{display:inline-block;font-size:.66rem;font-weight:800;letter-spacing:.04em;
text-transform:uppercase;border-radius:20px;padding:2px 9px;vertical-align:middle}
.sysbadge.new{background:var(--accent);color:#fff}
.sysbadge.legacy{background:var(--ink-faint);color:#fff}
.hstate{font-size:.68rem;font-weight:800;text-transform:uppercase;letter-spacing:.05em;
border-radius:5px;padding:2px 7px;color:#fff}
.hstate.ok{background:#1E6B54}.hstate.warn{background:#B45309}.hstate.fail{background:#99271F}
.hbanner{display:flex;gap:12px;align-items:center;border-radius:12px;padding:13px 16px;
margin-bottom:14px;color:#fff;font-size:.9rem}
.hbanner.ok{background:#1E6B54}.hbanner.warn{background:#B45309}.hbanner.fail{background:#99271F}
.hbanner b{font-size:1.02rem}
.tsec{font-size:.78rem;text-transform:uppercase;letter-spacing:.06em;color:var(--ink-soft);
margin:20px 0 8px;font-weight:700}
.bulkbar{display:flex;gap:8px;align-items:center;flex-wrap:wrap;background:var(--accent-bg);
border:1px solid var(--accent);border-radius:10px;padding:9px 12px;margin-bottom:12px}
.bulkbar select,.bulkbar input{padding:6px 8px;border:1px solid var(--line-strong);
border-radius:7px;background:var(--paper);color:var(--ink);font-size:.8rem}
@media(max-width:820px){.tops{flex-direction:column}
.tops-nav{flex:none;width:100%;height:auto;position:static;border-right:0;
border-bottom:1px solid var(--line);display:flex;flex-wrap:wrap;gap:4px}
.tops-nav .tops-brand,.tops-nav .navsep{width:100%}.tops-main{padding:16px}}
</style>
"""

AUTOSAVE_JS = """
<script>
(function(){
  var tok = document.body.getAttribute('data-csrf') || '';
  function save(td, value){
    var tr = td.closest('tr');
    var fd = new FormData();
    fd.append('_csrf', tok);
    fd.append('field', td.getAttribute('data-field'));
    fd.append('value', value);
    var reason = tr.getAttribute('data-locked') === '1'
      ? (prompt('This log is older than 48h. Reason for the edit?') || '') : '';
    if (tr.getAttribute('data-locked') === '1' && !reason){ render(td); return; }
    fd.append('edit_reason', reason);
    fetch('/team/ops/reports/' + tr.getAttribute('data-id') + '/save',
          {method:'POST', body:fd, credentials:'same-origin'})
      .then(function(r){ return r.json(); })
      .then(function(j){
        if(j.ok){ td.setAttribute('data-value', j.value); render(td); flash(td, 'Saved'); }
        else { render(td); flash(td, j.error || 'Not saved', true); }
      })
      .catch(function(){ render(td); flash(td, 'Network error', true); });
  }
  function flash(td, text, bad){
    var s = document.createElement('span');
    s.className = 'saved'; s.textContent = text;
    if(bad){ s.style.color = '#99271F'; }
    td.appendChild(s);
    setTimeout(function(){ if(s.parentNode){ s.parentNode.removeChild(s); } }, 2600);
  }
  // Keep this in step with _cell_html() in team_ui.py — a cell must look the
  // same after an inline save as it did on a fresh page load.
  var ULAB = {link_folder_google_drive: '📁 Drive folder',
              listing_url: '🔗 Listing'};
  function mk(tag, cls, text){
    var n = document.createElement(tag);
    if(cls){ n.className = cls; } if(text){ n.textContent = text; } return n;
  }
  function render(td){
    var v = td.getAttribute('data-value') || '';
    var mode = td.getAttribute('data-render') || '';
    td.textContent = '';
    if(mode === 'status'){
      if(v){ td.appendChild(mk('span',
        'stx s-' + v.toLowerCase().replace(/[^a-z0-9]+/g, '-'), v)); }
      return;
    }
    if(mode === 'url'){
      if(/^https?:\\/\\//i.test(v)){
        var a = mk('a', 'ulink',
                   (ULAB[td.getAttribute('data-field')] || '🔗 Open') + ' ↗');
        a.href = v; a.target = '_blank'; a.rel = 'noopener'; a.title = v;
        td.appendChild(a);
      } else {
        td.appendChild(mk('span', 'uempty', v || '＋ add link'));
      }
      var pen = mk('button', 'pen', '✎');
      pen.type = 'button'; pen.title = 'Edit link';
      pen.setAttribute('data-edit', '');
      td.appendChild(pen);
      return;
    }
    td.textContent = v;
  }
  document.addEventListener('click', function(e){
    var b = e.target.closest ? e.target.closest('[data-edit]') : null;
    if(!b) return;
    e.preventDefault();
    var td = b.closest('td.ed');
    if(td){ startEdit(td); }
  });
  document.addEventListener('dblclick', function(e){
    if(!e.target.closest || e.target.closest('a')) return;  // let links open
    var td = e.target.closest('td.ed');
    if(td){ startEdit(td); }
  });
  function startEdit(td){
    if(td.querySelector('input,select')) return;
    var cur = td.getAttribute('data-value') || '';
    var opts = td.getAttribute('data-options');
    var el;
    if(opts){
      el = document.createElement('select');
      opts.split('|').forEach(function(o){
        var op = document.createElement('option'); op.value = o; op.textContent = o;
        if(o === cur){ op.selected = true; } el.appendChild(op);
      });
    } else {
      el = document.createElement('input');
      el.type = td.getAttribute('data-type') || 'text';
      el.value = cur;
    }
    el.style.width = '100%';
    td.textContent = ''; td.appendChild(el); el.focus();
    var done = false;
    function commit(){
      if(done) return; done = true;
      var v = el.value;
      if(v === cur){ render(td); return; }
      save(td, v);
    }
    el.addEventListener('blur', commit);
    el.addEventListener('keydown', function(ev){
      if(ev.key === 'Enter'){ ev.preventDefault(); el.blur(); }
      if(ev.key === 'Escape'){ done = true; render(td); }
    });
  }
  window.topsNote = function(id, action){
    var labels = {clarify: 'What should this person improve? (they get notified)',
                  blocked: 'Why are you rejecting this report?',
                  note: 'Manager note for this report:'};
    var note = prompt(labels[action] || 'Note:');
    if(note === null) return;
    if(!note.trim()){ return; }
    var f = document.getElementById('tops-note-form');
    f.action = '/team/ops/reports/' + id + '/action';
    f.querySelector('input[name="action"]').value = action;
    f.querySelector('input[name="note"]').value = note;
    f.submit();
  };
  var all = document.getElementById('bulk-all');
  if(all){ all.addEventListener('change', function(){
    document.querySelectorAll('input[name="task_ids"]').forEach(function(c){
      c.checked = all.checked; });
  }); }
})();
</script>
"""


def register(app, page, login_required, current_user, log, esc_raw, safe_url, csrf):
    """Attach every /team/ops route. Helpers come from web.build_app()."""
    from flask import request, redirect, Response

    def esc(v):
        """web.py's escaper blanks a falsy value, which would hide a count of 0."""
        return esc_raw("" if v is None else str(v))

    # ------------------------------------------------------------ shell ----
    def shell(title, subtitle, body, user, actions="", msg="", badge=""):
        cur = NAV_ALIASES.get(request.path, request.path)
        items = ""
        for href, icon, label, need in NAV:
            if need == "manager" and not T.is_manager(user):
                continue
            if need == "owner" and not T.is_owner(user):
                continue
            on = " on" if cur == href else ""
            items += ('<a class="' + ("on" if on else "") + '" href="' + href + '">'
                      + icon + ' <span>' + label + '</span></a>')
        unread = T.unread_count(user["user_id"])
        bell = ('<a href="/team/ops/notifications">🔔 <span>Notifications'
                + (' (' + str(unread) + ')' if unread else '') + '</span></a>')
        nav = ('<aside class="tops-nav"><div class="tops-brand">Team Ops</div>'
               + items + '<div class="navsep"></div>' + bell
               + '<a href="/team">↩ <span>Command Center</span></a>'
               + '<a href="/">🏠 <span>Dashboard</span></a></aside>')
        banner = ""
        for kind, key in (("ok", "ok"), ("err", "err")):
            val = request.args.get(key)
            if val:
                banner += '<div class="msg ' + kind + '">' + esc(val) + '</div>'
        if msg:
            banner += msg
        # `title` also fills <title>, so a badge must never be baked into it.
        main = ('<main class="tops-main"><div class="tops-head"><div><h1>' + title
                + (' ' + badge if badge else "")
                + '</h1><p>' + subtitle + '</p></div>'
                + '<div class="tops-actions">' + actions + '</div></div>'
                + banner + body + '</main>')
        return page(title, CSS + '<div class="tops">' + nav + main + '</div>'
                    + AUTOSAVE_JS)

    @app.after_request
    def _tops_csrf_attr(resp):
        """Expose the CSRF token to the inline-edit fetch() calls."""
        try:
            if (request.path.startswith("/team/ops")
                    and "text/html" in resp.headers.get("Content-Type", "")
                    and resp.direct_passthrough is False):
                data = resp.get_data(as_text=True)
                # Match the bare opening tag only: the string "data-csrf" also
                # appears inside AUTOSAVE_JS, so a document-wide check would
                # always short-circuit. Replacing <body> is idempotent.
                if "<body>" in data:
                    resp.set_data(data.replace(
                        "<body>", '<body data-csrf="' + csrf() + '">', 1))
        except Exception:  # noqa: BLE001 - never break a page over a decoration
            pass
        return resp

    # ------------------------------------------------------- small parts ----
    def initials(name):
        parts = (name or "").split()
        return ("".join(p[0] for p in parts[:2]).upper() or "•")

    def who(uid, names):
        return names.get(uid, {}).get("display_name") or "Unassigned"

    def avatar(uid, names):
        nm = who(uid, names)
        return ('<span class="av" title="' + esc(nm) + '">' + esc(initials(nm))
                + '</span>')

    def due_tag(t, user):
        state = T.due_state(t)
        if state == "none":
            return ""
        label = {"overdue": "Overdue", "soon": "Due soon", "fix": "Fix requested",
                 "ontrack": "On track"}[state]
        when = T.to_local(t.get("due_at"), user, "%d %b %H:%M")
        return ('<span class="tag d-' + state + '">' + label
                + (" · " + esc(when) if when else "") + '</span>')

    def task_card(t, user, names, previews, select=False):
        tid = t["id"]
        state = T.due_state(t)
        ttype = T.TASK_TYPE_LABELS.get(t.get("task_type"), t.get("task_type") or "—")
        done_n = t.get("checklist_completed_count") or 0
        total_n = t.get("checklist_total_count") or 0
        bar = ""
        if total_n:
            pct = int(100 * done_n / total_n)
            bar = ('<div class="ckbar"><i style="width:' + str(pct) + '%"></i></div>')
        prev = previews.get(tid)
        kw = t.get("related_keyword") or ""
        store = t.get("related_store") or ""
        links_n = len(t.get("links") or []) + (1 if t.get("drive_folder") else 0)
        meta = ""
        if kw:
            meta += '<span class="tag">🔑 ' + esc(kw[:22]) + '</span>'
        if store:
            meta += '<span class="tag">🏪 ' + esc(store[:16]) + '</span>'
        if links_n:
            meta += '<span class="tag">🔗 ' + str(links_n) + '</span>'
        if total_n:
            meta += ('<span class="tag">☑ ' + str(done_n) + '/' + str(total_n)
                     + '</span>')
        prio = t.get("priority") or "MEDIUM"
        pick = ('<label class="tpick"><input type="checkbox" name="task_ids" value="'
                + str(tid) + '"> select</label>' if select else "")
        return (pick
                + '<a class="tcard d-' + state + '" href="/team/ops/task/' + str(tid) + '">'
                '<b>' + esc((t.get("title") or "")[:70]) + '</b>'
                '<div class="tcrow">' + avatar(t.get("assignee_id"), names)
                + '<span class="tag">' + esc(ttype) + '</span>'
                + '<span class="tag p-' + esc(prio) + '">' + esc(prio) + '</span></div>'
                + ('<div class="tcrow">' + meta + '</div>' if meta else '')
                + '<div class="tcrow">' + due_tag(t, user) + '</div>'
                + bar
                + ('<div class="cprev">💬 ' + esc((prev or "")[:60]) + '</div>'
                   if prev else '')
                + '</a>')

    def task_list_card(title, rows, user, names, cls=""):
        if not rows:
            body = '<p class="none">Nothing here — clear. ✨</p>'
        else:
            body = "<ul>"
            for t in rows[:8]:
                body += ('<li><a href="/team/ops/task/' + str(t["id"]) + '">'
                         + esc((t.get("title") or "")[:52]) + '</a> '
                         + due_tag(t, user) + '</li>')
            if len(rows) > 8:
                body += '<li class="none">+' + str(len(rows) - 8) + ' more</li>'
            body += "</ul>"
        return ('<div class="card ' + cls + '"><h3>' + title
                + '<span class="n">' + str(len(rows)) + '</span></h3>' + body + '</div>')

    def opts(values, selected=None, blank=None):
        out = ""
        if blank is not None:
            out += ('<option value="">' + esc(blank) + '</option>')
        for v in values:
            if isinstance(v, (tuple, list)):
                val, lbl = v[0], v[1]
            else:
                val, lbl = v, v
            sel = " selected" if str(val) == str(selected or "") else ""
            out += ('<option value="' + esc(val) + '"' + sel + '>' + esc(lbl)
                    + '</option>')
        return out

    def user_opts(user, selected=None, blank="— Unassigned —"):
        people = [(u["user_id"], (u.get("display_name") or "?") + " · "
                   + T.team_role(u)) for u in T.visible_staff(user)
                  if T.user_active(u)]
        return opts(people, selected, blank)

    def back(msg=None, err=None, to="/team/ops"):
        q = {}
        if msg:
            q["ok"] = msg
        if err:
            q["err"] = err
        return redirect(to + ("?" + urlencode(q) if q else ""))

    def need_manager(user):
        return None if T.is_manager(user) else back(
            err="Manager or Owner only.", to="/team/ops")

    def csv_response(cols, rows, filename):
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
        return Response(buf.getvalue(), mimetype="text/csv", headers={
            "Content-Disposition": 'attachment; filename="' + filename + '"'})

    # =========================================================== TEAM HOME ==
    @app.route("/team/ops")
    @login_required
    def tops_home():
        user = current_user()
        T.init_schema()
        try:
            T.sweep_deadline_notifications()
        except Exception:  # noqa: BLE001 - a notification must never 500 the page
            pass
        names = T.users_by_id()
        q = T.home_queues(user)
        alerts = ""
        for a in q["alerts"][:8]:
            alerts += ('<div class="alert ' + a["severity"] + '"><div><b>'
                       + esc(a["alert_type"]) + ' · ' + esc(a["who"]) + '</b>'
                       '<p>' + esc(a["action"]) + ' (now ' + esc(a["count"])
                       + ', threshold ' + esc(a["threshold"]) + ')</p></div>'
                       + ('<a class="tbtn sm" href="' + a["link"] + '">Open</a>'
                          if a["link"] else "") + '</div>')
        if not alerts:
            alerts = ('<div class="alert info"><div><b>No bottlenecks</b>'
                      '<p>Review queue, workload and daily logs are all inside '
                      'their thresholds.</p></div></div>')
        perf = ""
        for r in q["top_performers"]:
            perf += ('<li><b>' + esc(r["name"]) + '</b> — '
                     + str(r["tasks_done_approved"]) + ' done · '
                     + str(r["design_verified"]) + ' designs · '
                     + str(r["listing_verified"]) + ' listings · Q'
                     + str(r["quality_score"]) + '</li>')
        nolog = ""
        for p in q["no_log"]:
            nolog += ('<li>' + esc(p.get("display_name") or "?")
                      + ' <a class="tbtn sm" href="/team/ops/reports?view=team&amp;'
                      'staff=' + str(p["user_id"]) + '">View</a></li>')
        cards = (
            task_list_card("🔴 My overdue", q["my_overdue"], user, names, "crit")
            + task_list_card("📅 Due today", q["due_today"], user, names)
            + task_list_card("🔍 Waiting for review", q["waiting_review"], user, names)
            + task_list_card("🟣 Fix requested", q["fix_requested"], user, names)
            + task_list_card("✅ Done today", q["done_today"], user, names)
            + ('<div class="card ' + ("warn" if nolog else "") + '"><h3>📝 No daily log'
               '<span class="n">' + str(len(q["no_log"])) + '</span></h3>'
               + ('<ul>' + nolog + '</ul>' if nolog
                  else '<p class="none">Everyone filed today.</p>') + '</div>')
            + ('<div class="card"><h3>🏆 Top performers (7d)'
               '<span class="n">' + str(len(q["top_performers"])) + '</span></h3>'
               + ('<ul>' + perf + '</ul>' if perf
                  else '<p class="none">No completed work yet this week.</p>')
               + '</div>')
            + task_list_card("📥 Waiting to be assigned", q["unassigned"], user, names))
        # ---- Daily Staff Reports card (spec §6) ----
        rep = q["reports"]
        mgr = T.is_manager(user)
        missing_link = ('/team/ops/reports?view=team&amp;missing=1'
                        if mgr else '/team/ops/reports')
        rep_stats = [("Reports submitted today", rep["reports_today"], ""),
                     ("Staff missing report today", rep["missing_today_n"],
                      missing_link),
                     ("Designs today", rep["designs_today"], ""),
                     ("Listings today", rep["listings_today"], ""),
                     ("Blocked reports", rep["blocked"], ""),
                     ("Edited-after-lock reports", rep["edited_after_lock"], "")]
        rep_rows = ""
        for label, n, link in rep_stats:
            val = str(n)
            if link and n:
                val = '<a href="' + link + '"><b>' + val + '</b></a>'
            rep_rows += ('<li style="display:flex;justify-content:space-between;'
                         'gap:8px"><span>' + label + '</span><span>' + val
                         + '</span></li>')
        report_card = ('<div class="card ' + ("warn" if rep["missing_today_n"] else "")
                       + '"><h3>📝 Daily Staff Reports<span class="n">'
                       + str(rep["reports_today"]) + '</span></h3><ul>' + rep_rows
                       + '</ul><div class="tops-actions" style="margin-top:9px">'
                       '<a class="tbtn sm" href="/team/ops/reports">View Daily Reports'
                       '</a><a class="tbtn sm primary" href="/team/ops/reports?'
                       'view=mine">Add My Report</a></div></div>')
        cards = report_card + cards

        warn = ""
        if q["my_report_missing"]:
            warn = ('<div class="hbanner fail"><b>Missing report today</b>'
                    '<span>You have not submitted today\'s Etsy work report. '
                    '<a href="/team/ops/reports?view=mine" style="color:#fff;'
                    'text-decoration:underline">Add it now</a>.</span></div>')
        actions = ('<a class="tbtn primary" href="/team/ops/task/new">➕ Create task</a>'
                   '<a class="tbtn" href="/team/ops/board">Open board</a>')
        body = (warn + '<div class="tsec">Bottleneck alerts</div>' + alerts
                + '<div class="tsec">Action queues</div>'
                + '<div class="cards">' + cards + '</div>')
        return shell("Team Home", "Who is doing what, what is late, and what needs "
                     "you now.", body, user, actions)

    # =========================================================== TASK BOARD ==
    @app.route("/team/ops/board")
    @login_required
    def tops_board():
        user = current_user()
        T.init_schema()
        f = {k: (request.args.get(k) or "").strip()
             for k in ("assignee", "type", "priority", "store", "due", "q")}
        rows = T.list_tasks(user=user, task_type=f["type"] or None,
                            priority=f["priority"] or None,
                            assignee_id=int(f["assignee"]) if f["assignee"].isdigit() else None,
                            store=f["store"] or None, search=f["q"] or None)
        if f["due"] == "overdue":
            rows = [t for t in rows if T.is_overdue(t)]
        elif f["due"] == "soon":
            rows = [t for t in rows if T.is_due_soon(t)]
        names = T.users_by_id()
        previews = T.latest_comments_map([t["id"] for t in rows])
        mgr = T.is_manager(user)
        cols = ""
        for status, label in BOARD_COLUMNS:
            items = [t for t in rows if t["status"] == status]
            body = "".join(task_card(t, user, names, previews, select=mgr)
                           for t in items[:60])
            cols += ('<div class="bcol"><h3><span>' + label + '</span><span>'
                     + str(len(items)) + '</span></h3>'
                     + (body or '<p class="none" style="font-size:.78rem;color:'
                        'var(--ink-faint)">—</p>') + '</div>')
        stores = T.store_options() or sorted(
            {t.get("related_store") for t in rows if t.get("related_store")})
        filt = ('<form class="filters" method="get">'
                '<label>Search<input name="q" value="' + esc(f["q"]) + '" '
                'placeholder="title / keyword"></label>'
                '<label>Assignee<select name="assignee">'
                + user_opts(user, f["assignee"], "Everyone") + '</select></label>'
                '<label>Type<select name="type">'
                + opts(T.TASK_TYPES, f["type"], "All types") + '</select></label>'
                '<label>Priority<select name="priority">'
                + opts(T.PRIORITIES, f["priority"], "Any") + '</select></label>'
                '<label>Store<select name="store">'
                + opts(stores, f["store"], "All stores") + '</select></label>'
                '<label>Deadline<select name="due">'
                + opts([("overdue", "Overdue"), ("soon", "Due soon")], f["due"], "Any")
                + '</select></label>'
                '<button class="tbtn primary" type="submit">Filter</button>'
                '<a class="tbtn" href="/team/ops/board">Reset</a></form>')
        board = '<div class="board">' + cols + '</div>'
        if mgr:
            # The whole board is one form so the per-card checkboxes feed bulk actions.
            board = ('<form method="post" action="/team/ops/board/bulk">'
                     '<div class="bulkbar"><b>Bulk:</b>'
                     '<select name="action">'
                     + opts([("assignee", "Change assignee"),
                             ("due", "Change deadline"),
                             ("priority", "Change priority"),
                             ("status", "Move status"),
                             ("cancel", "Cancel tasks")]) + '</select>'
                     '<select name="assignee">' + user_opts(user, None, "—") + '</select>'
                     '<input type="datetime-local" name="due_at">'
                     '<select name="priority">' + opts(T.PRIORITIES) + '</select>'
                     '<select name="status">'
                     + opts([(s, T.STATUS_LABELS[s]) for s in T.STATUSES]) + '</select>'
                     '<label style="font-size:.76rem;font-weight:600">'
                     '<input type="checkbox" id="bulk-all"> all shown</label>'
                     '<button class="tbtn primary" type="submit">Apply to selected'
                     '</button></div>' + board + '</form>')
        actions = ('<a class="tbtn primary" href="/team/ops/task/new">➕ Create task</a>'
                   + ('<a class="tbtn" href="/team/ops/export/tasks.csv">⬇ CSV</a>'
                      if T.is_owner(user) else ""))
        return shell("Task Board",
                     str(len(rows)) + " tasks in scope · green on track, "
                     "yellow due soon, red overdue, purple fix requested.",
                     LEGACY_NOTE + filt + board, user, actions, badge=NEW_BADGE)

    @app.route("/team/ops/board/bulk", methods=["POST"])
    @login_required
    def tops_board_bulk():
        user = current_user()
        guard = need_manager(user)
        if guard:
            return guard
        ids = [int(x) for x in request.form.getlist("task_ids") if x.isdigit()]
        action = request.form.get("action")
        n, skipped = 0, 0
        for tid in ids:
            t = T.get_task(tid, include_deleted=False)
            if not t or not T.can_see_task(user, t):
                skipped += 1
                continue
            if action == "assignee":
                aid = request.form.get("assignee")
                T.update_task(tid, actor=user,
                              assignee_id=int(aid) if (aid or "").isdigit() else None)
            elif action == "due":
                T.update_task(tid, actor=user, due_at=T.local_dt_to_utc(
                    request.form.get("due_at"), user))
            elif action == "priority":
                T.update_task(tid, actor=user, priority=request.form.get("priority"))
            elif action == "status":
                _t, err = T.set_status(tid, request.form.get("status"), user)
                if err:
                    skipped += 1
                    continue
            elif action == "cancel":
                _t, err = T.set_status(tid, "CANCELLED", user)
                if err:
                    skipped += 1
                    continue
            n += 1
        log("TASK_UPDATE", module="team_ops", summary="bulk " + str(action)
            + " on " + str(n) + " tasks")
        return back(msg=str(n) + " task(s) updated"
                    + (", " + str(skipped) + " skipped" if skipped else ""),
                    to="/team/ops/board")

    # ============================================================= MY TASKS ==
    @app.route("/team/ops/my")
    @app.route("/team/ops/my-tasks")
    @login_required
    def tops_my():
        user = current_user()
        T.init_schema()
        names = T.users_by_id()
        uid = user["user_id"]
        mine = [t for t in T.list_tasks(user=user) if t.get("assignee_id") == uid]
        today = T.local_today(user)
        groups = [
            ("Overdue", [t for t in mine if T.is_overdue(t)]),
            ("Due today", [t for t in mine
                           if T.to_local(t.get("due_at"), user, "%Y-%m-%d") == today
                           and t["status"] in T.ACTIVE_STATUSES]),
            ("In progress", [t for t in mine if t["status"] == "IN_PROGRESS"]),
            ("Waiting for review", [t for t in mine if t["status"] == "REVIEW"]),
            ("Fix requested", [t for t in mine if t["status"] == "FIX_REQUESTED"]),
            ("To-do", [t for t in mine if t["status"] == "TODO"]),
            ("Done recently", [t for t in mine if t["status"] == "DONE"][:10]),
        ]
        previews = T.latest_comments_map([t["id"] for t in mine])
        body = ""
        for label, rows in groups:
            if not rows:
                continue
            body += ('<div class="tsec">' + label + ' (' + str(len(rows)) + ')</div>'
                     '<div class="cards">'
                     + "".join(task_card(t, user, names, previews) for t in rows)
                     + '</div>')
        if not body:
            body = ('<div class="panel"><p>No tasks assigned to you. Enjoy the quiet — '
                    'or report today\'s Etsy work in <a href="/team/ops/reports">'
                    'Daily Reports</a>.</p></div>')
        return shell("My Tasks",
                     "Only your work. Start it, submit it, get it approved.",
                     LEGACY_NOTE + body, user, badge=NEW_BADGE)

    # =========================================================== TASK CRUD ==
    def task_form(user, task=None, prefill=None):
        p = prefill or {}
        t = task or {}
        cur_type = t.get("task_type") or p.get("type") or (
            "DESIGN" if T.team_role(user) == "DESIGNER" else "RESEARCH")
        types = T.TASK_TYPES
        if T.team_role(user) == "DESIGNER" and not task:
            types = ([x for x in T.TASK_TYPES if x[0] in T.DESIGNER_TYPES]
                     + [x for x in T.TASK_TYPES if x[0] not in T.DESIGNER_TYPES])
        due_val = (T.utc_to_local_input(t.get("due_at"), user) if t.get("due_at")
                   else "")
        return (
            '<div class="fgrid">'
            '<label class="fwide">Title<input name="title" required value="'
            + esc(t.get("title") or p.get("title") or "") + '"></label>'
            '<label class="fwide">Description<textarea name="description" rows="2">'
            + esc(t.get("description") or "") + '</textarea></label>'
            '<label>Task type<select name="task_type">' + opts(types, cur_type)
            + '</select></label>'
            '<label>Assignee<select name="assignee_id">'
            + user_opts(user, t.get("assignee_id")) + '</select></label>'
            '<label>Priority<select name="priority">'
            + opts(T.PRIORITIES, t.get("priority") or "MEDIUM") + '</select></label>'
            '<label>Due (your local time)<input type="datetime-local" name="due_at" '
            'value="' + esc(due_val) + '"><span style="font-weight:400;'
            'text-transform:none;color:var(--ink-faint);font-size:.7rem">'
            'Blank = tomorrow 17:00 in the assignee\'s timezone</span></label>'
            '<label>Related keyword<input name="related_keyword" value="'
            + esc(t.get("related_keyword") or p.get("keyword") or "") + '"></label>'
            '<label>Related store / account<input name="related_store" value="'
            + esc(t.get("related_store") or p.get("store") or "") + '"></label>'
            '<label>Opportunity ID<input name="related_opportunity_id" value="'
            + esc(t.get("related_opportunity_id") or p.get("opportunity") or "")
            + '"></label>'
            '<label>Listing ID<input name="related_listing_id" value="'
            + esc(t.get("related_listing_id") or p.get("listing") or "") + '"></label>'
            '<label>Google Drive folder<input name="drive_folder" value="'
            + esc(t.get("drive_folder") or "") + '"></label>'
            '<label class="fwide">Expected output<input name="expected_output" '
            'value="' + esc(t.get("expected_output") or "") + '"></label>'
            '<label class="fwide">Internal notes<textarea name="internal_notes" '
            'rows="2">' + esc(t.get("internal_notes") or "") + '</textarea></label>'
            '</div>')

    @app.route("/team/ops/task/new")
    @login_required
    def tops_task_new():
        user = current_user()
        T.init_schema()
        guard = need_manager(user)
        if guard:
            return guard
        prefill = {k: (request.args.get(k) or "").strip()
                   for k in ("type", "title", "keyword", "opportunity", "listing",
                             "store")}
        body = ('<form method="post" action="/team/ops/task/new"><div class="panel">'
                '<h2>New task</h2>' + task_form(user, prefill=prefill)
                + '<div class="tops-actions" style="margin-top:12px">'
                '<button class="tbtn primary" type="submit">Create + assign</button>'
                '<a class="tbtn" href="/team/ops/board">Cancel</a></div></div></form>'
                '<div class="panel"><p style="margin:0;font-size:.82rem;'
                'color:var(--ink-soft)">The QA checklist for the task type is attached '
                'automatically. Deadlines are stored in UTC and shown in each '
                'person\'s timezone.</p></div>')
        return shell("Create Task", "Assign the next move to a person and a deadline.",
                     body, user)

    @app.route("/team/ops/task/new", methods=["POST"])
    @login_required
    def tops_task_create():
        user = current_user()
        guard = need_manager(user)
        if guard:
            return guard
        aid = request.form.get("assignee_id")
        assignee_id = int(aid) if (aid or "").isdigit() else None
        due = T.local_dt_to_utc(request.form.get("due_at"),
                                T.get_user(assignee_id) or user)
        title = (request.form.get("title") or "").strip()
        if not title:
            return back(err="A title is required.", to="/team/ops/task/new")
        t = T.create_task(
            title, assignee_id=assignee_id, assigned_by_id=user["user_id"],
            task_type=request.form.get("task_type"),
            priority=request.form.get("priority"),
            description=(request.form.get("description") or "").strip()[:4000],
            due_at=due,
            related_opportunity_id=(request.form.get("related_opportunity_id") or "").strip()[:80],
            related_keyword=(request.form.get("related_keyword") or "").strip()[:120],
            related_listing_id=(request.form.get("related_listing_id") or "").strip()[:80],
            related_store=(request.form.get("related_store") or "").strip()[:80],
            expected_output=(request.form.get("expected_output") or "").strip()[:400],
            drive_folder=safe_url(request.form.get("drive_folder")),
            internal_notes=(request.form.get("internal_notes") or "").strip()[:2000],
            actor=user)
        log("TASK_CREATE", module="team_ops", entity_type="team_task",
            entity_id=t["id"], summary=t["title"])
        return redirect("/team/ops/task/" + str(t["id"]) + "?ok=Task+created")

    @app.route("/team/ops/task/<int:tid>")
    @login_required
    def tops_task_detail(tid):
        user = current_user()
        T.init_schema()
        t = T.get_task(tid)
        if not t or not T.can_see_task(user, t):
            return back(err="Task not found or not visible to you.",
                        to="/team/ops/board")
        names = T.users_by_id()
        mgr = T.is_manager(user)
        is_assignee = t.get("assignee_id") == user["user_id"]
        deleted = bool(t.get("deleted_at"))

        # --- checklist ---
        ck = ""
        for i in t["checklist"]:
            checked = " checked" if i.get("is_checked") else ""
            can_tick = (mgr or is_assignee) and not deleted
            stamp = ""
            if i.get("checked_at"):
                stamp = ('<span class="when" style="color:var(--ink-faint);'
                         'font-size:.7rem">' + esc(who(i.get("checked_by"), names))
                         + " · " + esc(T.to_local(i.get("checked_at"), user)) + '</span>')
            ck += ('<form class="ck" method="post" action="/team/ops/task/' + str(tid)
                   + '/checklist"><input type="hidden" name="item_id" value="'
                   + esc(i.get("id")) + '">'
                   '<input type="hidden" name="checked" value="'
                   + ("0" if i.get("is_checked") else "1") + '">'
                   '<input type="checkbox"' + checked
                   + (' onchange="this.form.submit()"' if can_tick else " disabled")
                   + '><span>' + esc(i.get("label") or i.get("id")) + '</span>'
                   + ('<span class="req">required</span>' if i.get("required") else "")
                   + stamp + '</form>')
        missing = T.missing_required(t)
        ckpanel = ('<div class="panel"><h2>QA checklist ('
                   + str(t.get("checklist_completed_count") or 0) + '/'
                   + str(t.get("checklist_total_count") or 0) + ')</h2>'
                   + (ck or '<p class="none">No checklist for this task type.</p>')
                   + ('<p style="color:var(--stop);font-size:.8rem;margin:8px 0 0">'
                      'Required items still open: ' + esc(", ".join(missing)) + '</p>'
                      if missing else "") + '</div>')

        # --- staff actions ---
        acts = ""
        if not deleted:
            if is_assignee and t["status"] == "TODO":
                acts += status_btn(tid, "IN_PROGRESS", "▶ Start task", "primary")
            if is_assignee and t["status"] == "FIX_REQUESTED":
                acts += status_btn(tid, "IN_PROGRESS", "▶ Resume fix", "primary")
            if is_assignee and t["status"] == "IN_PROGRESS":
                acts += ('<form method="post" action="/team/ops/task/' + str(tid)
                         + '/submit" class="fstack panel">'
                         '<h2>Submit for review</h2>'
                         '<label>Link (listing / Drive / Canva / Figma)'
                         '<input name="link" placeholder="https://..."></label>'
                         '<label>Google Drive folder<input name="drive_folder" '
                         'value="' + esc(t.get("drive_folder") or "") + '"></label>'
                         '<label>Note for the reviewer<textarea name="note" rows="2">'
                         '</textarea></label>'
                         '<button class="tbtn primary" type="submit">'
                         'Submit for review</button></form>')
            if is_assignee and t["status"] in ("TODO", "IN_PROGRESS"):
                acts += ('<form method="post" action="/team/ops/task/' + str(tid)
                         + '/comment"><input type="hidden" name="blocked" value="1">'
                         '<input type="hidden" name="text" value="🚧 Blocked / need help">'
                         '<button class="tbtn" type="submit">🚧 Need help</button></form>')
            if mgr and t["status"] == "REVIEW":
                acts += status_btn(tid, "DONE", "✅ Approve Done", "primary")
                acts += ('<a class="tbtn" href="#fix">✏️ Request fix</a>')
            if mgr and t["status"] not in ("DONE", "CANCELLED"):
                acts += status_btn(tid, "CANCELLED", "Cancel task", "danger")
            # Task Board tracks the approval workflow; Daily Reports track volume.
            # This copies the task's details into a report the person confirms.
            if is_assignee or mgr:
                acts += ('<a class="tbtn" href="/team/ops/reports?view=mine&amp;'
                         'from_task=' + str(tid) + '">📝 Add to Daily Report</a>')

        # --- fix form ---
        fixform = ""
        if mgr and t["status"] == "REVIEW" and not deleted:
            fixform = ('<div class="panel" id="fix"><h2>Request fix</h2>'
                       '<form method="post" action="/team/ops/task/' + str(tid)
                       + '/fix" class="fstack">'
                       '<label>Fix reason<input name="reason" required></label>'
                       '<label>Required changes<textarea name="required_changes" '
                       'rows="2"></textarea></label>'
                       '<label>New deadline (blank = tomorrow 17:00)'
                       '<input type="datetime-local" name="due_at"></label>'
                       '<button class="tbtn primary" type="submit">'
                       'Send back for fix</button></form></div>')

        # --- edit panel ---
        editpanel = ""
        if mgr and not deleted:
            editpanel = ('<details class="panel"><summary style="cursor:pointer;'
                         'font-weight:700">✏️ Edit task</summary>'
                         '<form method="post" action="/team/ops/task/' + str(tid)
                         + '/edit" style="margin-top:11px">' + task_form(user, task=t)
                         + '<div class="tops-actions" style="margin-top:11px">'
                         '<button class="tbtn primary" type="submit">Save</button>'
                         '</div></form>'
                         '<form method="post" action="/team/ops/task/' + str(tid)
                         + '/delete" style="margin-top:11px;display:flex;gap:8px">'
                         '<input name="reason" placeholder="Delete reason" required '
                         'style="flex:1;padding:7px 9px;border:1px solid '
                         'var(--line-strong);border-radius:7px;background:var(--paper);'
                         'color:var(--ink)">'
                         '<button class="tbtn danger" type="submit" '
                         'onclick="return confirm(\'Soft-delete this task?\')">'
                         'Delete</button></form></details>')

        # --- comments + activity ---
        comments = ""
        for c in T.task_comments(tid, 60):
            tag = " · system" if c.get("is_system_event") else ""
            comments += ('<li><span class="who">' + esc(who(c.get("user_id"), names))
                         + '</span> <span class="when">'
                         + esc(T.to_local(c.get("created_at"), user)) + esc(tag)
                         + '</span><div>' + esc(c.get("comment_text") or "")
                         + '</div></li>')
        acts_log = ""
        for a in T.task_activity(tid, 60):
            old, new = a.get("old_value"), a.get("new_value")
            arrow = (esc(old) + " → " + esc(new)) if old and new else esc(new or "")
            acts_log += ('<li><span class="who">' + esc(who(a.get("actor_id"), names))
                         + '</span> ' + esc(a["action"]) + ' ' + arrow
                         + ' <span class="when">'
                         + esc(T.to_local(a.get("created_at"), user)) + '</span></li>')

        links = ""
        for l in (t.get("links") or []):
            u = safe_url(l.get("url"))
            if u:
                links += ('<li><a href="' + esc(u) + '" target="_blank" rel="noopener">'
                          + esc(u[:70]) + '</a></li>')
        if t.get("drive_folder"):
            u = safe_url(t.get("drive_folder"))
            if u:
                links += ('<li>📁 <a href="' + esc(u) + '" target="_blank" '
                          'rel="noopener">' + esc(u[:70]) + '</a></li>')

        facts = [("Status", T.STATUS_LABELS.get(t["status"], t["status"])),
                 ("Type", T.TASK_TYPE_LABELS.get(t.get("task_type"), "—")),
                 ("Priority", t.get("priority")),
                 ("Assignee", who(t.get("assignee_id"), names)),
                 ("Assigned by", who(t.get("assigned_by_id"), names)),
                 ("Reviewer", who(t.get("reviewer_manager_id"), names)),
                 ("Due", T.to_local(t.get("due_at"), user, "%d %b %Y %H:%M") or "—"),
                 ("Completed", T.to_local(t.get("completed_at"), user) or "—"),
                 ("Keyword", t.get("related_keyword") or "—"),
                 ("Store", t.get("related_store") or "—"),
                 ("Opportunity", t.get("related_opportunity_id") or "—"),
                 ("Listing", t.get("related_listing_id") or "—"),
                 ("Expected output", t.get("expected_output") or "—")]
        factrows = "".join('<tr><th>' + esc(k) + '</th><td>' + esc(v) + '</td></tr>'
                           for k, v in facts)
        delnote = ""
        if deleted:
            delnote = ('<div class="msg err">Soft-deleted '
                       + esc(T.to_local(t.get("deleted_at"), user)) + ' by '
                       + esc(who(t.get("deleted_by_id"), names)) + ' — reason: '
                       + esc(t.get("delete_reason") or "—")
                       + '. The row is kept for audit and KPI history.</div>')
        body = (delnote
                + '<div class="tops-actions" style="margin-bottom:14px">' + acts + '</div>'
                + '<div class="cards" style="grid-template-columns:1fr 1fr">'
                '<div><div class="panel"><h2>Task</h2>'
                '<table class="grid">' + factrows + '</table>'
                + ('<p style="margin:10px 0 0;font-size:.84rem">'
                   + esc(t.get("description") or "") + '</p>'
                   if t.get("description") else "")
                + ('<h3 style="font-size:.8rem;margin:12px 0 4px">Links</h3><ul>'
                   + links + '</ul>' if links else "")
                + '</div>' + ckpanel + fixform + editpanel + '</div>'
                '<div><div class="panel"><h2>Comments</h2>'
                '<form method="post" action="/team/ops/task/' + str(tid)
                + '/comment" class="fstack">'
                '<label>Add a comment <span style="font-weight:400;text-transform:none;'
                'color:var(--ink-faint)">@Owner @Manager @Assignee work</span>'
                '<textarea name="text" rows="2" required></textarea></label>'
                '<button class="tbtn primary" type="submit">Comment</button></form>'
                '<ul class="tl" style="margin-top:11px">' + comments + '</ul></div>'
                '<div class="panel"><h2>Activity</h2><ul class="tl">' + acts_log
                + '</ul></div></div></div>')
        return shell("Task #" + str(tid), esc((t.get("title") or "")[:90]), body, user)

    def status_btn(tid, status, label, cls=""):
        return ('<form method="post" action="/team/ops/task/' + str(tid) + '/status">'
                '<input type="hidden" name="status" value="' + status + '">'
                '<button class="tbtn ' + cls + '" type="submit">' + label
                + '</button></form>')

    @app.route("/team/ops/task/<int:tid>/status", methods=["POST"])
    @login_required
    def tops_task_status(tid):
        user = current_user()
        t, err = T.set_status(tid, request.form.get("status"), user,
                              note=(request.form.get("note") or "").strip()[:1000])
        if err:
            return back(err=err, to="/team/ops/task/" + str(tid))
        log("TASK_STATUS_CHANGE", module="team_ops", entity_type="team_task",
            entity_id=tid, summary=request.form.get("status"))
        return back(msg="Status updated", to="/team/ops/task/" + str(tid))

    @app.route("/team/ops/task/<int:tid>/submit", methods=["POST"])
    @login_required
    def tops_task_submit(tid):
        user = current_user()
        t, err = T.submit_for_review(
            tid, user, note=(request.form.get("note") or "").strip()[:2000],
            link=safe_url(request.form.get("link")),
            drive_folder=safe_url(request.form.get("drive_folder")))
        if err:
            return back(err=err, to="/team/ops/task/" + str(tid))
        log("TASK_STATUS_CHANGE", module="team_ops", entity_type="team_task",
            entity_id=tid, summary="submitted for review")
        return back(msg="Submitted for review", to="/team/ops/task/" + str(tid))

    @app.route("/team/ops/task/<int:tid>/fix", methods=["POST"])
    @login_required
    def tops_task_fix(tid):
        user = current_user()
        due = T.local_dt_to_utc(request.form.get("due_at"), user)
        t, err = T.request_fix(
            tid, user, (request.form.get("reason") or "").strip()[:500],
            (request.form.get("required_changes") or "").strip()[:2000], due)
        if err:
            return back(err=err, to="/team/ops/task/" + str(tid))
        log("TASK_REVIEW_REJECT", module="team_ops", entity_type="team_task",
            entity_id=tid, summary="fix requested")
        return back(msg="Fix requested", to="/team/ops/task/" + str(tid))

    @app.route("/team/ops/task/<int:tid>/checklist", methods=["POST"])
    @login_required
    def tops_task_checklist(tid):
        user = current_user()
        _t, err = T.set_checklist_item(tid, request.form.get("item_id"),
                                       request.form.get("checked") == "1", user)
        return back(err=err or None, to="/team/ops/task/" + str(tid))

    @app.route("/team/ops/task/<int:tid>/comment", methods=["POST"])
    @login_required
    def tops_task_comment(tid):
        user = current_user()
        t = T.get_task(tid)
        if not t or not T.can_see_task(user, t):
            return back(err="Not your task.", to="/team/ops/board")
        text = (request.form.get("text") or "").strip()[:4000]
        if text:
            T.add_comment(tid, user["user_id"], text)
        return back(msg="Comment added", to="/team/ops/task/" + str(tid))

    @app.route("/team/ops/task/<int:tid>/edit", methods=["POST"])
    @login_required
    def tops_task_edit(tid):
        user = current_user()
        t = T.get_task(tid)
        if not t or not T.can_edit_task(user, t):
            return back(err="Manager or Owner only.", to="/team/ops/task/" + str(tid))
        aid = request.form.get("assignee_id")
        assignee_id = int(aid) if (aid or "").isdigit() else None
        T.update_task(
            tid, actor=user, title=(request.form.get("title") or "").strip()[:200],
            description=(request.form.get("description") or "").strip()[:4000],
            task_type=request.form.get("task_type"),
            priority=request.form.get("priority"), assignee_id=assignee_id,
            due_at=T.local_dt_to_utc(request.form.get("due_at"),
                                     T.get_user(assignee_id) or user),
            related_keyword=(request.form.get("related_keyword") or "").strip()[:120],
            related_store=(request.form.get("related_store") or "").strip()[:80],
            related_opportunity_id=(request.form.get("related_opportunity_id") or "").strip()[:80],
            related_listing_id=(request.form.get("related_listing_id") or "").strip()[:80],
            drive_folder=safe_url(request.form.get("drive_folder")),
            expected_output=(request.form.get("expected_output") or "").strip()[:400],
            internal_notes=(request.form.get("internal_notes") or "").strip()[:2000])
        log("TASK_UPDATE", module="team_ops", entity_type="team_task", entity_id=tid,
            summary="edited")
        return back(msg="Task updated", to="/team/ops/task/" + str(tid))

    @app.route("/team/ops/task/<int:tid>/delete", methods=["POST"])
    @login_required
    def tops_task_delete(tid):
        user = current_user()
        ok, err = T.soft_delete_task(tid, user,
                                     (request.form.get("reason") or "").strip()[:400])
        if not ok:
            return back(err=err, to="/team/ops/task/" + str(tid))
        log("TASK_UPDATE", module="team_ops", entity_type="team_task", entity_id=tid,
            summary="soft deleted")
        return back(msg="Task soft-deleted (row kept for audit)", to="/team/ops/board")

    # ======================================================= DAILY REPORTS ==
    # One module, several obvious names. /team/ops/logs stays as the original
    # alias; proactive_work_logs is still the table underneath.
    @app.route("/team/ops/reports")
    @app.route("/team/ops/daily-reports")
    @app.route("/team/ops/working-log")
    @app.route("/team/ops/logs")
    @login_required
    def tops_logs():
        """Daily Reports — where staff report the Etsy work they did today.

        Staff get a simple "My Daily Report" page; Owner/Manager get the
        team-wide grid. Same table underneath (proactive_work_logs).
        """
        user = current_user()
        T.init_schema()
        view = (request.args.get("view") or "").strip()
        team_view = T.is_manager(user) and view != "mine"
        return (_reports_team(user) if team_view else _reports_mine(user))

    def report_form(user, prefill=None, task=None):
        """The Add Today Report form. Work type defaults to the person's role."""
        p = prefill or {}
        target = T.get_user(p.get("staff_id")) if p.get("staff_id") else user
        wt = p.get("work_type") or T.default_work_type(target)
        stores = T.store_options()
        store_field = (
            '<label>Account / Store<select name="account_store">'
            + opts(stores, p.get("account_store") or user.get("default_store"),
                   "— choose —") + '</select></label>'
            if stores else
            '<label>Account / Store<input name="account_store" value="'
            + esc(p.get("account_store") or user.get("default_store") or "")
            + '" placeholder="Shop name"></label>')
        ptypes = T.product_type_options()
        ptype_field = (
            '<label>Product Type<select name="product_type">'
            + opts(ptypes, p.get("product_type"), "— choose —") + '</select></label>'
            if ptypes else
            '<label>Product Type<input name="product_type" value="'
            + esc(p.get("product_type") or "") + '" placeholder="Tumbler, hoodie, '
            'bag..."></label>')
        return (
            '<div class="fgrid">'
            '<label>Date<input type="date" name="date" value="'
            + esc(p.get("date") or T.local_today(user)) + '"></label>'
            + ('<label>Staff<select name="staff_id">'
               + user_opts(user, p.get("staff_id") or user["user_id"], None)
               + '</select></label>' if T.is_manager(user) else
               '<label>Staff<input value="' + esc(user.get("display_name") or "")
               + '" disabled></label>')
            + '<label>Role<input value="' + esc(T.team_role(target))
            + '" disabled></label>'
            + store_field
            + '<label>Work Type<select name="work_type">'
            + opts(T.work_type_options(), wt) + '</select></label>'
            '<label>Seed phrase / Keyword<input name="seed_phrase_keyword" value="'
            + esc(p.get("seed_phrase_keyword") or "") + '"></label>'
            + ptype_field
            + '<label>Google Drive Folder<input name="link_folder_google_drive" '
            'value="' + esc(p.get("link_folder_google_drive") or "")
            + '" placeholder="https://drive.google.com/..."></label>'
            '<label>Listing URL <span style="font-weight:400;text-transform:none;'
            'color:var(--ink-faint)">optional · paste it yourself</span>'
            '<input name="listing_url" value="' + esc(p.get("listing_url") or "")
            + '" placeholder="https://www.etsy.com/listing/..."></label>'
            '<label>Designs completed<input type="number" min="0" name="design_count" '
            'value="' + esc(p.get("design_count") or 0) + '"></label>'
            '<label>Listings created<input type="number" min="0" '
            'name="listing_count" value="' + esc(p.get("listing_count") or 0)
            + '"></label>'
            '<label>Status<select name="status">'
            + opts(T.LOG_STATUSES, p.get("status")) + '</select></label>'
            '<label class="fwide">Notes<textarea name="notes" rows="2">'
            + esc(p.get("notes") or "") + '</textarea></label>'
            + ('<input type="hidden" name="task_id" value="'
               + str(p.get("task_id")) + '">' if p.get("task_id") else "")
            + '</div>')

    def _reports_help():
        return ('<p style="font-size:.81rem;color:var(--ink-soft);margin:0 0 12px">'
                'Staff use this page to report daily Etsy work: designs completed, '
                'listings created, keywords researched, and Drive folders.</p>')

    # Cell rendering shared with AUTOSAVE_JS's render() — keep the two in step so
    # a cell looks the same after an inline save as it did on page load.
    URL_LABELS = {"link_folder_google_drive": "📁 Drive folder",
                  "listing_url": "🔗 Listing"}

    def status_badge(v):
        v = (v or "").strip()
        if not v:
            return ""
        return ('<span class="stx s-'
                + "".join(c if c.isalnum() else "-" for c in v.lower())
                + '">' + esc(v) + '</span>')

    def _cell_html(field, val, mode, allowed):
        if mode == "status":
            return status_badge(val)
        if mode == "url":
            pen = ('<button class="pen" type="button" data-edit '
                   'title="Edit link">✎</button>') if allowed else ""
            href = safe_url(val) if val else ""
            if href:
                return ('<a class="ulink" href="' + esc(href) + '" target="_blank" '
                        'rel="noopener" title="' + esc(href) + '">'
                        + URL_LABELS.get(field, "🔗 Open") + ' ↗</a>' + pen)
            return ('<span class="uempty">'
                    + (esc(val[:48]) if val else "＋ add link") + '</span>' + pen)
        return esc(val[:48])

    def review_badge(r, by=""):
        """Manager verdict: Approved / Needs improvement / Rejected / Pending."""
        note = esc(r.get("manager_note") or "")
        if r.get("verified_by_manager_id"):
            return ('<span class="rv approved" title="' + note + '">✅ Approved'
                    + (' · ' + esc(by) if by else "") + '</span>')
        state = (r.get("review_state") or "").lower()
        if state == "rejected":
            return '<span class="rv rejected" title="' + note + '">⛔ Rejected</span>'
        if state == "improve":
            return ('<span class="rv improve" title="' + note
                    + '">✏️ Needs improvement</span>')
        return '<span class="rv pending">⏳ Pending review</span>'

    def _report_row_badges(r):
        out = review_badge(r)
        if r.get("edited_after_lock_by"):
            out += ('<span class="tag d-soon" title="'
                    + esc(r.get("edited_after_lock_reason") or "")
                    + '">Edited after lock</span>')
        if T.log_locked(r):
            out += '<span class="tag">🔒 locked</span>'
        if r.get("manager_note"):
            out += ('<span class="tag d-fix" title="'
                    + esc(r.get("manager_note")) + '">Manager note</span>')
        return out

    # ---------------------------------------------------- staff-first view ----
    def _reports_mine(user):
        now = T.utcnow()
        today = T.local_today(user)
        prefill = {}
        task = None
        tid = (request.args.get("from_task") or "").strip()
        if tid.isdigit():
            task = T.get_task(int(tid))
            if task and T.can_see_task(user, task):
                prefill = T.report_prefill_from_task(task)
            else:
                task = None
        mine = T.list_logs(user=user, staff_id=user["user_id"], limit=200)
        today_rows = [r for r in mine if (r.get("date") or "")[:10] == today]
        d_today = sum(T._int(r.get("design_count")) for r in today_rows)
        l_today = sum(T._int(r.get("listing_count")) for r in today_rows)
        pending = [r for r in mine if (r.get("status") or "")
                   in ("Waiting Review", "Blocked")]
        tiles = [("My designs today", d_today, ""),
                 ("My listings today", l_today, ""),
                 ("My reports today", len(today_rows),
                  " bad" if not today_rows else " good"),
                 ("Waiting review / blocked", len(pending),
                  " bad" if pending else "")]
        kpis = '<div class="kpis">' + "".join(
            '<div class="kpi' + c + '"><div class="n">' + esc(n) + '</div>'
            '<div class="l">' + esc(l) + '</div></div>' for l, n, c in tiles) + '</div>'
        warn = ""
        if T.missing_report_warning(user, now):
            warn = ('<div class="hbanner fail"><b>Missing report today</b>'
                    '<span>You have not submitted today\'s Etsy work report.</span>'
                    '</div>')
        elif not today_rows:
            warn = ('<div class="hbanner warn"><b>No report yet today</b>'
                    '<span>Add today\'s designs, listings or keyword work before you '
                    'finish.</span></div>')
        fromtask = ""
        if task:
            fromtask = ('<div class="msg ok">Pre-filled from task #' + str(task["id"])
                        + ' — ' + esc((task.get("title") or "")[:70])
                        + '. Check the numbers, then save.</div>')
        form = ('<details class="panel" ' + ("open" if (not today_rows or prefill)
                                             else "") + '>'
                '<summary style="cursor:pointer;font-weight:700">'
                '➕ Add Today Report</summary>'
                '<form method="post" action="/team/ops/reports/new" '
                'style="margin-top:11px">' + report_form(user, prefill, task)
                + '<button class="tbtn primary" type="submit" style="margin-top:11px">'
                'Save report</button></form></details>')
        rows = ""
        for r in mine[:60]:
            allowed, needs_reason, why = T.can_edit_log(user, r)
            drive = safe_url(r.get("link_folder_google_drive"))
            listing = safe_url(r.get("listing_url"))
            links = ""
            if drive:
                links += ('<a class="tbtn sm" href="' + esc(drive) + '" '
                          'target="_blank" rel="noopener">📁 Drive</a>')
            if listing:
                links += ('<a class="tbtn sm" href="' + esc(listing) + '" '
                          'target="_blank" rel="noopener">🔗 Listing</a>')
            edit = ('<a class="tbtn sm" href="/team/ops/reports?view=team&amp;staff='
                    + str(user["user_id"]) + '">Edit in grid</a>' if allowed
                    else '<span class="tag" title="' + esc(why) + '">read-only</span>')
            rows += ('<tr><td>' + esc((r.get("date") or "")[:10]) + '</td>'
                     '<td>' + esc(r.get("work_type") or "") + '</td>'
                     '<td>' + esc(r.get("account_store") or "—") + '</td>'
                     '<td>' + esc(r.get("seed_phrase_keyword") or "—") + '</td>'
                     '<td>' + esc(T._int(r.get("design_count"))) + '</td>'
                     '<td>' + esc(T._int(r.get("listing_count"))) + '</td>'
                     '<td>' + status_badge(r.get("status")) + '</td>'
                     '<td>' + links + '</td>'
                     '<td>' + _report_row_badges(r) + '</td>'
                     '<td>' + edit + '</td></tr>')
        table = ('<div class="gwrap"><table class="grid"><thead><tr><th>Date</th>'
                 '<th>Work Type</th><th>Account / Store</th><th>Keyword</th>'
                 '<th>Designs completed</th><th>Listings created</th><th>Status</th>'
                 '<th>Links</th><th>State</th><th></th></tr></thead><tbody>'
                 + (rows or '<tr><td colspan="10" style="color:var(--ink-faint)">'
                    'No reports yet — use Add Today Report above.</td></tr>')
                 + '</tbody></table></div>')
        notes = [r for r in mine if r.get("manager_note")][:5]
        mnotes = ""
        for r in notes:
            mnotes += ('<li><b>' + esc((r.get("date") or "")[:10]) + '</b> — '
                       + esc(r.get("manager_note")) + '</li>')
        mpanel = ('<div class="panel"><h2>Manager notes</h2><ul class="tl">'
                  + mnotes + '</ul></div>') if mnotes else ""
        actions = ('<a class="tbtn" href="/team/ops/reports?view=team">Team view</a>'
                   if T.is_manager(user) else "")
        return shell("My Daily Report", "Report your Etsy work.",
                     _reports_help() + warn + fromtask + kpis + form
                     + '<div class="tsec">My recent reports</div>' + table + mpanel,
                     user, actions)

    # ------------------------------------------------ owner / manager grid ----
    def _reports_team(user):
        f = {k: (request.args.get(k) or "").strip()
             for k in ("staff", "store", "status", "work_type", "role", "from", "to",
                       "q")}
        # "Staff missing report today" on Team Home lands here: narrow the grid to
        # today so who-filed vs who-didn't is obvious side by side.
        only_missing = request.args.get("missing") == "1"
        if only_missing and not (f["from"] or f["to"]):
            f["from"] = f["to"] = T.local_today(user)
        rows = T.list_logs(
            user=user, staff_id=int(f["staff"]) if f["staff"].isdigit() else None,
            store=f["store"] or None, status=f["status"] or None,
            work_type=f["work_type"] or None, role=f["role"] or None,
            date_from=f["from"] or None, date_to=f["to"] or None,
            search=f["q"] or None)
        names = T.users_by_id(include_inactive=True)
        s = T.daily_report_summary(user, date_from=f["from"] or None,
                                   date_to=f["to"] or None)
        tiles = [("Reports today", s["reports_today"], ""),
                 ("Submitted Designs", s["designs_submitted"], ""),
                 ("Verified Designs", s["designs_verified"], " good"),
                 ("Submitted Listings", s["listings_submitted"], ""),
                 ("Verified Listings", s["listings_verified"], " good"),
                 ("Missing report today", s["missing_today_n"],
                  " bad" if s["missing_today_n"] else ""),
                 ("Blocked reports", s["blocked"], " bad" if s["blocked"] else ""),
                 ("Edited after lock", s["edited_after_lock"],
                  " bad" if s["edited_after_lock"] else ""),
                 ("Avg listings / seller", s["avg_listings_per_seller"], ""),
                 ("Avg designs / designer", s["avg_designs_per_designer"], "")]
        kpis = '<div class="kpis">' + "".join(
            '<div class="kpi' + c + '"><div class="n">' + esc(n) + '</div>'
            '<div class="l">' + esc(l) + '</div></div>' for l, n, c in tiles) + '</div>'
        missing = ""
        for p in s["missing_today"]:
            missing += ('<a class="tbtn sm" href="/team/ops/reports?view=team&amp;'
                        'staff=' + str(p["user_id"]) + '">'
                        + esc(p.get("display_name") or "?") + '</a>')
        if missing:
            missing = ('<div class="hbanner ' + ("fail" if only_missing else "warn")
                       + '"><b>Missing report today (' + str(s["missing_today_n"])
                       + ')</b><span>' + missing + '</span></div>')
        elif only_missing:
            missing = ('<div class="hbanner ok"><b>Everyone filed today</b>'
                       '<span>No missing reports.</span></div>')
        stores = T.store_options() or sorted(
            {r.get("account_store") for r in rows if r.get("account_store")})
        cells = [("date", "Date", "date", None),
                 ("account_store", "Account / Store", "text", stores or None),
                 ("work_type", "Work Type", "text", T.work_type_options()),
                 ("seed_phrase_keyword", "Seed phrase / Keyword", "text", None),
                 ("product_type", "Product Type", "text",
                  T.product_type_options() or None),
                 ("link_folder_google_drive", "Google Drive Folder", "url", None),
                 ("listing_url", "Listing URL", "url", None),
                 ("design_count", "Design Count", "number", None),
                 ("listing_count", "Listing Count", "number", None),
                 ("status", "Status", "text", T.LOG_STATUSES),
                 ("notes", "Notes", "text", None)]
        head = ('<tr><th>Staff Name</th><th>Role</th>'
                + "".join('<th>' + esc(lbl) + '</th>' for _f, lbl, _t, _o in cells)
                + '<th>Last Updated</th><th>Edited After Lock</th><th>Review</th>'
                '<th>Actions</th></tr>')
        n_cols = 2 + len(cells) + 4
        trs = ""
        for r in rows:
            allowed, needs_reason, why = T.can_edit_log(user, r)
            tds = ""
            for field, _lbl, ftype, options in cells:
                val = "" if r.get(field) is None else str(r.get(field))
                mode = ("url" if ftype == "url"
                        else "status" if field == "status" else "")
                attrs = (' data-field="' + field + '" data-value="' + esc(val)
                         + '" data-type="' + ftype + '"'
                         + (' data-render="' + mode + '"' if mode else ""))
                if options:
                    attrs += ' data-options="' + esc("|".join(options)) + '"'
                tds += ('<td class="' + ("ed" if allowed else "locked") + '"'
                        + (attrs if allowed else "")
                        + ' title="' + esc(val if allowed else why) + '">'
                        + _cell_html(field, val, mode, allowed) + '</td>')
            lock = ('<span class="tag d-soon" title="'
                    + esc(r.get("edited_after_lock_reason") or "") + '">Yes</span>'
                    if r.get("edited_after_lock_by") else '<span class="tag">No</span>')
            ver = review_badge(r, who(r.get("verified_by_manager_id"), names)
                               if r.get("verified_by_manager_id") else "")
            acts = '<div class="acts">'
            if not r.get("verified_by_manager_id"):
                acts += ('<button class="tbtn sm ok" type="submit" form="vf'
                         + str(r["id"]) + '" title="Approve — signs this report off '
                         'so it counts as verified">✅ Approve</button>')
            acts += ('<button class="tbtn sm imp" type="button" '
                     'title="Improve — ask the staff member to fix it; they get '
                     'notified" onclick="topsNote(' + str(r["id"])
                     + ',&quot;clarify&quot;)">✏️ Improve</button>'
                     '<button class="tbtn sm danger" type="button" '
                     'title="Reject — marks the report Blocked with your reason" '
                     'onclick="topsNote(' + str(r["id"]) + ',&quot;blocked&quot;)">'
                     '⛔ Reject</button>'
                     '<button class="tbtn sm ic" type="button" '
                     'title="Add a manager note (no verdict)" '
                     'onclick="topsNote(' + str(r["id"]) + ',&quot;note&quot;)">'
                     '📝</button>')
            if allowed:
                acts += ('<button class="tbtn sm ic" type="submit" form="df'
                         + str(r["id"]) + '" title="Soft-delete this report" '
                         'onclick="return confirm('
                         '&quot;Soft-delete this report?&quot;)">🗑</button>')
            acts += '</div>'
            mnote = ('<div class="cprev" title="' + esc(r.get("manager_note") or "")
                     + '">📝 ' + esc((r.get("manager_note") or "")[:40]) + '</div>'
                     if r.get("manager_note") else "")
            trs += ('<tr data-id="' + str(r["id"]) + '" data-locked="'
                    + ("1" if needs_reason else "0") + '">'
                    '<td><b>' + esc(who(r.get("staff_id"), names)) + '</b>' + mnote
                    + '</td><td>' + esc(r.get("role") or "") + '</td>' + tds
                    + '<td>' + esc(T.to_local(r.get("updated_at"), user)) + '</td>'
                    '<td>' + lock + '</td><td>' + ver + '</td>'
                    '<td>' + acts + '</td></tr>')
        forms = ""
        for r in rows:
            forms += ('<form id="vf' + str(r["id"]) + '" method="post" '
                      'action="/team/ops/reports/' + str(r["id"]) + '/verify"></form>'
                      '<form id="df' + str(r["id"]) + '" method="post" '
                      'action="/team/ops/reports/' + str(r["id"]) + '/delete">'
                      '<input type="hidden" name="reason" value="removed by '
                      + esc(user.get("display_name") or "") + '"></form>')
        grid = ('<div class="gwrap"><table class="grid"><thead>' + head
                + '</thead><tbody>' + (trs or '<tr><td colspan="' + str(n_cols)
                + '" style="color:var(--ink-faint)">No reports match these filters.'
                '</td></tr>') + '</tbody></table></div>' + forms)
        notef = ('<form id="tops-note-form" method="post" action="" '
                 'style="display:none"><input type="hidden" name="action" '
                 'value=""><input type="hidden" name="note" value=""></form>')
        filt = ('<form class="filters" method="get">'
                '<input type="hidden" name="view" value="team">'
                '<label>Search keyword<input name="q" value="' + esc(f["q"])
                + '" placeholder="keyword / store / notes"></label>'
                '<label>Staff<select name="staff">'
                + user_opts(user, f["staff"], "Everyone") + '</select></label>'
                '<label>Role<select name="role">'
                + opts(["SELLER", "DESIGNER", "MANAGER", "OWNER"], f["role"], "Any")
                + '</select></label>'
                '<label>Account / Store<select name="store">'
                + opts(stores, f["store"], "All") + '</select></label>'
                '<label>Work Type<select name="work_type">'
                + opts(T.work_type_options(), f["work_type"], "Any") + '</select></label>'
                '<label>Status<select name="status">'
                + opts(T.LOG_STATUSES, f["status"], "Any") + '</select></label>'
                '<label>From<input type="date" name="from" value="' + esc(f["from"])
                + '"></label>'
                '<label>To<input type="date" name="to" value="' + esc(f["to"])
                + '"></label>'
                '<button class="tbtn primary" type="submit">Filter</button>'
                '<a class="tbtn" href="/team/ops/reports?view=team">Reset</a></form>')
        note = ('<p style="font-size:.79rem;color:var(--ink-soft);margin:0 0 12px">'
                'Double-click a cell to edit; it saves on blur. Staff may edit only '
                'Today and Yesterday — rows lock 48 hours after they are created. A '
                'Manager/Owner edit after the lock records a reason in the audit '
                'trail and flags the row until it is verified. Review each row with '
                '<b>✅ Approve</b> (signs it off — it now counts as verified), '
                '<b>✏️ Improve</b> (asks the staff member to fix it) or '
                '<b>⛔ Reject</b> (marks it Blocked with your reason).</p>')
        actions = ('<a class="tbtn primary" href="/team/ops/reports?view=mine">'
                   '➕ Add My Report</a>'
                   '<a class="tbtn" href="/team/ops/export/logs.csv?'
                   + urlencode({k: v for k, v in f.items() if v}) + '">⬇ Export CSV</a>'
                   '<a class="tbtn" href="/team/ops/reports/audit">🧾 Audit trail</a>')
        return shell("Team Daily Reports",
                     str(len(rows)) + " report(s) in scope · what each person "
                     "actually shipped today.",
                     _reports_help() + missing + kpis + note + filt + grid + notef,
                     user, actions)

    @app.route("/team/ops/reports/new", methods=["POST"])
    @app.route("/team/ops/logs/new", methods=["POST"])
    @login_required
    def tops_log_new():
        user = current_user()
        sid = request.form.get("staff_id")
        back_to = "/team/ops/reports"
        row, err = T.create_log(
            user, date=(request.form.get("date") or "").strip()[:10],
            staff_id=int(sid) if (sid or "").isdigit() else None,
            account_store=(request.form.get("account_store") or "").strip()[:80],
            work_type=request.form.get("work_type"),
            seed_phrase_keyword=(request.form.get("seed_phrase_keyword") or "").strip()[:160],
            product_type=(request.form.get("product_type") or "").strip()[:80],
            link_folder_google_drive=safe_url(request.form.get("link_folder_google_drive")),
            listing_url=safe_url(request.form.get("listing_url")),
            design_count=request.form.get("design_count"),
            listing_count=request.form.get("listing_count"),
            status=request.form.get("status"),
            notes=(request.form.get("notes") or "").strip()[:2000],
            metadata=({"from_task": int(request.form["task_id"])}
                      if (request.form.get("task_id") or "").isdigit() else None))
        if err:
            return back(err=err, to=back_to)
        log("FEEDBACK_ADD", module="team_ops", entity_type="work_log",
            entity_id=row["id"], summary="daily report")
        return back(msg="Report saved", to=back_to)

    @app.route("/team/ops/reports/<int:lid>/action", methods=["POST"])
    @login_required
    def tops_report_action(lid):
        """Manager row actions: request clarification / mark blocked / add note."""
        user = current_user()
        _r, err = T.manager_action(lid, user, request.form.get("action"),
                                   request.form.get("note"))
        if err:
            return back(err=err, to="/team/ops/reports?view=team")
        log("FEEDBACK_UPDATE_DAY7", module="team_ops", entity_type="work_log",
            entity_id=lid, summary="manager " + str(request.form.get("action")))
        return back(msg="Report updated", to="/team/ops/reports?view=team")

    @app.route("/team/ops/reports/<int:lid>/save", methods=["POST"])
    @app.route("/team/ops/logs/<int:lid>/save", methods=["POST"])
    @login_required
    def tops_log_save(lid):
        """Inline-grid autosave. Returns JSON so the cell can show 'Saved'."""
        user = current_user()
        field = request.form.get("field")
        value = request.form.get("value")
        if field not in T.LOG_FIELDS:
            return Response(json.dumps({"ok": False, "error": "unknown field"}),
                            mimetype="application/json", status=400)
        if field in ("link_folder_google_drive", "listing_url") and value:
            value = safe_url(value)
        row, err = T.update_log(lid, user, {field: value},
                                edit_reason=(request.form.get("edit_reason") or "")[:400])
        if err:
            return Response(json.dumps({"ok": False, "error": err}),
                            mimetype="application/json", status=403)
        log("FEEDBACK_UPDATE_DAY3", module="team_ops", entity_type="work_log",
            entity_id=lid, summary="edit " + str(field))
        return Response(json.dumps({"ok": True,
                                    "value": str(row.get(field) or "")}),
                        mimetype="application/json")

    @app.route("/team/ops/reports/<int:lid>/verify", methods=["POST"])
    @app.route("/team/ops/logs/<int:lid>/verify", methods=["POST"])
    @login_required
    def tops_log_verify(lid):
        user = current_user()
        _r, err = T.verify_log(lid, user, (request.form.get("note") or ""))
        return back(msg=None if err else "Report verified", err=err or None,
                    to="/team/ops/reports?view=team")

    @app.route("/team/ops/reports/<int:lid>/delete", methods=["POST"])
    @app.route("/team/ops/logs/<int:lid>/delete", methods=["POST"])
    @login_required
    def tops_log_delete(lid):
        user = current_user()
        ok, err = T.soft_delete_log(lid, user,
                                    (request.form.get("reason") or "")[:400])
        return back(msg="Report soft-deleted" if ok else None,
                    err=None if ok else err, to="/team/ops/reports")

    @app.route("/team/ops/reports/audit")
    @app.route("/team/ops/logs/audit")
    @login_required
    def tops_log_audit():
        user = current_user()
        guard = need_manager(user)
        if guard:
            return guard
        names = T.users_by_id(include_inactive=True)
        rows = ""
        for a in T.log_audit_trail(limit=400):
            flag = ('<span class="tag d-overdue">after lock</span>'
                    if a.get("edited_after_lock") else '<span class="tag">in window</span>')
            rows += ('<tr><td>' + esc(T.to_local(a.get("created_at"), user)) + '</td>'
                     '<td>#' + str(a["log_id"]) + '</td>'
                     '<td>' + esc(who(a.get("actor_id"), names)) + '</td>'
                     '<td>' + esc(a["field_name"]) + '</td>'
                     '<td>' + esc(a.get("old_value") or "") + '</td>'
                     '<td>' + esc(a.get("new_value") or "") + '</td>'
                     '<td>' + esc(a.get("edit_reason") or "") + '</td>'
                     '<td>' + flag + '</td></tr>')
        body = ('<div class="gwrap"><table class="grid"><thead><tr><th>When</th>'
                '<th>Log</th><th>Actor</th><th>Field</th><th>Old</th><th>New</th>'
                '<th>Reason</th><th>Lock</th></tr></thead><tbody>'
                + (rows or '<tr><td colspan="8">No edits recorded.</td></tr>')
                + '</tbody></table></div>')
        return shell("Work-log audit trail",
                     "Every change to a KPI-sensitive field. Append-only — nobody can "
                     "delete this history.", body, user)

    # ========================================================= REVIEW QUEUE ==
    @app.route("/team/ops/review")
    @login_required
    def tops_review():
        user = current_user()
        T.init_schema()
        guard = need_manager(user)
        if guard:
            return guard
        rows = T.list_tasks(user=user, status="REVIEW")
        names = T.users_by_id(include_inactive=True)
        previews = T.latest_comments_map([t["id"] for t in rows])
        items = ""
        for t in rows:
            tid = t["id"]
            done_n = t.get("checklist_completed_count") or 0
            total_n = t.get("checklist_total_count") or 0
            links = ""
            for l in (t.get("links") or [])[:4]:
                u = safe_url(l.get("url"))
                if u:
                    links += ('<a class="tbtn sm" href="' + esc(u) + '" target="_blank"'
                              ' rel="noopener">🔗 link</a>')
            if t.get("drive_folder"):
                u = safe_url(t.get("drive_folder"))
                if u:
                    links += ('<a class="tbtn sm" href="' + esc(u) + '" target="_blank"'
                              ' rel="noopener">📁 Drive</a>')
            ck = ""
            for i in t["checklist"]:
                mark = "☑" if i.get("is_checked") else "☐"
                ck += ('<span class="tag">' + mark + ' ' + esc(i.get("label") or "")
                       + '</span>')
            prev = previews.get(tid)
            items += ('<div class="panel"><div class="tops-head">'
                      '<div><h2 style="margin:0"><a href="/team/ops/task/' + str(tid)
                      + '">' + esc(t["title"][:80]) + '</a></h2>'
                      '<p style="margin:3px 0 0;font-size:.8rem;color:var(--ink-soft)">'
                      + esc(who(t.get("assignee_id"), names)) + ' · '
                      + esc(T.TASK_TYPE_LABELS.get(t.get("task_type"), "—")) + ' · '
                      + esc(t.get("related_keyword") or "no keyword") + ' · '
                      + 'checklist ' + str(done_n) + '/' + str(total_n) + '</p></div>'
                      '<div class="tops-actions">' + due_tag(t, user) + links
                      + status_btn(tid, "DONE", "✅ Approve Done", "primary sm")
                      + '<a class="tbtn sm" href="/team/ops/task/' + str(tid)
                      + '#fix">✏️ Request fix</a></div></div>'
                      + ('<div class="tcrow">' + ck + '</div>' if ck else "")
                      + ('<p class="cprev">💬 ' + esc((prev or "")[:140]) + '</p>'
                         if prev else "") + '</div>')
        body = items or ('<div class="panel"><p>Review queue is empty. Nothing is '
                         'waiting on you.</p></div>')
        return shell("Review Queue", str(len(rows)) + " task(s) waiting for your "
                     "approval. Staff cannot mark anything Done.", body, user)

    # ====================================================== TEAM ANALYTICS ==
    @app.route("/team/ops/analytics")
    @login_required
    def tops_analytics():
        user = current_user()
        T.init_schema()
        guard = need_manager(user)
        if guard:
            return guard
        rng = (request.args.get("range") or "week").strip()
        d_from = (request.args.get("from") or "").strip()
        d_to = (request.args.get("to") or "").strip()
        now = T.utcnow()
        if rng == "today":
            d_from = T.local_today(user)
        elif rng == "week":
            d_from = (now - timedelta(days=7)).date().isoformat()
        elif rng == "month":
            d_from = (now - timedelta(days=30)).date().isoformat()
        staff = (request.args.get("staff") or "").strip()
        data = T.analytics(
            user=user, date_from=d_from or None, date_to=(d_to + "T23:59:59+00:00")
            if d_to else None,
            staff_id=int(staff) if staff.isdigit() else None,
            role=(request.args.get("role") or "").strip() or None,
            store=(request.args.get("store") or "").strip() or None,
            task_type=(request.args.get("type") or "").strip() or None)
        w = data["widgets"]
        tiles = [("Tasks created", w["created"], ""),
                 ("Completed", w["completed"], " good"),
                 ("Overdue", w["overdue"], " bad" if w["overdue"] else ""),
                 ("On-time rate", str(w["on_time_rate"]) + "%", ""),
                 ("Submitted Designs", w["designs"], ""),
                 ("Submitted Listings", w["listings"], ""),
                 ("Keywords researched", w["keywords_researched"], ""),
                 ("Pattern Miner runs", w["pattern_runs"], ""),
                 ("Re-rank reviewed", w["rerank_reviewed"], ""),
                 ("Fix-request rate", str(w["fix_rate"]) + "%", ""),
                 ("Avg review (h)", w["avg_review_hours"], ""),
                 ("Avg completion (h)", w["avg_completion_hours"], "")]
        kpis = '<div class="kpis">' + "".join(
            '<div class="kpi' + c + '"><div class="n">' + esc(n) + '</div>'
            '<div class="l">' + esc(l) + '</div></div>' for l, n, c in tiles) + '</div>'
        lb = ""
        for r in data["leaderboard"]:
            flag = ('<span class="tag d-soon">' + str(r["logs_edited_after_lock"])
                    + '</span>' if r["logs_edited_after_lock"] else "0")
            miss = ('<span class="tag d-overdue">' + str(r["missing_report_days"])
                    + '</span>' if r["missing_report_days"] else "0")
            lb += ('<tr><td><b>' + esc(r["name"]) + '</b>'
                   + ('' if r["active"] else ' <span class="tag">inactive</span>')
                   + '</td><td>' + esc(r["role"]) + '</td>'
                   '<td>' + str(r["tasks_done_approved"]) + '</td>'
                   '<td>' + str(r["on_time_pct"]) + '%</td>'
                   '<td>' + str(r["overdue"]) + '</td>'
                   '<td>' + str(r["design_raw"]) + '</td>'
                   '<td><b>' + str(r["design_verified"]) + '</b></td>'
                   '<td>' + str(r["listing_raw"]) + '</td>'
                   '<td><b>' + str(r["listing_verified"]) + '</b></td>'
                   '<td>' + str(r["log_count"]) + '</td>'
                   '<td>' + miss + '</td>'
                   '<td>' + flag + '</td>'
                   '<td>' + str(r["fix_requests"]) + '</td>'
                   '<td><b>' + str(r["quality_score"]) + '</b></td></tr>')
        table = ('<div class="gwrap"><table class="grid"><thead><tr><th>Staff</th>'
                 '<th>Role</th><th>Done</th><th>On-time</th><th>Overdue</th>'
                 '<th>Submitted designs</th><th>Verified designs</th>'
                 '<th>Submitted listings</th><th>Verified listings</th>'
                 '<th>Reports submitted</th><th>Missing report days</th>'
                 '<th>Edited after lock</th>'
                 '<th>Fix requests</th><th>Quality</th></tr></thead><tbody>'
                 + (lb or '<tr><td colspan="14">No data in this range.</td></tr>')
                 + '</tbody></table></div>')
        # Daily Report widgets (spec §5) — same filters, reported separately from
        # the task widgets above.
        ds = T.daily_report_summary(
            user, date_from=d_from or None, date_to=d_to or None,
            staff_id=int(staff) if staff.isdigit() else None,
            store=(request.args.get("store") or "").strip() or None)
        rtiles = [("Total designs submitted", ds["designs_submitted"], ""),
                  ("Total designs verified", ds["designs_verified"], " good"),
                  ("Total listings submitted", ds["listings_submitted"], ""),
                  ("Total listings verified", ds["listings_verified"], " good"),
                  ("Staff with no report today", ds["missing_today_n"],
                   " bad" if ds["missing_today_n"] else ""),
                  ("Blocked reports", ds["blocked"], " bad" if ds["blocked"] else ""),
                  ("Edited-after-lock reports", ds["edited_after_lock"],
                   " bad" if ds["edited_after_lock"] else ""),
                  ("Avg listings per seller", ds["avg_listings_per_seller"], ""),
                  ("Avg designs per designer", ds["avg_designs_per_designer"], "")]
        rkpis = ('<div class="tsec">Daily Reports</div><div class="kpis">'
                 + "".join('<div class="kpi' + c + '"><div class="n">' + esc(n)
                           + '</div><div class="l">' + esc(l) + '</div></div>'
                           for l, n, c in rtiles)
                 + '</div><p style="font-size:.79rem;color:var(--ink-soft)">'
                 '<a href="/team/ops/reports?view=team">Open Team Daily Reports →</a>'
                 '</p>')
        filt = ('<form class="filters" method="get">'
                '<label>Range<select name="range">'
                + opts([("today", "Today"), ("week", "This week"),
                        ("month", "This month"), ("custom", "Custom")], rng)
                + '</select></label>'
                '<label>From<input type="date" name="from" value="' + esc(d_from)
                + '"></label>'
                '<label>To<input type="date" name="to" value="' + esc(d_to)
                + '"></label>'
                '<label>Staff<select name="staff">'
                + user_opts(user, staff, "Everyone") + '</select></label>'
                '<label>Role<select name="role">'
                + opts(["OWNER", "MANAGER", "SELLER", "DESIGNER"],
                       request.args.get("role"), "Any") + '</select></label>'
                '<label>Type<select name="type">'
                + opts(T.TASK_TYPES, request.args.get("type"), "All") + '</select></label>'
                '<button class="tbtn primary" type="submit">Apply</button></form>')
        note = ('<p style="font-size:.79rem;color:var(--ink-soft)"><b>Submitted</b> = '
                'what staff typed. <b>Verified</b> = not edited after the 48-hour '
                'lock, or signed off by a manager. The leaderboard scores verified '
                'output. Quality = 25% on-time + 25% approval + 20% verified volume '
                '+ 20% low-fix + 10% report integrity. Management insight, not an '
                'automatic punishment.</p>')
        actions = ('<a class="tbtn" href="/team/ops/export/tasks.csv">⬇ Tasks CSV</a>'
                   '<a class="tbtn" href="/team/ops/export/logs.csv">'
                   '⬇ Daily Reports CSV</a>' if T.is_owner(user) else "")
        return shell("Team Analytics", "Output, on-time delivery and KPI integrity.",
                     filt + '<div class="tsec">Tasks</div>' + kpis + rkpis
                     + '<div class="tsec">Leaderboard</div>' + table + note,
                     user, actions)

    # ====================================================== STAFF DIRECTORY ==
    @app.route("/team/ops/staff")
    @login_required
    def tops_staff():
        user = current_user()
        T.init_schema()
        people = T.visible_staff(user)
        names = T.users_by_id(include_inactive=True)
        owner = T.is_owner(user)
        rows, forms = "", ""
        for p in people:
            uid = p["user_id"]
            active = T.user_active(p)
            badge = ('<span class="tag d-ontrack">active</span>' if active
                     else '<span class="tag d-overdue">inactive</span>')
            if owner:
                # A <form> may not live inside <tr>, so the forms sit after the
                # table and the inputs point at them with form="…" (HTML5).
                sf, af = "stf" + str(uid), "act" + str(uid)
                forms += ('<form id="' + sf + '" method="post" '
                          'action="/team/ops/staff/save">'
                          '<input type="hidden" name="user_id" value="' + str(uid)
                          + '"></form>'
                          '<form id="' + af + '" method="post" '
                          'action="/team/ops/staff/active">'
                          '<input type="hidden" name="user_id" value="' + str(uid)
                          + '"><input type="hidden" name="active" value="'
                          + ("0" if active else "1") + '"></form>')
                cells = ('<td><select form="' + sf + '" name="manager_id">'
                         + user_opts(user, p.get("manager_id"), "— none —")
                         + '</select></td>'
                         '<td><input form="' + sf + '" name="timezone" value="'
                         + esc(p.get("timezone") or "") + '" placeholder="'
                         + esc(T.DEFAULT_TZ) + '" size="16"></td>'
                         '<td><input form="' + sf + '" name="default_store" value="'
                         + esc(p.get("default_store") or "") + '" size="10"></td>'
                         '<td><input form="' + sf + '" type="date" name="joined_at" '
                         'value="' + esc((p.get("joined_at") or "")[:10]) + '"></td>'
                         '<td><input form="' + sf + '" type="number" '
                         'name="target_designs" min="0" value="'
                         + str(p.get("target_designs") or 0) + '" style="width:62px">'
                         '</td>'
                         '<td><input form="' + sf + '" type="number" '
                         'name="target_listings" min="0" value="'
                         + str(p.get("target_listings") or 0) + '" style="width:62px">'
                         '</td>'
                         '<td><input form="' + sf + '" type="number" '
                         'name="target_research" min="0" value="'
                         + str(p.get("target_research") or 0) + '" style="width:62px">'
                         '</td>'
                         '<td><input form="' + sf + '" type="checkbox" name="day_off" '
                         'value="1"' + (" checked" if p.get("day_off") else "")
                         + '></td>'
                         '<td><button class="tbtn sm primary" type="submit" form="'
                         + sf + '">Save</button></td>'
                         '<td><button class="tbtn sm' + (" danger" if active else "")
                         + '" type="submit" form="' + af + '">'
                         + ("Deactivate" if active else "Reactivate") + '</button></td>')
                rows += ('<tr><td><b>' + esc(p.get("display_name") or "") + '</b><br>'
                         '<span style="font-size:.72rem;color:var(--ink-faint)">'
                         + esc(p.get("email") or "") + '</span></td>'
                         '<td>' + esc(T.team_role(p)) + '</td>'
                         '<td>' + badge + '</td>' + cells + '</tr>')
            else:
                rows += ('<tr><td><b>' + esc(p.get("display_name") or "") + '</b></td>'
                         '<td>' + esc(T.team_role(p)) + '</td><td>' + badge + '</td>'
                         '<td>' + esc(who(p.get("manager_id"), names)) + '</td>'
                         '<td>' + esc(p.get("timezone") or T.DEFAULT_TZ) + '</td>'
                         '<td>' + esc(p.get("default_store") or "—") + '</td>'
                         '<td>' + esc((p.get("joined_at") or "")[:10] or "—") + '</td>'
                         '<td>' + str(p.get("target_designs") or 0) + '</td>'
                         '<td>' + str(p.get("target_listings") or 0) + '</td>'
                         '<td>' + str(p.get("target_research") or 0) + '</td>'
                         '<td>' + esc(T.to_local(p.get("last_login_at"), user) or "—")
                         + '</td></tr>')
        head = ('<tr><th>Name</th><th>Role</th><th>Status</th><th>Manager</th>'
                '<th>Timezone</th><th>Store</th><th>Joined</th><th>Target designs</th>'
                '<th>Target listings</th><th>Target research</th>'
                + ('<th>Day off</th><th></th><th></th>' if owner
                   else '<th>Last login</th>') + '</tr>')
        note = ('<p style="font-size:.79rem;color:var(--ink-soft)">People are never '
                'hard-deleted — deactivating keeps every task, log, comment and KPI '
                'row resolvable. Accounts and passwords are still managed in '
                '<a href="/admin/users">Admin · Users</a>.</p>')
        body = ('<div class="gwrap"><table class="grid"><thead>' + head
                + '</thead><tbody>' + rows + '</tbody></table></div>' + forms + note)
        return shell("Staff Directory", str(len(people)) + " people in your scope.",
                     body, user)

    @app.route("/team/ops/staff/save", methods=["POST"])
    @login_required
    def tops_staff_save():
        user = current_user()
        if not T.is_owner(user):
            return back(err="Owner only.", to="/team/ops/staff")
        uid = int(request.form.get("user_id") or 0)
        mid = request.form.get("manager_id")
        T.update_staff(
            uid, manager_id=int(mid) if (mid or "").isdigit() else None,
            timezone=(request.form.get("timezone") or "").strip()[:64],
            default_store=(request.form.get("default_store") or "").strip()[:80],
            joined_at=(request.form.get("joined_at") or "").strip()[:10],
            target_designs=int(request.form.get("target_designs") or 0),
            target_listings=int(request.form.get("target_listings") or 0),
            target_research=int(request.form.get("target_research") or 0),
            day_off=1 if request.form.get("day_off") else 0)
        log("TASK_UPDATE", module="team_ops", entity_type="user", entity_id=uid,
            summary="directory updated")
        return back(msg="Saved", to="/team/ops/staff")

    @app.route("/team/ops/staff/active", methods=["POST"])
    @login_required
    def tops_staff_active():
        user = current_user()
        if not T.is_owner(user):
            return back(err="Owner only.", to="/team/ops/staff")
        uid = int(request.form.get("user_id") or 0)
        if uid == user["user_id"]:
            return back(err="You cannot deactivate yourself.", to="/team/ops/staff")
        active = request.form.get("active") == "1"
        T.set_user_active(uid, active, user["user_id"])
        log("TASK_UPDATE", module="team_ops", entity_type="user", entity_id=uid,
            summary="active=" + str(active))
        return back(msg="Updated", to="/team/ops/staff")

    # ============================================================= SETTINGS ==
    @app.route("/team/ops/settings")
    @login_required
    def tops_settings():
        user = current_user()
        T.init_schema()
        if not T.is_owner(user):
            return back(err="Owner only.", to="/team/ops")
        s = T.all_settings()

        def cb(k):
            return " checked" if s.get(k) == "1" else ""

        form = ('<form method="post" action="/team/ops/settings/save">'
                '<div class="panel"><h2>Task defaults</h2><div class="fgrid">'
                '<label>Default deadline hour (local)<input type="number" min="0" '
                'max="23" name="default_deadline_hour" value="'
                + esc(s["default_deadline_hour"]) + '"></label>'
                '<label>Deadline offset (days)<input type="number" min="0" max="30" '
                'name="default_deadline_offset_days" value="'
                + esc(s["default_deadline_offset_days"]) + '"></label>'
                '<label>Business timezone<input name="business_timezone" value="'
                + esc(s["business_timezone"]) + '"></label>'
                '<label>Due-soon threshold (hours)<input type="number" min="1" '
                'max="72" name="due_soon_hours" value="' + esc(s["due_soon_hours"])
                + '"></label></div>'
                '<label class="ck"><input type="checkbox" name="overdue_notifications" '
                'value="1"' + cb("overdue_notifications")
                + '> Overdue / due-soon notifications</label>'
                '</div>'
                '<div class="panel"><h2>Notifications</h2>'
                '<label class="ck"><input type="checkbox" name="inapp_notifications" '
                'value="1"' + cb("inapp_notifications") + '> In-app notifications</label>'
                '<label class="ck"><input type="checkbox" name="email_notifications" '
                'value="1"' + cb("email_notifications")
                + '> Email (Phase 5 — not wired yet)</label>'
                '<label class="ck"><input type="checkbox" name="push_notifications" '
                'value="1"' + cb("push_notifications")
                + '> Push (Phase 5 — not wired yet)</label>'
                '</div><button class="tbtn primary" type="submit">Save settings'
                '</button></form>')
        dd = ""
        for kind, label, fallback in (("store", "Stores / accounts", []),
                                      ("product_type", "Product types", []),
                                      ("work_type", "Work types", T.WORK_TYPES)):
            vals = T.dropdown_values(kind, fallback)
            chips = ""
            for v in vals:
                chips += ('<form method="post" action="/team/ops/settings/dropdown" '
                          'style="display:inline-block;margin:0 5px 5px 0">'
                          '<input type="hidden" name="kind" value="' + kind + '">'
                          '<input type="hidden" name="value" value="' + esc(v) + '">'
                          '<input type="hidden" name="op" value="del">'
                          '<button class="tbtn sm" type="submit">' + esc(v)
                          + ' ✕</button></form>')
            dd += ('<div class="panel"><h2>' + label + '</h2>' + (chips or
                   '<p class="none">Using built-in defaults.</p>')
                   + '<form method="post" action="/team/ops/settings/dropdown" '
                   'style="display:flex;gap:7px;margin-top:9px">'
                   '<input type="hidden" name="kind" value="' + kind + '">'
                   '<input type="hidden" name="op" value="add">'
                   '<input name="value" placeholder="Add a value" style="flex:1;'
                   'padding:7px 9px;border:1px solid var(--line-strong);'
                   'border-radius:7px;background:var(--paper);color:var(--ink)">'
                   '<button class="tbtn" type="submit">Add</button></form></div>')
        hc = ('<div class="panel"><h2>System health</h2>'
              '<p style="font-size:.83rem;margin:0 0 9px">Check that every Team Ops '
              'table, index and column exists before you deploy to the VPS. '
              'Read-only — it never migrates or repairs anything.</p>'
              '<a class="tbtn primary" href="/team/ops/system-health">'
              '🩺 Run schema check</a></div>')
        safety = ('<div class="panel"><h2>Safety</h2><p style="font-size:.83rem;'
                  'margin:0">This module is internal only. <b>PUBLISH_AUTOMATION = '
                  'false</b> — the Team OS never signs in to Etsy, never calls the '
                  'Seller API and never publishes a listing. Tasks and logs only move '
                  'work between people on this dashboard.</p></div>')
        return shell("Settings", "Owner-only defaults for deadlines, dropdowns and "
                     "notifications.", form + dd + hc + safety, user)

    @app.route("/team/ops/settings/save", methods=["POST"])
    @login_required
    def tops_settings_save():
        user = current_user()
        if not T.is_owner(user):
            return back(err="Owner only.", to="/team/ops")
        for k in ("default_deadline_hour", "default_deadline_offset_days",
                  "business_timezone", "due_soon_hours"):
            v = (request.form.get(k) or "").strip()
            if v:
                T.set_setting(k, v[:64])
        for k in ("overdue_notifications", "inapp_notifications",
                  "email_notifications", "push_notifications"):
            T.set_setting(k, "1" if request.form.get(k) else "0")
        log("TASK_UPDATE", module="team_ops", summary="team settings saved")
        return back(msg="Settings saved", to="/team/ops/settings")

    @app.route("/team/ops/settings/dropdown", methods=["POST"])
    @login_required
    def tops_settings_dropdown():
        user = current_user()
        if not T.is_owner(user):
            return back(err="Owner only.", to="/team/ops")
        kind = request.form.get("kind")
        value = (request.form.get("value") or "").strip()[:80]
        if request.form.get("op") == "del":
            T.remove_dropdown(kind, value)
        else:
            T.add_dropdown(kind, value)
        return back(msg="Dropdown updated", to="/team/ops/settings")

    # ======================================================= SYSTEM HEALTH ==
    @app.route("/team/ops/system-health")
    @login_required
    def tops_system_health():
        user = current_user()
        T.init_schema()
        if not T.is_owner(user):
            return back(err="Owner only.", to="/team/ops")
        h = T.health()
        head = {"ok": ("ok", "✅ Schema healthy",
                       "Every table, index and column the Team Ops module needs is "
                       "present. Safe to deploy."),
                "warn": ("warn", "⚠️ Healthy with notes",
                         "Nothing is broken, but read the amber rows before you "
                         "deploy."),
                "fail": ("fail", "🛑 Schema incomplete",
                         "Something required is missing. Restart the app to run "
                         "init_schema(), then reload this page.")}[h["overall"]]
        banner = ('<div class="hbanner ' + head[0] + '"><b>' + head[1] + '</b>'
                  '<span>' + head[2] + '</span></div>')
        legacy = h["legacy"]
        if legacy["both_active"]:
            banner += ('<div class="hbanner warn"><b>' + esc(legacy["label"])
                       + '</b><span>' + esc(legacy["note"]) + '</span></div>')
        secs = ""
        for s in h["sections"]:
            rows = ""
            for r in s["rows"]:
                rows += ('<tr><td><code>' + esc(r["name"]) + '</code></td>'
                         '<td><span class="hstate ' + r["state"] + '">'
                         + r["state"] + '</span></td>'
                         '<td>' + esc(r["detail"]) + '</td></tr>')
            n_ok = sum(1 for r in s["rows"] if r["state"] == "ok")
            secs += ('<div class="panel"><h2>' + esc(s["title"])
                     + ' <span class="hstate ' + s["state"] + '">' + s["state"]
                     + '</span> <span style="font-weight:400;font-size:.78rem;'
                     'color:var(--ink-soft)">' + str(n_ok) + '/'
                     + str(len(s["rows"])) + ' ok</span></h2>'
                     '<div class="gwrap"><table class="grid"><thead><tr>'
                     '<th>Object</th><th>State</th><th>Detail</th></tr></thead>'
                     '<tbody>' + rows + '</tbody></table></div></div>')
        c = h["counts"]
        tiles = [("Active tasks", c["tasks_active"], ""),
                 ("Open tasks", c["tasks_open"], ""),
                 ("Deleted tasks", c["tasks_deleted"], ""),
                 ("Work logs", c["logs_active"], ""),
                 ("Deleted logs", c["logs_deleted"], ""),
                 ("Audit rows", c["audit_rows"], ""),
                 ("Notifications", c["notifications"], ""),
                 ("Unread", c["notifications_unread"], ""),
                 ("Comments", c["comments"], ""),
                 ("Activity rows", c["activity_rows"], ""),
                 ("KPI day rows", c["kpi_rows"], ""),
                 ("Legacy tasks", legacy["legacy_rows"],
                  " bad" if legacy["both_active"] else "")]
        kpis = '<div class="kpis">' + "".join(
            '<div class="kpi' + cls + '"><div class="n">'
            + ("—" if n is None else str(n)) + '</div><div class="l">' + esc(lbl)
            + '</div></div>' for lbl, n, cls in tiles) + '</div>'
        rollout = ('<div class="panel"><h2>Task system rollout</h2>'
                   '<p style="margin:0 0 8px;font-size:.84rem">'
                   + NEW_BADGE + ' <b>/team/ops/board</b> — '
                   + str(legacy["teamops_rows"]) + ' row(s) in <code>team_tasks'
                   '</code>.</p>'
                   '<p style="margin:0;font-size:.84rem">'
                   '<span class="sysbadge legacy">Legacy task system</span> '
                   '<b>/admin/tasks</b> + <b>/me/tasks</b> — '
                   + str(legacy["legacy_rows"]) + ' row(s) in <code>tasks</code>. '
                   'Legacy task system remains active during rollout; this page '
                   '<b>never migrates</b> it.</p></div>')
        env = ('<div class="panel"><h2>Environment</h2>'
               '<div class="gwrap"><table class="grid"><tbody>'
               '<tr><th>Database</th><td><code>' + esc(h["db_path"])
               + '</code></td></tr>'
               '<tr><th>SQLite JSON1</th><td>'
               + ("available" if h["json1"] else "NOT available — TEXT fallback")
               + '</td></tr>'
               '<tr><th>PUBLISH_AUTOMATION</th><td><b>'
               + esc(h["publish_automation"]) + '</b>'
               + (' <span class="hstate ok">confirmed false</span>'
                  if h["publish_automation"] is False
                  else ' <span class="hstate fail">must be false</span>')
               + '</td></tr>'
               '<tr><th>Business timezone</th><td>'
               + esc(T.business_tz_name()) + '</td></tr>'
               '</tbody></table></div></div>')
        return shell("System Health", "Owner-only pre-deploy schema check. "
                     "Read-only — it never migrates or repairs anything.",
                     banner + kpis + rollout + env + secs, user,
                     '<a class="tbtn" href="/team/ops/settings">Settings</a>')

    # ======================================================== NOTIFICATIONS ==
    @app.route("/team/ops/notifications")
    @login_required
    def tops_notifications():
        user = current_user()
        T.init_schema()
        rows = T.notifications(user["user_id"], limit=80)
        items = ""
        for n in rows:
            unread = not n.get("read_at")
            link = ('/team/ops/task/' + str(n["related_task_id"])
                    if n.get("related_task_id") else "/team/ops")
            items += ('<li><a href="' + link + '"><b>'
                      + ("🔵 " if unread else "") + esc(n.get("title") or "")
                      + '</b></a> <span class="when">'
                      + esc(T.to_local(n.get("created_at"), user)) + '</span>'
                      '<div>' + esc(n.get("message") or "") + '</div></li>')
        body = ('<form method="post" action="/team/ops/notifications/read" '
                'style="margin-bottom:12px"><button class="tbtn" type="submit">'
                'Mark all read</button></form>'
                '<div class="panel"><ul class="tl">'
                + (items or '<li class="none">Nothing yet.</li>') + '</ul></div>')
        return shell("Notifications", "In-app only. Email and push are Phase 5.",
                     body, user)

    @app.route("/team/ops/notifications/read", methods=["POST"])
    @login_required
    def tops_notifications_read():
        user = current_user()
        T.mark_notifications_read(user["user_id"])
        return back(msg="All read", to="/team/ops/notifications")

    # ============================================================== EXPORTS ==
    @app.route("/team/ops/export/tasks.csv")
    @login_required
    def tops_export_tasks():
        user = current_user()
        if not T.is_owner(user):
            return back(err="Owner only.", to="/team/ops")
        log("PDF_EXPORT_MANAGER", module="team_ops", summary="tasks csv")
        return csv_response(T.TASK_CSV_COLS,
                            T.tasks_csv_rows(user, include_deleted=True),
                            "team_tasks.csv")

    @app.route("/team/ops/export/logs.csv")
    @login_required
    def tops_export_logs():
        user = current_user()
        if not T.is_manager(user):
            return back(err="Manager or Owner only.", to="/team/ops")
        f = {k: (request.args.get(k) or "").strip() for k in ("store", "status", "q")}
        log("PDF_EXPORT_MANAGER", module="team_ops", summary="work logs csv")
        return csv_response(
            T.LOG_CSV_COLS,
            T.logs_csv_rows(user, include_deleted=T.is_owner(user),
                            store=f["store"] or None, status=f["status"] or None,
                            search=f["q"] or None),
            "proactive_work_logs.csv")

    # ================================================= WORKFLOW INTEGRATION ==
    @app.route("/team/ops/followups", methods=["POST"])
    @login_required
    def tops_followups():
        """Day 3 + Day 7 checks from Learn. Internal reminders only."""
        user = current_user()
        guard = need_manager(user)
        if guard:
            return guard
        aid = request.form.get("assignee_id")
        made = T.create_followups_for_listing(
            (request.form.get("listing_id") or "").strip()[:80],
            (request.form.get("keyword") or "").strip()[:120],
            int(aid) if (aid or "").isdigit() else None, user["user_id"],
            (request.form.get("store") or "").strip()[:80])
        log("TASK_CREATE", module="team_ops",
            summary="day3+day7 follow-ups (" + str(len(made)) + ")")
        return back(msg="Day 3 + Day 7 follow-up tasks created",
                    to=request.form.get("next") or "/team/ops/board")

    return app
