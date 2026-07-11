/**
 * Rythmify Dashboard — Interactive JS
 * Dark theme enhancement layer with toasts, keyboard shortcuts, and UX polish.
 */

/* ── Toast notification system ─────────────────────────────────────────── */

const Toast = (() => {
  let container = document.getElementById('toast-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toast-container';
    container.className = 'toast-container';
    document.body.appendChild(container);
  }

  const icons = {
    gold:    '✨',
    success: '✓',
    error:   '✗',
    info:    'ℹ',
    warning: '⚠',
  };

  function show(message, type = 'info', duration = 4000) {
    const el = document.createElement('div');
    el.className = `toast ${type}`;
    el.innerHTML = `
      <span class="toast-icon">${icons[type] || icons.info}</span>
      <span class="toast-body">${escapeHtml(message)}</span>
      <button class="toast-close" onclick="this.closest('.toast').remove()" aria-label="Dismiss">&times;</button>
    `;
    container.appendChild(el);
    // Trigger animation
    requestAnimationFrame(() => el.classList.add('show'));

    if (duration > 0) {
      setTimeout(() => {
        el.classList.remove('show');
        setTimeout(() => el.remove(), 400);
      }, duration);
    }
    return el;
  }

  function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  return { show };
})();


/* ── Keyboard shortcuts ────────────────────────────────────────────────── */

const Keybinds = (() => {
  const binds = new Map();

  function on(keyCombo, handler, description) {
    binds.set(keyCombo, { handler, description });
  }

  document.addEventListener('keydown', (e) => {
    // Don't trigger in input fields
    if (e.target.matches('input, textarea, select, [contenteditable]')) return;

    const parts = [];
    if (e.ctrlKey || e.metaKey) parts.push('Ctrl');
    if (e.shiftKey) parts.push('Shift');
    if (e.altKey) parts.push('Alt');
    parts.push(e.key.length === 1 ? e.key.toUpperCase() : e.key);

    const combo = parts.join('+');
    const bind = binds.get(combo);
    if (bind) {
      e.preventDefault();
      bind.handler(e);
    }
  });

  return { on, binds };
})();


/* ── Keyboard shortcut defaults ────────────────────────────────────────── */

Keybinds.on('r', () => {
  document.querySelector('[data-shortcut="refresh"]')?.click() || location.reload();
}, 'Refresh page');

Keybinds.on('/', () => {
  const input = document.querySelector('input[type="text"], input[placeholder*="Search" i]');
  if (input) { input.focus(); input.select(); }
}, 'Focus search');

Keybinds.on('Escape', () => {
  // Close any open modals / popups
  document.querySelectorAll('.modal, .popup, .dropdown').forEach(el => el.remove());
  // Remove focus from inputs
  if (document.activeElement?.matches('input, textarea')) {
    document.activeElement.blur();
  }
}, 'Close modals / blur input');

Keybinds.on('?', () => {
  const shortcuts = [...Keybinds.binds.entries()]
    .map(([combo, bind]) => `<b>${combo}</b> — ${bind.description}`)
    .join('<br>');
  Toast.show(
    `<div style="font-size:0.9rem"><strong>⌨ Keyboard Shortcuts</strong><br><br>${shortcuts}</div>`,
    'info',
    6000
  );
}, 'Show keyboard shortcuts');


/* ── Theme toggle ──────────────────────────────────────────────────────── */

const ThemeManager = (() => {
  let isDark = true;

  function toggle() {
    isDark = !isDark;
    document.documentElement.style.filter = isDark ? 'none' : 'invert(1) hue-rotate(180deg)';
    Toast.show(isDark ? '🌙 Dark mode' : '☀️ Light mode', 'gold');
  }

  return { toggle };
})();


/* ── Auto-refresh ──────────────────────────────────────────────────────── */

class AutoRefresh {
  constructor(intervalMs = 30000) {
    this.interval = intervalMs;
    this._timer = null;
    this._started = false;
  }

  start() {
    if (this._started) return;
    this._started = true;
    this._tick();
  }

  stop() {
    this._started = false;
    if (this._timer) { clearTimeout(this._timer); this._timer = null; }
  }

  _tick() {
    if (!this._started) return;
    this._timer = setTimeout(() => {
      if (document.hidden) {
        // Page not visible — skip this refresh, try later
        this._tick();
        return;
      }
      this._refresh();
    }, this.interval);
  }

  async _refresh() {
    try {
      const resp = await fetch(window.location.href, { headers: { 'X-Requested-With': 'XMLHttpRequest' } });
      if (resp.ok) {
        // Reload the page to get fresh server-rendered content
        location.reload();
      }
    } catch (e) {
      // Ignore fetch errors — the page will reload via normal means
    }
  }
}


/* ── Server interaction helpers ────────────────────────────────────────── */

async function api(endpoint, options = {}) {
  try {
    const resp = await fetch(endpoint, {
      headers: { 'Content-Type': 'application/json', ...options.headers },
      ...options,
    });
    const data = await resp.json();
    if (!data.success) {
      Toast.show(data.error || 'Request failed', 'error');
    }
    return data;
  } catch (e) {
    Toast.show(`Network error: ${e.message}`, 'error');
    return { success: false, error: e.message };
  }
}


/* ── DOMContentLoaded initializer ──────────────────────────────────────── */

document.addEventListener('DOMContentLoaded', () => {
  // Animate cards with staggered delay
  document.querySelectorAll('.card, .guild-card, [data-animate]').forEach((el, i) => {
    el.style.animationDelay = `${i * 80}ms`;
    el.classList.add('animate-fade');
  });

  // Init auto-refresh for dashboard pages (not guild detail pages)
  if (document.querySelector('[data-auto-refresh]')) {
    const refresh = new AutoRefresh(parseInt(document.querySelector('[data-auto-refresh]').dataset.autoRefresh, 10) || 30000);
    refresh.start();
  }

  // Gold shimmer on logo/title
  const logo = document.querySelector('.logo, .brand, h1');
  if (logo) {
    logo.classList.add('gold-text');
  }
});


/* ── Expose to global scope ────────────────────────────────────────────── */
window.Toast = Toast;
window.Keybinds = Keybinds;
window.ThemeManager = ThemeManager;
window.AutoRefresh = AutoRefresh;
window.api = api;
