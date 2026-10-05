(function () {
  const b = document.getElementById('undo-btn'), w = document.getElementById('undo-what');
  if (!b) return;
  async function state() {
    const d = await (await fetch('/undo.json')).json();
    b.disabled = !d.what; w.textContent = d.what ? 'undo: ' + d.what : '';
  }
  async function undo() {
    if (b.disabled) return;
    const r = await fetch('/undo', {method: 'POST'});
    if (!r.ok) { alert('Can’t undo: ' + await r.text()); return; }
    location.reload();
  }
  b.addEventListener('click', undo);
  addEventListener('keydown', (e) => { if ((e.ctrlKey || e.metaKey) && e.key === 'z' && !e.target.closest('input, textarea')) { e.preventDefault(); undo(); } });
  window.refreshUndo = state; state();
})();
