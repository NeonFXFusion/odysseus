import * as Modals from './modalManager.js';
import { makeWindowDraggable } from './windowDrag.js';
import settingsModule from './settings.js';
import uiModule from './ui.js';

const API_BASE = window.location.origin;
const IG_ICON = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="20" height="20" rx="5"/><circle cx="12" cy="12" r="4"/><circle cx="17.5" cy="6.5" r="1"/></svg>';

let _open = false;
let _accounts = [];
let _account = '';
let _threads = [];
let _activeThreadId = '';
let _pendingThreadId = '';
let _searchTimer = null;

function esc(value) {
  return String(value || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function linkify(text) {
  return esc(text).replace(/(https?:\/\/[^\s<]+)/g, '<a href="$1" target="_blank" rel="noopener noreferrer">$1</a>');
}

function _installStyles() {
  if (document.getElementById('instagram-panel-styles')) return;
  const style = document.createElement('style');
  style.id = 'instagram-panel-styles';
  style.textContent = `
    #instagram-modal .instagram-modal-content {
      width: min(920px, 94vw);
      height: min(760px, 88vh);
      background: var(--bg);
      color: var(--fg);
      overflow: hidden;
      display: flex;
      flex-direction: column;
    }
    .instagram-shell { display: grid; grid-template-columns: minmax(250px, 330px) minmax(0, 1fr); gap: 0; min-height: 0; flex: 1; }
    .instagram-sidebar { border-right: 1px solid var(--border); display: flex; flex-direction: column; min-width: 0; min-height: 0; }
    .instagram-toolbar { display: flex; gap: 6px; padding: 8px; border-bottom: 1px solid var(--border); align-items: center; }
    .instagram-input, .instagram-select, .instagram-reply { background: color-mix(in srgb, var(--fg) 5%, transparent); color: var(--fg); border: 1px solid var(--border); border-radius: 6px; padding: 7px 8px; font: inherit; min-width: 0; }
    .instagram-list { overflow: auto; padding: 6px; }
    .instagram-thread { width: 100%; text-align: left; border: 1px solid transparent; background: transparent; color: var(--fg); border-radius: 7px; padding: 8px; cursor: pointer; display: block; }
    .instagram-thread:hover { background: color-mix(in srgb, var(--fg) 6%, transparent); }
    .instagram-thread.active { border-color: color-mix(in srgb, var(--accent, var(--red)) 45%, transparent); background: color-mix(in srgb, var(--accent, var(--red)) 10%, transparent); }
    .instagram-thread-title { display: flex; gap: 6px; align-items: center; font-size: 12px; font-weight: 650; min-width: 0; }
    .instagram-thread-sub { font-size: 11px; opacity: .56; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; margin-top: 3px; }
    .instagram-reader { display: flex; flex-direction: column; min-width: 0; min-height: 0; }
    .instagram-reader-head { padding: 10px 12px; border-bottom: 1px solid var(--border); display: flex; align-items: center; gap: 8px; min-height: 46px; }
    #instagram-back { display: none; }
    .instagram-messages { flex: 1; overflow: auto; padding: 12px; display: flex; flex-direction: column; gap: 8px; }
    .instagram-empty { opacity: .55; font-size: 12px; text-align: center; padding: 30px 18px; line-height: 1.45; }
    .instagram-msg { max-width: 78%; padding: 8px 10px; border: 1px solid var(--border); border-radius: 8px; background: color-mix(in srgb, var(--fg) 4%, transparent); }
    .instagram-msg.mine { align-self: flex-end; background: color-mix(in srgb, var(--accent, var(--red)) 13%, transparent); border-color: color-mix(in srgb, var(--accent, var(--red)) 28%, var(--border)); }
    .instagram-msg-meta { font-size: 10px; opacity: .5; margin-bottom: 4px; display: flex; gap: 6px; flex-wrap: wrap; }
    .instagram-msg-text { font-size: 13px; line-height: 1.42; white-space: pre-wrap; overflow-wrap: anywhere; }
    .instagram-tags { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 5px; }
    .instagram-tag { font-size: 9px; text-transform: uppercase; letter-spacing: .04em; border: 1px solid color-mix(in srgb, var(--accent, var(--red)) 38%, transparent); color: var(--accent, var(--red)); border-radius: 4px; padding: 1px 5px; background: color-mix(in srgb, var(--accent, var(--red)) 9%, transparent); }
    .instagram-replybar { display: flex; gap: 8px; border-top: 1px solid var(--border); padding: 8px; align-items: flex-end; }
    .instagram-reply { resize: vertical; min-height: 38px; max-height: 140px; flex: 1; }
    .instagram-btn { border: 1px solid var(--border); color: var(--fg); background: color-mix(in srgb, var(--fg) 5%, transparent); border-radius: 6px; padding: 7px 9px; cursor: pointer; display: inline-flex; align-items: center; gap: 5px; }
    .instagram-btn.primary { background: var(--accent, var(--red)); border-color: var(--accent, var(--red)); color: #fff; font-weight: 650; }
    .instagram-btn:disabled { opacity: .45; cursor: default; }
    @media (max-width: 760px) {
      #instagram-modal .instagram-modal-content { width: 100vw; height: 100vh; max-height: 100vh; border-radius: 0; }
      .instagram-shell { grid-template-columns: 1fr; }
      .instagram-sidebar.thread-open { display: none; }
      .instagram-reader:not(.thread-open) { display: none; }
      #instagram-back { display: inline-flex; }
      .instagram-msg { max-width: 92%; }
    }
  `;
  document.head.appendChild(style);
}

function _openSettingsIntegrations() {
  if (settingsModule?.open) settingsModule.open('integrations');
  else document.getElementById('settings-modal')?.classList.remove('hidden');
}

function _accountParam() {
  return _account ? `account=${encodeURIComponent(_account)}` : '';
}

function _accountSelectHtml() {
  return `<select id="instagram-account" class="instagram-select" title="Instagram account">${_accounts.map(a => {
    const value = a.id || a.username || a.name || '';
    return `<option value="${esc(value)}" ${value === _account ? 'selected' : ''}>${esc(a.username ? '@' + a.username : a.name || value)}</option>`;
  }).join('')}</select>`;
}

function _tagHtml(tags) {
  if (!tags || !tags.length) return '';
  return `<div class="instagram-tags">${tags.map(t => `<span class="instagram-tag">${esc(t)}</span>`).join('')}</div>`;
}

function _previewThread(thread) {
  const msg = (thread.messages || [])[0] || {};
  return msg.text || thread.thread_id || '';
}

function _renderThreadList() {
  const list = document.getElementById('instagram-thread-list');
  if (!list) return;
  if (!_threads.length) {
    list.innerHTML = '<div class="instagram-empty">No Instagram threads found.</div>';
    return;
  }
  list.innerHTML = _threads.map(thread => {
    const title = thread.thread_title || '(untitled thread)';
    const users = (thread.users || []).map(u => u.username).filter(Boolean).join(', ');
    const active = String(thread.thread_id) === String(_activeThreadId);
    return `<button class="instagram-thread ${active ? 'active' : ''}" data-thread-id="${esc(thread.thread_id)}">
      <div class="instagram-thread-title"><span style="min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${esc(title)}</span></div>
      <div class="instagram-thread-sub">${esc(users || _previewThread(thread))}</div>
      ${_tagHtml(thread.tags || [])}
    </button>`;
  }).join('');
  list.querySelectorAll('.instagram-thread').forEach(btn => {
    btn.addEventListener('click', () => _readThread(btn.dataset.threadId));
  });
}

function _setReaderEmpty(message) {
  const head = document.getElementById('instagram-reader-head');
  const msgs = document.getElementById('instagram-messages');
  const reply = document.getElementById('instagram-replybar');
  if (head) head.innerHTML = `<span style="opacity:.65">${IG_ICON}</span><strong>Instagram</strong>`;
  if (msgs) msgs.innerHTML = `<div class="instagram-empty">${message}</div>`;
  if (reply) reply.style.display = 'none';
}

function _renderThread(thread, accountUsername = '') {
  _activeThreadId = thread.thread_id || '';
  _renderThreadList();
  const head = document.getElementById('instagram-reader-head');
  const msgs = document.getElementById('instagram-messages');
  const reply = document.getElementById('instagram-replybar');
  if (head) {
    const users = (thread.users || []).map(u => u.username).filter(Boolean).join(', ');
    head.innerHTML = `<button class="instagram-btn" id="instagram-back">Back</button><span style="opacity:.65">${IG_ICON}</span><div style="min-width:0;flex:1;"><div style="font-size:13px;font-weight:700;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${esc(thread.thread_title || 'Instagram thread')}</div><div style="font-size:11px;opacity:.55;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${esc(users || thread.thread_id || '')}</div></div>${_tagHtml(thread.tags || [])}`;
    head.querySelector('#instagram-back')?.addEventListener('click', () => {
      document.querySelector('.instagram-sidebar')?.classList.remove('thread-open');
      document.querySelector('.instagram-reader')?.classList.remove('thread-open');
    });
  }
  if (msgs) {
    const own = String(accountUsername || _accounts.find(a => (a.id || a.username || a.name) === _account)?.username || '').toLowerCase();
    const messages = [...(thread.messages || [])].reverse();
    msgs.innerHTML = messages.length ? messages.map(msg => {
      const from = msg.from_username || msg.from_user_id || '';
      const mine = own && String(from).toLowerCase() === own;
      return `<div class="instagram-msg ${mine ? 'mine' : ''}">
        <div class="instagram-msg-meta"><span>${esc(from || (mine ? 'me' : 'unknown'))}</span><span>${esc(msg.timestamp || '')}</span></div>
        <div class="instagram-msg-text">${linkify(msg.text || '')}</div>
        ${_tagHtml(msg.tags || [])}
        ${msg.triage_reason ? `<div style="font-size:10px;opacity:.55;margin-top:4px;">${esc(msg.triage_reason)}</div>` : ''}
      </div>`;
    }).join('') : '<div class="instagram-empty">No messages in this thread.</div>';
    msgs.scrollTop = msgs.scrollHeight;
  }
  if (reply) reply.style.display = 'flex';
  document.querySelector('.instagram-sidebar')?.classList.add('thread-open');
  document.querySelector('.instagram-reader')?.classList.add('thread-open');
}

async function _loadAccounts() {
  const res = await fetch(`${API_BASE}/api/instagram/accounts`, { credentials: 'same-origin' });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Failed to load Instagram accounts');
  const data = await res.json();
  _accounts = data.accounts || [];
  const def = _accounts.find(a => a.is_default) || _accounts[0] || null;
  _account = _account || (def ? (def.id || def.username || def.name || '') : '');
}

async function _loadThreads() {
  const list = document.getElementById('instagram-thread-list');
  if (list) list.innerHTML = '<div class="instagram-empty">Loading threads...</div>';
  const query = _accountParam();
  const res = await fetch(`${API_BASE}/api/instagram/threads?max_results=30${query ? '&' + query : ''}`, { credentials: 'same-origin' });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Failed to load Instagram threads');
  const data = await res.json();
  _threads = data.threads || [];
  _renderThreadList();
  if (_pendingThreadId) {
    const id = _pendingThreadId;
    _pendingThreadId = '';
    await _readThread(id);
  } else if (!_activeThreadId && _threads[0]) {
    await _readThread(_threads[0].thread_id);
  } else if (!_threads.length) {
    _setReaderEmpty('Select an Instagram thread.');
  }
}

async function _searchThreads(q) {
  if (!q.trim()) {
    await _loadThreads();
    return;
  }
  const list = document.getElementById('instagram-thread-list');
  if (list) list.innerHTML = '<div class="instagram-empty">Searching...</div>';
  const params = new URLSearchParams({ q: q.trim(), max_threads: '30', max_messages_per_thread: '30' });
  if (_account) params.set('account', _account);
  const res = await fetch(`${API_BASE}/api/instagram/search?${params.toString()}`, { credentials: 'same-origin' });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Search failed');
  const data = await res.json();
  const byThread = new Map();
  for (const msg of data.messages || []) {
    const id = msg.thread_id || '';
    if (!id) continue;
    if (!byThread.has(id)) {
      byThread.set(id, {
        thread_id: id,
        thread_title: msg.thread_title || id,
        users: msg.from_username ? [{ username: msg.from_username }] : [],
        messages: [msg],
        tags: msg.tags || [],
      });
    }
  }
  _threads = [...byThread.values()];
  _renderThreadList();
  _setReaderEmpty(_threads.length ? 'Select a matching thread.' : 'No matching Instagram messages.');
}

async function _readThread(threadId) {
  if (!threadId) return;
  const msgs = document.getElementById('instagram-messages');
  if (msgs) msgs.innerHTML = '<div class="instagram-empty">Loading thread...</div>';
  const params = new URLSearchParams({ max_messages: '80' });
  if (_account) params.set('account', _account);
  const res = await fetch(`${API_BASE}/api/instagram/threads/${encodeURIComponent(threadId)}?${params.toString()}`, { credentials: 'same-origin' });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Failed to read thread');
  const data = await res.json();
  const account = _accounts.find(a => (a.id || a.username || a.name) === _account);
  _renderThread(data.thread, account?.username || '');
}

async function _sendReply() {
  const textarea = document.getElementById('instagram-reply');
  const send = document.getElementById('instagram-send');
  const text = textarea?.value?.trim() || '';
  if (!_activeThreadId || !text) return;
  send.disabled = true;
  try {
    const res = await fetch(`${API_BASE}/api/instagram/send`, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ account: _account || undefined, thread_id: _activeThreadId, text }),
    });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Send failed');
    textarea.value = '';
    uiModule?.showToast?.('Instagram message sent');
    await _readThread(_activeThreadId);
  } catch (err) {
    uiModule?.showError?.(err.message || 'Send failed');
  } finally {
    send.disabled = false;
  }
}

