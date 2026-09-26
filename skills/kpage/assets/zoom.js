<div class="zoom" id="zoom" hidden role="dialog" aria-label="Diagram">
  <div class="zbar"><span class="zt">DIAGRAM · wheel to zoom, drag to pan</span><button type="button" data-z="out">−</button><button type="button" data-z="in">+</button><button type="button" data-z="fit">fit</button><button type="button" data-z="one">100%</button><button type="button" data-z="close">close</button></div>
  <div class="zstage" id="zstage"></div>
</div>
<script>
// Diagram zoom. The viewer renders mermaid fences into an SVG; this finds
// every such drawing, shows it at full width, adds an "open" button, and on
// click copies the drawing into a full-screen stage with wheel zoom and drag.
(function(){
  var zoom = document.getElementById('zoom'), stage = document.getElementById('zstage');
  var cur = null, s = 1, tx = 0, ty = 0, drag = null;
  function apply(){ if (cur) cur.style.transform = 'translate(' + tx + 'px,' + ty + 'px) scale(' + s + ')'; }
  function natural(svg){
    var vb = svg.viewBox && svg.viewBox.baseVal;
    if (vb && vb.width && vb.height) return {w: vb.width, h: vb.height};
    var r = svg.getBoundingClientRect(); return {w: r.width || 800, h: r.height || 600};
  }
  function fit(){
    if (!cur) return;
    var n = natural(cur), W = stage.clientWidth, H = stage.clientHeight;
    s = Math.min(W / n.w, H / n.h) * 0.96; tx = (W - n.w * s) / 2; ty = (H - n.h * s) / 2; apply();
  }
  function open(svg){
    stage.innerHTML = '';
    cur = svg.cloneNode(true);
    var n = natural(svg);
    cur.removeAttribute('style'); cur.setAttribute('width', n.w); cur.setAttribute('height', n.h);
    stage.appendChild(cur); zoom.hidden = false; document.body.style.overflow = 'hidden';
    requestAnimationFrame(fit);
  }
  function close(){ zoom.hidden = true; stage.innerHTML = ''; cur = null; document.body.style.overflow = ''; }
  function zoomAt(f, cx, cy){
    var ns = Math.max(0.1, Math.min(12, s * f));
    tx = cx - (cx - tx) * (ns / s); ty = cy - (cy - ty) * (ns / s); s = ns; apply();
  }
  zoom.querySelector('.zbar').addEventListener('click', function(e){
    var b = e.target.closest('button'); if (!b) return;
    var c = stage.clientWidth / 2, m = stage.clientHeight / 2;
    if (b.dataset.z === 'in') zoomAt(1.25, c, m);
    else if (b.dataset.z === 'out') zoomAt(0.8, c, m);
    else if (b.dataset.z === 'fit') fit();
    else if (b.dataset.z === 'one'){ var n = natural(cur); s = 1; tx = (stage.clientWidth - n.w) / 2; ty = 20; apply(); }
    else if (b.dataset.z === 'close') close();
  });
  stage.addEventListener('wheel', function(e){
    e.preventDefault(); var r = stage.getBoundingClientRect();
    zoomAt(e.deltaY < 0 ? 1.12 : 1 / 1.12, e.clientX - r.left, e.clientY - r.top);
  }, {passive: false});
  stage.addEventListener('pointerdown', function(e){ drag = {x: e.clientX - tx, y: e.clientY - ty}; stage.classList.add('drag'); stage.setPointerCapture(e.pointerId); });
  stage.addEventListener('pointermove', function(e){ if (!drag) return; tx = e.clientX - drag.x; ty = e.clientY - drag.y; apply(); });
  stage.addEventListener('pointerup', function(){ drag = null; stage.classList.remove('drag'); });
  stage.addEventListener('pointercancel', function(){ drag = null; stage.classList.remove('drag'); });
  document.addEventListener('keydown', function(e){ if (e.key === 'Escape' && !zoom.hidden) close(); });
  window.addEventListener('resize', function(){ if (!zoom.hidden) fit(); });

  // Find rendered diagrams. The viewer may replace the <pre> or render into it,
  // so look for any SVG whose container carries "mermaid" in its class, now and
  // whenever the document changes.
  function holder(svg){
    var el = svg.parentElement;
    while (el && el !== document.body){ if (/\bmermaid\b/.test(el.className || '')) return el; el = el.parentElement; }
    return null;
  }
  function wire(){
    document.querySelectorAll('.prose svg').forEach(function(svg){
      if (svg.dataset.zoomed) return;
      var h = holder(svg); if (!h) return;
      svg.dataset.zoomed = '1'; h.classList.add('diagram');
      svg.addEventListener('click', function(){ open(svg); });
      if (!h.querySelector('.diagram-open')){
        var b = document.createElement('button'); b.type = 'button'; b.className = 'diagram-open'; b.textContent = 'open large';
        b.addEventListener('click', function(e){ e.stopPropagation(); open(svg); });
        h.appendChild(b);
      }
    });
  }
  wire();
  var pending = null;
  new MutationObserver(function(){ if (pending) return; pending = setTimeout(function(){ pending = null; wire(); }, 100); })
    .observe(document.body, {childList: true, subtree: true});
  document.addEventListener('kpage:tab', function(){ setTimeout(wire, 200); });
})();
</script>
