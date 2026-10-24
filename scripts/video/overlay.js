// Presentation layer injected only while recording the demo: cursor, click ripple, caption chip, zoom, time-lapse badge.
// It never changes the app's behavior; it only draws on top of the page.
(() => {
  if (window.__tmov) return;
  window.__tmov = true;
  const css = `
  ::-webkit-scrollbar { width: 0 !important; height: 0 !important; }
  #tmov-cap { position: fixed; left: 44px; bottom: 44px; z-index: 2147483646; display: flex; align-items: center; gap: 16px;
    padding: 14px 26px 14px 14px; border-radius: 16px; background: linear-gradient(135deg, rgba(11,26,51,.97), rgba(23,52,94,.97));
    color: #fff; font: 650 23px Inter, "Segoe UI", system-ui, sans-serif; letter-spacing: .005em; box-shadow: 0 16px 44px rgba(7,18,38,.38);
    opacity: 0; transform: translateY(18px); transition: opacity .45s ease, transform .45s ease; pointer-events: none; max-width: 980px; }
  #tmov-cap.on { opacity: 1; transform: none; }
  #tmov-cap .m { width: 42px; height: 42px; border-radius: 11px; background: linear-gradient(135deg, #2a78d6, #1baf7a);
    display: grid; place-items: center; flex-shrink: 0; }
  #tmov-cap .s { display: block; font-weight: 450; font-size: 16px; color: #c9d4e6; margin-top: 3px; }
  #tmov-cur { position: fixed; left: 0; top: 0; z-index: 2147483647; width: 30px; height: 30px; pointer-events: none;
    transition: transform .58s cubic-bezier(.45,0,.2,1); transform: translate(1500px, 700px); filter: drop-shadow(0 3px 6px rgba(0,0,0,.35)); }
  .tmov-rip { position: fixed; z-index: 2147483645; width: 18px; height: 18px; margin: -9px 0 0 -9px; border-radius: 50%;
    border: 3px solid #2a78d6; background: rgba(42,120,214,.18); pointer-events: none; animation: tmrip .65s ease-out forwards; }
  @keyframes tmrip { from { transform: scale(.4); opacity: 1 } to { transform: scale(3.4); opacity: 0 } }
  #root { transition: transform 1s cubic-bezier(.45,0,.2,1); will-change: transform; }
  #tmov-tl { position: fixed; top: 74px; left: 50%; transform: translateX(-50%); z-index: 2147483646; padding: 7px 16px; border-radius: 999px;
    background: rgba(11,26,51,.88); color: #fff; font: 600 15px Inter, "Segoe UI", sans-serif; opacity: 0; transition: opacity .3s; pointer-events: none; }
  #tmov-tl.on { opacity: 1; }`;
  const leaf = '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 20A7 7 0 0 1 9.8 6.1C15.5 5 17 4.48 19 2c1 2 2 4.18 2 8 0 5.5-4.78 10-10 10Z"/><path d="M2 21c0-3 1.85-5.36 5.08-6C9.5 14.52 12 13 13 12"/></svg>';
  const arrow = '<svg width="30" height="30" viewBox="0 0 24 24"><path d="M4 2.5 L4 20 L8.6 15.6 L11.6 22 L14.4 20.8 L11.5 14.6 L17.8 14.6 Z" fill="#fff" stroke="#0b1a33" stroke-width="1.4" stroke-linejoin="round"/></svg>';
  function mount() {
    if (document.getElementById('tmov-cap')) return;
    const st = document.createElement('style'); st.textContent = css; document.head.appendChild(st);
    const cap = document.createElement('div'); cap.id = 'tmov-cap'; cap.innerHTML = `<div class="m">${leaf}</div><div><span class="t"></span><span class="s"></span></div>`;
    const cur = document.createElement('div'); cur.id = 'tmov-cur'; cur.innerHTML = arrow;
    const tl = document.createElement('div'); tl.id = 'tmov-tl'; tl.textContent = '⏩  Waiting time shortened';
    document.body.append(cap, cur, tl);
    if (window.__curPos) cur.style.transform = `translate(${window.__curPos[0]}px, ${window.__curPos[1]}px)`;
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount); else mount();
  window.__cap = (t, s) => {
    mount();
    const c = document.getElementById('tmov-cap');
    c.querySelector('.t').textContent = t; const sub = c.querySelector('.s'); sub.textContent = s || ''; sub.style.display = s ? 'block' : 'none';
    c.classList.add('on');
  };
  window.__capOff = () => document.getElementById('tmov-cap')?.classList.remove('on');
  window.__cur = (x, y, instant) => {
    mount(); window.__curPos = [x, y];
    const c = document.getElementById('tmov-cur');
    if (instant) { c.style.transition = 'none'; c.style.transform = `translate(${x}px, ${y}px)`; void c.offsetWidth; c.style.transition = ''; }
    else c.style.transform = `translate(${x}px, ${y}px)`;
  };
  window.__curHide = (h) => { const c = document.getElementById('tmov-cur'); if (c) c.style.opacity = h ? '0' : '1'; };
  window.__rip = (x, y) => { const r = document.createElement('div'); r.className = 'tmov-rip'; r.style.left = x + 'px'; r.style.top = y + 'px'; document.body.appendChild(r); setTimeout(() => r.remove(), 800); };
  window.__zoom = (s, x, y) => {
    const r = document.getElementById('root'); if (!r) return;
    if (s === 1) { r.style.transform = ''; return; }
    r.style.transformOrigin = `${x}px ${y}px`; r.style.transform = `scale(${s})`;
  };
  window.__tl = (on) => { mount(); document.getElementById('tmov-tl').classList.toggle('on', !!on); };
})();