function _renderShell() {
  const modal = document.getElementById('instagram-modal');
  if (!modal) return;
  const content = modal.querySelector('.instagram-modal-content');
  if (!_accounts.length) {
    content.innerHTML = `
      <div class="modal-header">
        <h4 style="display:flex;align-items:center;gap:6px;">${IG_ICON} Instagram</h4>
        <span style="flex:1"></span>
        <button class="close-btn" id="instagram-close">x</button>
      </div>
      <div class="modal-body" style="padding:18px;">
        <div class="instagram-empty" style="border:1px solid var(--border);border-radius:8px;">
          No Instagram account is configured.<br>
          <button class="instagram-btn primary" id="instagram-settings" style="margin-top:10px;">Open Integrations</button>
        </div>
      </div>`;
    content.querySelector('#instagram-close')?.addEventListener('click', closeInstagramPanel);
    content.querySelector('#instagram-settings')?.addEventListener('click', _openSettingsIntegrations);
    return;
  }
  content.innerHTML = `
    <div class="modal-header">
      <h4 style="display:flex;align-items:center;gap:6px;">${IG_ICON} Instagram</h4>
      <span style="flex:1"></span>
      ${_accountSelectHtml()}
      <button class="instagram-btn" id="instagram-refresh" title="Refresh">Refresh</button>
      <button class="close-btn" id="instagram-close">x</button>
    </div>
    <div class="instagram-shell">
      <div class="instagram-sidebar">
        <div class="instagram-toolbar">
          <input id="instagram-search" class="instagram-input" placeholder="Search DMs" style="flex:1;">
        </div>
        <div id="instagram-thread-list" class="instagram-list"></div>
      </div>
      <div class="instagram-reader" id="instagram-reader">
        <div class="instagram-reader-head" id="instagram-reader-head"></div>
        <div class="instagram-messages" id="instagram-messages"></div>
        <div class="instagram-replybar" id="instagram-replybar" style="display:none;">
          <textarea id="instagram-reply" class="instagram-reply" placeholder="Reply..."></textarea>
          <button class="instagram-btn primary" id="instagram-send">Send</button>
        </div>
      </div>
    </div>`;
  content.querySelector('#instagram-close')?.addEventListener('click', closeInstagramPanel);
  content.querySelector('#instagram-refresh')?.addEventListener('click', () => _loadThreads().catch(err => uiModule?.showError?.(err.message)));
  content.querySelector('#instagram-account')?.addEventListener('change', (e) => {
    _account = e.target.value || '';
    _activeThreadId = '';
    _loadThreads().catch(err => uiModule?.showError?.(err.message));
  });
  content.querySelector('#instagram-search')?.addEventListener('input', (e) => {
    clearTimeout(_searchTimer);
    _searchTimer = setTimeout(() => _searchThreads(e.target.value || '').catch(err => uiModule?.showError?.(err.message)), 250);
  });
  content.querySelector('#instagram-send')?.addEventListener('click', _sendReply);
  content.querySelector('#instagram-reply')?.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') _sendReply();
  });
}

