<script>
// Tabs: one panel per document, the open one named in the URL hash so a link
// to a heading opens its document first. Announces each switch as kpage:tab
// so the comment and zoom layers re-anchor to the visible panel.
(function(){
  try { if ('scrollRestoration' in history) history.scrollRestoration = 'manual'; } catch(e){}
  var panels = Array.prototype.slice.call(document.querySelectorAll('.panel'));
  var btns = Array.prototype.slice.call(document.querySelectorAll('.tabs button[data-doc]'));
  var ids = panels.map(function(p){ return p.dataset.slug; });
  var pageTitle = document.title;
  function remember(id){ try { localStorage.setItem('kpage-tab', id); } catch(e){} }
  function recall(){ try { return localStorage.getItem('kpage-tab'); } catch(e){ return null; } }
  function show(id, scroll){
    if (ids.indexOf(id) < 0) id = ids[0];
    var panel = document.getElementById('p-' + id);
    panels.forEach(function(p){ p.hidden = (p !== panel); });
    btns.forEach(function(b){ b.setAttribute('aria-selected', String(b.dataset.doc === id)); });
    remember(id);
    document.body.dataset.tab = id;
    try { document.dispatchEvent(new CustomEvent('kpage:tab', { detail: id })); } catch(e){}
    document.title = pageTitle + ' · ' + panel.querySelector('.doc-title').textContent;
    if (scroll) window.scrollTo(0, 0);
  }
  function go(id){
    if (('#' + id) !== location.hash) history.pushState(null, '', '#' + id);
    show(id, true);
  }
  btns.forEach(function(b){ b.addEventListener('click', function(){ go(b.dataset.doc); }); });
  function fromHash(){
    var h = location.hash.replace(/^#/, '');
    if (!h) return null;
    if (ids.indexOf(h) >= 0) return h;
    // an anchor inside a document: open that document, then jump to it
    var el = document.getElementById(h);
    var owner = el && el.closest ? el.closest('.panel') : null;
    if (owner) { show(owner.dataset.slug, false); if (el.scrollIntoView) el.scrollIntoView(); return owner.dataset.slug; }
    return null;
  }
  window.addEventListener('hashchange', function(){ var h = location.hash.slice(1); if (ids.indexOf(h) >= 0) show(h, true); else fromHash(); });
  window.addEventListener('popstate', function(){ show(fromHash() || recall() || ids[0], false); });
  var start = fromHash();
  if (!start) show(recall() || ids[0], false);
})();
</script>
