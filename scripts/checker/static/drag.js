// Click and drag with drop zones (mouse, pen or touch): dragging something over a target splits the target into the
// choices that drop allows, each saying what it does; letting go on one does it, anywhere else does nothing (as does
// Escape). A press without moving is a click; on touch, hold a moment before dragging, so a swipe still scrolls.
// o: {handle, target: selectors; item(handleEl); label(item); name(targetEl): shown over the zones;
//     zones(item, targetEl) -> [{label, say, run} or null]; minWidth: the zones at least this wide, centred on a smaller
//     target (a dot on the map)}
function dragZones(o) {
  let drag = null, over = null, zoneEl = null, hot = null, justDragged = false;
  addEventListener('click', (e) => { if (justDragged) { e.stopPropagation(); e.preventDefault(); } }, true);
  const ghost = Object.assign(document.createElement('div'), {className: 'dz-ghost'});
  document.body.appendChild(ghost);
  const tag = () => document.querySelectorAll(o.handle).forEach((h) => h.classList.add('dz-handle'));
  new MutationObserver(tag).observe(document.body, {childList: true, subtree: true}); tag();
  function clearZones() { if (zoneEl) zoneEl.remove(); zoneEl = null; over = null; hot = null; }
  function showZones(t) {
    if (t === over) return;
    clearZones();
    if (!t) return;
    const zs = o.zones(drag.item, t).filter(Boolean);
    if (!zs.length) return;
    over = t;
    const r = t.getBoundingClientRect(), h = Math.max(Math.min(r.height, 50), 44) + 24;
    // Over a short target, centred on it; over a tall one (a whole card), where the pointer is
    const top = r.height <= 60 ? r.top - (h - r.height) / 2 : Math.max(r.top, Math.min(drag.y - h / 2, r.bottom - h));
    zoneEl = Object.assign(document.createElement('div'), {className: 'dz-zones'});
    const w = Math.max(r.width, o.minWidth || 0), left = Math.max(4, Math.min(r.left + r.width / 2 - w / 2, innerWidth - w - 4));
    Object.assign(zoneEl.style, {left: left + scrollX + 'px', top: top + scrollY + 'px', width: w + 'px', height: h + 'px'});
    zoneEl.innerHTML = `<div class="dz-row">${zs.map((z, i) => `<div class="dz-zone" data-z="${i}">${z.label}</div>`).join('')}</div><div class="dz-name"></div>`;
    zoneEl.lastChild.textContent = o.name ? o.name(t) : '';
    zoneEl.zs = zs; document.body.appendChild(zoneEl);
  }
  function hit(x, y) {
    const el = document.elementFromPoint(x, y);
    const z = el && el.closest('.dz-zone');
    if (z) return {zone: zoneEl.zs[+z.dataset.z], zEl: z, t: over};
    if (el && zoneEl && zoneEl.contains(el)) return {t: over};
    const t = el && el.closest(o.target);
    return {t: t && t !== drag.el ? t : null};
  }
  function update() {
    const h = hit(drag.x, drag.y);
    if (!h.zone) showZones(h.t);
    if (hot) hot.classList.remove('hot');
    hot = h.zEl || null;
    if (hot) hot.classList.add('hot');
    ghost.innerHTML = '';
    ghost.append(o.label(drag.item));
    if (h.zone) ghost.appendChild(Object.assign(document.createElement('div'), {className: 'dz-say', textContent: h.zone.say}));
    // Above the pointer, so it never covers the zones under it
    ghost.style.left = Math.max(8, Math.min(drag.x + 14, innerWidth - ghost.offsetWidth - 8)) + 'px';
    ghost.style.top = Math.max(4, drag.y - ghost.offsetHeight - 14) + 'px';
    return h;
  }
  function start() {
    drag.on = true; document.body.classList.add('dragging');
    document.querySelectorAll(o.target).forEach((t) => t.classList.add('dz-target'));
    ghost.style.display = 'block'; update(); scroll();
  }
  function scroll() {  // near the window's top or bottom edge the page scrolls, so far targets can be reached
    if (!drag || !drag.on) return;
    const edge = 70, y = drag.y;
    const speed = y < edge ? -(edge - y) / 3 : y > innerHeight - edge ? (y - (innerHeight - edge)) / 3 : 0;
    if (speed) { scrollBy(0, speed); clearZones(); update(); }
    requestAnimationFrame(scroll);
  }
  function end(ev, cancel) {
    if (!drag) return;
    clearTimeout(drag.timer);
    const d = drag, h = d.on && !cancel ? hit(ev.clientX, ev.clientY) : {};
    drag = null; clearZones();
    ghost.style.display = 'none'; document.body.classList.remove('dragging');
    document.querySelectorAll('.dz-target').forEach((t) => t.classList.remove('dz-target'));
    if (!d.on) return;
    justDragged = true; setTimeout(() => { justDragged = false; }, 0);  // the click a drag ends with is no click
    if (h.zone) h.zone.run();
  }
  document.addEventListener('pointerdown', (ev) => {
    if (ev.button !== 0 || ev.target.closest('button, input, select, a, dialog')) return;
    const handle = ev.target.closest(o.handle); if (!handle) return;
    const item = o.item(handle); if (!item) return;
    drag = {item, el: handle, x: ev.clientX, y: ev.clientY, sx: ev.clientX, sy: ev.clientY, on: false, touch: ev.pointerType === 'touch'};
    if (drag.touch) drag.timer = setTimeout(() => { if (drag && !drag.on) start(); }, 350);
  });
  document.addEventListener('pointermove', (ev) => {
    if (!drag) return;
    drag.x = ev.clientX; drag.y = ev.clientY;
    const moved = Math.hypot(ev.clientX - drag.sx, ev.clientY - drag.sy);
    if (!drag.on) {
      if (drag.touch) { if (moved > 8) { clearTimeout(drag.timer); drag = null; } return; }  // a swipe: let it scroll
      if (moved < 6) return;
      start();
    }
    ev.preventDefault(); update();
  });
  document.addEventListener('touchmove', (ev) => { if (drag && drag.on) ev.preventDefault(); }, {passive: false});
  document.addEventListener('pointerup', (ev) => end(ev, false));
  document.addEventListener('pointercancel', (ev) => end(ev, true));
  addEventListener('keydown', (ev) => { if (ev.key === 'Escape' && drag) end(ev, true); });
}