export async function openInstagramPanel(opts = {}) {
  _pendingThreadId = opts.threadId || opts.thread_id || '';
  if (Modals.isRegistered('instagram-modal')) {
    Modals.restore('instagram-modal');
    if (_pendingThreadId) _readThread(_pendingThreadId).catch(err => uiModule?.showError?.(err.message));
    return;
  }
  _installStyles();
  _open = true;
  const modal = document.createElement('div');
  modal.id = 'instagram-modal';
  modal.className = 'modal';
  modal.innerHTML = `<div class="modal-content instagram-modal-content"><div class="instagram-empty">Loading Instagram...</div></div>`;
  document.body.appendChild(modal);
  Modals.register('instagram-modal', {
    railBtnId: ['rail-instagram', 'instagram-section-title'],
    restoreFn: () => { modal.classList.remove('hidden'); },
    closeFn: closeInstagramPanel,
  });
  const content = modal.querySelector('.instagram-modal-content');
  makeWindowDraggable(modal, { content, header: content, skipSelector: 'button, input, select, textarea, a' });
  modal.addEventListener('click', (e) => {
    if (e.target === modal) closeInstagramPanel();
  });
  try {
    await _loadAccounts();
    _renderShell();
    await _loadThreads();
  } catch (err) {
    _accounts = [];
    _renderShell();
    uiModule?.showError?.(err.message || 'Instagram failed');
  }
}

export function closeInstagramPanel() {
  const modal = document.getElementById('instagram-modal');
  _open = false;
  _activeThreadId = '';
  if (!modal) return;
  Modals.unregister?.('instagram-modal');
  const content = modal.querySelector('.modal-content');
  if (content) {
    content.classList.add('modal-closing');
    content.addEventListener('animationend', () => modal.remove(), { once: true });
    setTimeout(() => { if (modal.parentElement) modal.remove(); }, 250);
  } else {
    modal.remove();
  }
}

export function isOpen() {
  return _open;
}

export function init() {
  document.getElementById('instagram-section-title')?.addEventListener('click', () => openInstagramPanel());
}

export default { init, openInstagramPanel, closeInstagramPanel, isOpen };
