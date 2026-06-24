/* ==========================================
   Workbench — Theme Manager
   Manual light/dark toggle, persisted in localStorage
   ========================================== */

const Theme = (() => {
  const LS_KEY = 'wb_theme';
  const linkLight = document.getElementById('theme-light');
  const linkDark = document.getElementById('theme-dark');

  function apply(name) {
    const html = document.documentElement;
    html.setAttribute('data-theme', name);
    if (linkLight) linkLight.disabled = name !== 'light';
    if (linkDark) linkDark.disabled = name !== 'dark';
    localStorage.setItem(LS_KEY, name);
  }

  function get() {
    return document.documentElement.getAttribute('data-theme') || 'dark';
  }

  function toggle() {
    apply(get() === 'dark' ? 'light' : 'dark');
  }

  function init() {
    const saved = localStorage.getItem(LS_KEY) || 'dark';
    apply(saved);
    const btn = document.getElementById('theme-toggle');
    if (btn) btn.addEventListener('click', toggle);
  }

  return { init, get, toggle, apply };
})();
