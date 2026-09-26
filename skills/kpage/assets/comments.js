
<div class="cbtn" id="cbtn" hidden><button type="button" class="cprimary">Comment</button></div>
<div class="composer" id="composer" hidden>
  <div class="cq" id="composerQuote"></div>
  <textarea id="composerBody" rows="4" placeholder="What about this?"></textarea>
  <div class="cacts"><button type="button" id="composerCancel" class="tlink">cancel</button><button type="button" id="composerSave" class="cprimary">Comment</button></div>
</div>
<aside class="threads" id="threads" hidden aria-label="Comments"></aside>
<script>
// Comment threads, after the pi-workflow console. A thread is anchored to the
// quoted text plus a little context either side; the page finds the quote
// again on every render, uses the context only to choose between repeats, and
// shows a thread as orphaned when its sentence is gone rather than pinning it
// to words nobody was talking about. Threads live in the artifact's database,
// so the Claude session that published the page reads them and replies into
// the same thread.
(function(){
  var state = { db: null, threads: [], active: null, showResolved: false, pending: null, open: false, replying: null, status: '' };
  var $ = function(id){ return document.getElementById(id); };
  var esc = function(s){ return String(s == null ? '' : s).replace(/[&<>"']/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]; }); };
  var currentTab = function(){ return document.body.dataset.tab || ''; };
  var currentPanel = function(){ return document.getElementById('p-' + currentTab()); };
  var badge = document.createElement('button');
  badge.type = 'button'; badge.className = 'cbadge'; badge.setAttribute('aria-pressed', 'false'); badge.textContent = 'Comments';
  document.querySelector('.tabs .row').appendChild(badge);
  try { state.open = localStorage.getItem('kpage-threads') === '1'; } catch(e){}

  // --- anchoring ---------------------------------------------------------
  function textNodes(root){
    var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT), nodes = [], off = 0, n;
    while ((n = walker.nextNode())) { nodes.push({ node: n, start: off, end: off + n.nodeValue.length }); off += n.nodeValue.length; }
    return { nodes: nodes, text: nodes.map(function(x){ return x.node.nodeValue; }).join('') };
  }
  function anchorSpan(text, t){
    var hits = [], i;
    for (i = text.indexOf(t.quote); i !== -1; i = text.indexOf(t.quote, i + 1)) hits.push(i);
    if (!hits.length) return null;
    if (hits.length === 1) return { start: hits[0], end: hits[0] + t.quote.length };
    var before = t.before || '', after = t.after || '';
    var score = function(i){
      var b = text.slice(Math.max(0, i - before.length), i), a = text.slice(i + t.quote.length, i + t.quote.length + after.length), s = 0, e = 0;
      while (s < b.length && b[b.length - 1 - s] === before[before.length - 1 - s]) s++;
      while (e < a.length && a[e] === after[e]) e++;
      return s + e;
    };
    var scored = hits.map(function(i){ return [i, score(i)]; }).sort(function(x, y){ return y[1] - x[1]; });
    if (scored.length > 1 && scored[0][1] === scored[1][1]) return null;
    return { start: scored[0][0], end: scored[0][0] + t.quote.length };
  }
  function markSpan(root, start, end, id, cls){
    var nodes = textNodes(root).nodes;
    nodes.filter(function(n){ return n.start < end && n.end > start; }).forEach(function(n){
      var from = Math.max(0, start - n.start), to = Math.min(n.node.nodeValue.length, end - n.start);
      if (to <= from) return;
      var mid = from > 0 ? n.node.splitText(from) : n.node;
      if (to - from < mid.nodeValue.length) mid.splitText(to - from);
      var mark = document.createElement('mark');
      mark.className = 'cmark' + cls; mark.dataset.thread = id;
      mid.parentNode.insertBefore(mark, mid); mark.appendChild(mid);
    });
  }
  function clearMarks(root){
    Array.prototype.slice.call(root.querySelectorAll('mark.cmark')).forEach(function(m){
      var p = m.parentNode; while (m.firstChild) p.insertBefore(m.firstChild, m); p.removeChild(m); p.normalize();
    });
  }
  var orphaned = {};
  function applyMarks(){
    var root = currentPanel(); if (!root) return;
    clearMarks(root);
    var text = textNodes(root).text, spans = [];
    orphaned = {};
    threadsFor(currentTab()).forEach(function(t){
      var s = anchorSpan(text, t);
      if (!s) orphaned[t.id] = true;
      else spans.push({ start: s.start, end: s.end, id: t.id, cls: (t.resolved ? ' done' : '') + (state.active === t.id ? ' active' : '') });
    });
    spans.sort(function(a, b){ return b.start - a.start; }).forEach(function(s){ markSpan(root, s.start, s.end, s.id, s.cls); });
    Array.prototype.slice.call(root.querySelectorAll('mark.cmark')).forEach(function(m){
      m.onclick = function(ev){ ev.stopPropagation(); state.active = m.dataset.thread; state.open = true; render(); };
    });
  }

  // --- rendering ---------------------------------------------------------
  function threadsFor(doc){
    return state.threads.filter(function(t){ return t.doc === doc; }).sort(function(a, b){ return (a.createdAt || '').localeCompare(b.createdAt || ''); });
  }
  function fmt(at){ try { var d = new Date(at); return d.toLocaleDateString(undefined, { day: 'numeric', month: 'short' }) + ' ' + d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' }); } catch(e){ return ''; } }
  function renderThreads(){
    var all = threadsFor(currentTab());
    var open = all.filter(function(t){ return !t.resolved; });
    var shown = state.showResolved ? all : open;
    var head = '<div class="thead"><span class="eyebrow">Comments on this tab · ' + open.length + ' open</span>' +
      '<span>' + (all.length > open.length ? '<button type="button" class="tlink" id="toggleResolved">' + (state.showResolved ? 'hide' : 'show') + ' ' + (all.length - open.length) + ' resolved</button> ' : '') + '<button type="button" class="tlink" id="closeThreads">close</button></span></div>';
    if (state.status) head += '<div class="cstatus">' + esc(state.status) + '</div>';
    if (!state.db) return head + '<div class="tnone">Comments are stored with this page on claude.ai and need the signed-in viewer. This view cannot reach that store, so commenting is off here.</div>';
    if (!all.length) return head + '<div class="tnone">Select any text on this tab and a <b>Comment</b> button appears. Each comment opens a thread. Tell the Claude session that published this page to read them; it replies here.</div>';
    return head + shown.map(function(t){
      var cls = 'thread' + (t.resolved ? ' done' : '') + (state.active === t.id ? ' active' : '') + (orphaned[t.id] ? ' orphan' : '');
      var msgs = (t.messages || []).map(function(m){
        return '<div class="tmsg ' + (m.author === 'Claude' ? 'claude' : 'human') + '"><div class="ta">' + esc(m.author) + ' · ' + fmt(m.at) + '</div><div class="tb">' + esc(m.body) + '</div></div>';
      }).join('');
      var reply = state.replying === t.id
        ? '<div class="treplybox"><textarea rows="3" data-reply="' + esc(t.id) + '" placeholder="Reply"></textarea><div class="cacts"><button type="button" class="tlink" data-cancelreply="' + esc(t.id) + '">cancel</button><button type="button" class="cprimary" data-sendreply="' + esc(t.id) + '">Reply</button></div></div>'
        : '';
      return '<div class="' + cls + '" data-thread="' + esc(t.id) + '">' +
        '<div class="tquote">' + (orphaned[t.id] ? '<b>no longer on this tab · </b>' : '') + esc(t.quote) + '</div>' + msgs + reply +
        '<div class="tacts"><button type="button" class="tlink" data-replyto="' + esc(t.id) + '">reply</button><button type="button" class="tlink" data-resolve="' + esc(t.id) + '">' + (t.resolved ? 'reopen' : 'resolve') + '</button></div></div>';
    }).join('');
  }
  function renderCounts(){
    var counts = {};
    state.threads.forEach(function(t){ if (!t.resolved) counts[t.doc] = (counts[t.doc] || 0) + 1; });
    Array.prototype.slice.call(document.querySelectorAll('.tabs button[data-doc]')).forEach(function(b){
      var c = counts[b.dataset.doc], el = b.querySelector('.cnt');
      if (c && !el) { el = document.createElement('span'); el.className = 'cnt'; b.appendChild(el); }
      if (el) { if (c) el.textContent = String(c); else el.remove(); }
    });
    var total = state.threads.filter(function(t){ return !t.resolved; }).length;
    badge.textContent = 'Comments' + (total ? ' · ' + total : '');
    badge.setAttribute('aria-pressed', String(state.open));
  }
  function render(){
    var draft = null, focusId = state.replying;
    var ta = focusId && document.querySelector('textarea[data-reply="' + focusId + '"]');
    if (ta) draft = ta.value;
    document.body.classList.toggle('threads-open', state.open);
    var aside = $('threads');
    aside.hidden = !state.open;
    aside.innerHTML = renderThreads();
    renderCounts();
    applyMarks();
    try { localStorage.setItem('kpage-threads', state.open ? '1' : '0'); } catch(e){}
    if (draft != null) { ta = document.querySelector('textarea[data-reply="' + focusId + '"]'); if (ta) { ta.value = draft; ta.focus(); } }
    wireAside();
  }

  // --- store -------------------------------------------------------------
  function col(){ return state.db.collection('threads'); }
  function setStatus(msg){ state.status = msg; render(); if (msg) setTimeout(function(){ if (state.status === msg) { state.status = ''; render(); } }, 6000); }
  function fail(e){ setStatus('Could not save: ' + (e && e.code ? e.code : 'unknown error')); }
  function openThread(pending, body){
    var now = new Date().toISOString();
    var doc = { doc: currentTab(), quote: pending.quote, before: pending.before, after: pending.after, resolved: false, createdAt: now,
                messages: [{ author: 'Reviewer', body: body, at: now }] };
    return col().add(doc).catch(fail);
  }
  function reply(id, body){
    var t = state.threads.filter(function(x){ return x.id === id; })[0]; if (!t) return;
    var msgs = (t.messages || []).slice(); msgs.push({ author: 'Reviewer', body: body, at: new Date().toISOString() });
    return col().doc(id).update({ messages: msgs }).catch(fail);
  }
  function resolve(id, on){ return col().doc(id).update({ resolved: on }).catch(fail); }

  // --- wiring ------------------------------------------------------------
  function wireAside(){
    var aside = $('threads');
    Array.prototype.slice.call(aside.querySelectorAll('.thread')).forEach(function(el){
      el.onclick = function(ev){
        if (ev.target.closest('.tlink, .cprimary, textarea')) return;
        state.active = el.dataset.thread; render();
        var mark = currentPanel().querySelector('mark.cmark[data-thread="' + el.dataset.thread + '"]');
        if (mark) mark.scrollIntoView({ block: 'center', behavior: 'smooth' });
      };
    });
    Array.prototype.slice.call(aside.querySelectorAll('[data-resolve]')).forEach(function(b){
      b.onclick = function(){ var t = state.threads.filter(function(x){ return x.id === b.dataset.resolve; })[0]; if (t) resolve(t.id, !t.resolved); };
    });
    Array.prototype.slice.call(aside.querySelectorAll('[data-replyto]')).forEach(function(b){
      b.onclick = function(){ state.replying = b.dataset.replyto; state.active = b.dataset.replyto; render(); var ta = aside.querySelector('textarea[data-reply]'); if (ta) ta.focus(); };
    });
    Array.prototype.slice.call(aside.querySelectorAll('[data-cancelreply]')).forEach(function(b){ b.onclick = function(){ state.replying = null; render(); }; });
    Array.prototype.slice.call(aside.querySelectorAll('[data-sendreply]')).forEach(function(b){
      b.onclick = function(){
        var ta = aside.querySelector('textarea[data-reply="' + b.dataset.sendreply + '"]'), body = ta ? ta.value.trim() : '';
        if (!body) return;
        b.disabled = true; state.replying = null;
        reply(b.dataset.sendreply, body).then(function(){ render(); });
      };
    });
    var tr = $('toggleResolved'); if (tr) tr.onclick = function(){ state.showResolved = !state.showResolved; render(); };
    var cl = $('closeThreads'); if (cl) cl.onclick = function(){ state.open = false; render(); };
  }
  badge.onclick = function(){ state.open = !state.open; render(); };

  var cbtn = $('cbtn'), composer = $('composer');
  var hide = function(){ cbtn.hidden = true; composer.hidden = true; state.pending = null; };
  document.addEventListener('mouseup', function(ev){
    if (!state.db) return;
    if (ev.target.closest('.threads, .composer, .cbtn, .tabs')) return;
    setTimeout(function(){
      var sel = window.getSelection(), root = currentPanel();
      if (!sel || sel.isCollapsed || !root || !root.contains(sel.anchorNode)) { if (composer.hidden) hide(); return; }
      var quote = sel.toString().trim();
      if (quote.length < 2) { if (composer.hidden) hide(); return; }
      var tn = textNodes(root), r = sel.getRangeAt(0);
      var entry = tn.nodes.filter(function(n){ return n.node === r.startContainer; })[0];
      if (!entry) { hide(); return; }
      var raw = sel.toString(), lead = raw.length - raw.replace(/^\s+/, '').length;
      var s = entry.start + r.startOffset + lead, e = s + quote.length;
      state.pending = { quote: quote, before: tn.text.slice(Math.max(0, s - 60), s), after: tn.text.slice(e, e + 60) };
      var rect = r.getBoundingClientRect();
      cbtn.style.top = Math.min(window.innerHeight - 44, rect.bottom + 6) + 'px';
      cbtn.style.left = Math.min(window.innerWidth - 110, Math.max(8, rect.left)) + 'px';
      cbtn.hidden = false; composer.hidden = true;
    }, 0);
  });
  cbtn.firstElementChild.onclick = function(){
    cbtn.hidden = true;
    $('composerQuote').textContent = state.pending.quote;
    composer.hidden = false; $('composerBody').value = ''; $('composerBody').focus();
  };
  $('composerCancel').onclick = hide;
  $('composerSave').onclick = function(){
    var body = $('composerBody').value.trim(), pending = state.pending;
    if (!body || !pending) return;
    $('composerSave').disabled = true;
    openThread(pending, body).then(function(){ $('composerSave').disabled = false; hide(); state.open = true; render(); });
  };
  document.addEventListener('keydown', function(ev){ if (ev.key === 'Escape') { hide(); state.replying = null; render(); } });
  document.addEventListener('kpage:tab', function(){ state.active = null; state.replying = null; render(); });

  render();
  if (!window.claude || typeof window.claude.use !== 'function') return;
  window.claude.use('db').then(function(db){
    if (!db) { render(); return; }
    state.db = db;
    col().onSnapshot(function(snap){
      state.threads = snap.docs.map(function(d){ var b = d.data() || {}; return { id: d.id, doc: b.doc, quote: b.quote || '', before: b.before || '', after: b.after || '', resolved: !!b.resolved, createdAt: b.createdAt || '', messages: b.messages || [] }; });
      render();
    }, function(e){ state.db = null; state.status = 'Comment store unavailable (' + (e && e.code ? e.code : 'error') + ').'; render(); });
    render();
  });
})();
</script>
