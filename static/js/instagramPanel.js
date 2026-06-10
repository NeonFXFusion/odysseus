import * as Modals from './modalManager.js';
import { makeWindowDraggable } from './windowDrag.js';
import settingsModule from './settings.js';
import uiModule from './ui.js';

const API_BASE = window.location.origin;
const IG_ICON = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="20" height="20" rx="5"/><circle cx="12" cy="12" r="4"/><circle cx="17.5" cy="6.5" r="1"/></svg>';
const DM_ICON = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H8l-5 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>';
const STORY_ICON = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>';
const GRID_ICON = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>';
const PLUS_ICON = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="16"/><line x1="8" y1="12" x2="16" y2="12"/></svg>';
const REFRESH_ICON = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 0 1-15.5 6.3L3 16"/><path d="M3 21v-5h5"/><path d="M3 12A9 9 0 0 1 18.5 5.7L21 8"/><path d="M21 3v5h-5"/></svg>';

let _open = false;
let _accounts = [];
let _account = '';
let _threads = [];
let _stories = [];
let _posts = [];
let _activeThreadId = '';
let _pendingThreadId = '';
let _activeTab = 'dm';
let _searchTimer = null;
let _mediaSeq = 0;
let _mediaStore = new Map();
let _mediaHydrationChain = Promise.resolve();

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
      width: min(1060px, 94vw);
      height: min(820px, 90vh);
      background: var(--bg);
      color: var(--fg);
      overflow: hidden;
      display: flex;
      flex-direction: column;
    }
    #instagram-modal .modal-header { border-bottom: 1px solid var(--border); flex-shrink: 0; }
    .instagram-account-wrap { display:flex; align-items:center; gap:8px; min-width:0; }
    .instagram-account-label { font-size:10px; opacity:.55; text-transform:uppercase; letter-spacing:.04em; }
    .instagram-select, .instagram-input, .instagram-textarea {
      background: color-mix(in srgb, var(--fg) 5%, transparent);
      color: var(--fg);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 7px 8px;
      font: inherit;
      min-width: 0;
    }
    .instagram-select { max-width: 210px; }
    .instagram-tabs { padding: 8px 10px 0; flex-shrink: 0; }
    .instagram-tab-panels { flex:1; min-height:0; overflow:hidden; display:flex; flex-direction:column; }
    .instagram-tab-panel { flex:1; min-height:0; overflow:hidden; display:none; }
    .instagram-tab-panel.active { display:flex; }
    .instagram-shell { display:grid; grid-template-columns:minmax(260px, 340px) minmax(0, 1fr); min-height:0; flex:1; }
    .instagram-sidebar { border-right:1px solid var(--border); display:flex; flex-direction:column; min-width:0; min-height:0; }
    .instagram-toolbar { display:flex; gap:6px; padding:8px; border-bottom:1px solid var(--border); align-items:center; }
    .instagram-list { overflow:auto; padding:6px; }
    .instagram-thread {
      width:100%;
      border:1px solid transparent;
      background:transparent;
      color:var(--fg);
      border-radius:7px;
      padding:8px;
      cursor:pointer;
      text-align:left;
      display:grid;
      grid-template-columns:32px minmax(0,1fr);
      gap:10px;
      align-items:center;
    }
    .instagram-thread + .instagram-thread { margin-top:3px; }
    .instagram-thread:hover { background: color-mix(in srgb, var(--fg) 6%, transparent); }
    .instagram-thread.active {
      border-color: color-mix(in srgb, var(--accent, var(--red)) 44%, transparent);
      background: color-mix(in srgb, var(--accent, var(--red)) 10%, transparent);
    }
    .instagram-avatar {
      width:32px;
      height:32px;
      border-radius:50%;
      display:inline-flex;
      align-items:center;
      justify-content:center;
      color:#fff;
      background:linear-gradient(135deg,#d62976,#f77737);
      font-size:11px;
      font-weight:700;
      flex-shrink:0;
      overflow:hidden;
    }
    .instagram-avatar img { width:100%; height:100%; object-fit:cover; display:block; border-radius:inherit; }
    .instagram-thread-main { min-width:0; display:flex; flex-direction:column; gap:3px; }
    .instagram-thread-title { font-size:12px; font-weight:650; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; line-height:1.25; }
    .instagram-thread-users { display:flex; gap:6px; align-items:center; min-width:0; font-size:11px; opacity:.66; overflow:hidden; white-space:nowrap; }
    .instagram-thread-user { min-width:0; overflow:hidden; text-overflow:ellipsis; }
    .instagram-thread-sub { font-size:11px; opacity:.5; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; margin-top:3px; }
    .instagram-reader { display:flex; flex-direction:column; min-width:0; min-height:0; background:color-mix(in srgb, var(--fg) 1.5%, transparent); }
    .instagram-reader-head { border-bottom:1px solid var(--border); flex-shrink:0; }
    .instagram-reader-head .email-reader-header { border-bottom:0; }
    #instagram-back { display:none; }
    .instagram-messages { flex:1; overflow:auto; padding:12px 14px; display:flex; flex-direction:column; gap:10px; }
    .instagram-empty { opacity:.55; font-size:12px; text-align:center; padding:30px 18px; line-height:1.45; }
    .instagram-msg-row { display:grid; grid-template-columns:32px minmax(0, 1fr); gap:8px; max-width:82%; align-self:flex-start; }
    .instagram-msg-row.mine { grid-template-columns:minmax(0, 1fr) 32px; align-self:flex-end; }
    .instagram-msg-row.mine .instagram-avatar { grid-column:2; grid-row:1; }
    .instagram-msg-row.mine .instagram-msg-card { grid-column:1; grid-row:1; }
    .instagram-msg-card {
      border:1px solid var(--border);
      border-radius:8px;
      background:var(--bg);
      padding:8px 10px;
      min-width:0;
      box-shadow:0 1px 0 rgba(0,0,0,.04);
    }
    .instagram-msg-row.mine .instagram-msg-card {
      background:color-mix(in srgb, var(--accent, var(--red)) 12%, var(--bg));
      border-color:color-mix(in srgb, var(--accent, var(--red)) 30%, var(--border));
    }
    .instagram-msg-meta { font-size:10px; opacity:.56; margin-bottom:5px; display:flex; gap:9px; align-items:center; flex-wrap:wrap; }
    .instagram-msg-user { font-weight:700; opacity:.88; margin-right:1px; }
    .instagram-msg-time { opacity:.8; }
    .instagram-msg-text { font-size:13px; line-height:1.44; white-space:pre-wrap; overflow-wrap:anywhere; }
    .instagram-tags { display:flex; flex-wrap:wrap; gap:4px; margin-top:6px; }
    .instagram-tag { font-size:9px; text-transform:uppercase; letter-spacing:.04em; border:1px solid color-mix(in srgb, var(--accent, var(--red)) 38%, transparent); color:var(--accent, var(--red)); border-radius:4px; padding:1px 5px; background:color-mix(in srgb, var(--accent, var(--red)) 9%, transparent); }
    .instagram-replybar { display:flex; gap:8px; border-top:1px solid var(--border); padding:8px; align-items:flex-end; background:var(--bg); flex-shrink:0; }
    .instagram-reply { resize:vertical; min-height:38px; max-height:140px; flex:1; }
    .instagram-btn {
      border:1px solid var(--border);
      color:var(--fg);
      background:color-mix(in srgb, var(--fg) 5%, transparent);
      border-radius:6px;
      padding:7px 9px;
      cursor:pointer;
      display:inline-flex;
      align-items:center;
      justify-content:center;
      gap:5px;
      font:inherit;
    }
    .instagram-btn.primary { background:var(--accent, var(--red)); border-color:var(--accent, var(--red)); color:#fff; font-weight:650; }
    .instagram-btn:disabled { opacity:.45; cursor:default; }
    .instagram-media-strip { display:grid; grid-template-columns:repeat(auto-fill,minmax(96px,1fr)); gap:6px; margin-top:8px; }
    .instagram-media-card {
      position:relative;
      border:1px solid var(--border);
      border-radius:7px;
      overflow:hidden;
      background:color-mix(in srgb, var(--fg) 4%, transparent);
      min-height:92px;
      cursor:pointer;
      color:var(--fg);
      padding:0;
      text-align:left;
    }
    .instagram-media-card.loading { opacity:.72; cursor:wait; }
    .instagram-media-card img, .instagram-media-card video { width:100%; height:100%; min-height:92px; max-height:190px; object-fit:cover; display:block; background:#000; }
    .instagram-media-label { position:absolute; left:6px; bottom:6px; font-size:10px; color:#fff; background:rgba(0,0,0,.55); border-radius:4px; padding:2px 5px; max-width:calc(100% - 12px); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
    .instagram-content-panel { flex:1; min-height:0; overflow:auto; padding:10px; display:flex; flex-direction:column; gap:10px; }
    .instagram-content-toolbar { display:flex; gap:8px; align-items:center; flex-wrap:wrap; padding:0 0 2px; }
    .instagram-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(150px,1fr)); gap:8px; }
    .instagram-grid-card { min-height:190px; border-radius:8px; }
    .instagram-grid-card img, .instagram-grid-card video { min-height:190px; height:190px; }
    .instagram-grid-meta { padding:7px; font-size:11px; line-height:1.35; }
    .instagram-create-wrap { width:min(720px,100%); margin:0 auto; display:flex; flex-direction:column; gap:10px; }
    .instagram-create-row { display:grid; grid-template-columns:120px minmax(0,1fr); gap:10px; align-items:start; }
    .instagram-create-row label { font-size:11px; opacity:.62; padding-top:8px; }
    .instagram-textarea { min-height:110px; resize:vertical; }
    .instagram-upload-list { display:flex; gap:6px; flex-wrap:wrap; font-size:11px; opacity:.7; }
    .instagram-upload-pill { border:1px solid var(--border); border-radius:5px; padding:4px 6px; background:color-mix(in srgb, var(--fg) 4%, transparent); }
    .instagram-media-viewer { position:absolute; inset:0; z-index:20; background:rgba(0,0,0,.72); display:flex; align-items:center; justify-content:center; padding:18px; }
    .instagram-media-viewer-card { width:min(920px,96vw); max-height:92vh; background:var(--bg); border:1px solid var(--border); border-radius:8px; display:flex; flex-direction:column; overflow:hidden; color:var(--fg); }
    .instagram-media-viewer-body { display:grid; grid-template-columns:minmax(0,1fr) minmax(220px,300px); min-height:0; }
    .instagram-media-stage { background:#050505; display:flex; align-items:center; justify-content:center; min-height:360px; overflow:hidden; }
    .instagram-media-stage img, .instagram-media-stage video { max-width:100%; max-height:72vh; object-fit:contain; }
    .instagram-media-detail { padding:12px; border-left:1px solid var(--border); overflow:auto; font-size:12px; line-height:1.45; }
    .instagram-resource-row { display:flex; gap:6px; flex-wrap:wrap; margin-top:10px; }
    @media (max-width:760px) {
      #instagram-modal .instagram-modal-content { width:100vw; height:100vh; max-height:100vh; border-radius:0; }
      .instagram-shell { grid-template-columns:1fr; }
      .instagram-sidebar.thread-open { display:none; }
      .instagram-reader:not(.thread-open) { display:none; }
      #instagram-back { display:inline-flex; }
      .instagram-msg-row, .instagram-msg-row.mine { max-width:96%; }
      .instagram-media-viewer-body { grid-template-columns:1fr; }
      .instagram-media-detail { border-left:0; border-top:1px solid var(--border); max-height:180px; }
      .instagram-create-row { grid-template-columns:1fr; gap:4px; }
      .instagram-create-row label { padding-top:0; }
    }
  `;
  document.head.appendChild(style);
}

function _openSettingsIntegrations() {
  if (settingsModule?.open) settingsModule.open('integrations');
  else document.getElementById('settings-modal')?.classList.remove('hidden');
}

async function _fetchJson(url, options = {}) {
  const res = await fetch(url, { credentials: 'same-origin', ...options });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || data.error || data.message || `HTTP ${res.status}`);
  return data;
}

function _accountParam() {
  return _account ? `account=${encodeURIComponent(_account)}` : '';
}

function _currentAccount() {
  return _accounts.find(a => (a.id || a.username || a.name || '') === _account) || _accounts[0] || {};
}

function _currentAccountUsername() {
  return String(_currentAccount().username || '').replace(/^@+/, '');
}

function _accountSelectHtml() {
  return `<div class="instagram-account-wrap"><span class="instagram-account-label">Account</span><select id="instagram-account" class="instagram-select" title="Instagram account">${_accounts.map(a => {
    const value = a.id || a.username || a.name || '';
    return `<option value="${esc(value)}" ${value === _account ? 'selected' : ''}>${esc(a.username ? '@' + a.username : a.name || value)}</option>`;
  }).join('')}</select></div>`;
}

function _tagHtml(tags) {
  if (!tags || !tags.length) return '';
  return `<div class="instagram-tags">${tags.map(t => `<span class="instagram-tag">${esc(t)}</span>`).join('')}</div>`;
}

function _initials(value) {
  const text = String(value || 'IG').replace(/^@+/, '').trim();
  const parts = text.split(/[\s._-]+/).filter(Boolean);
  return (parts[0]?.[0] || 'I').toUpperCase() + (parts[1]?.[0] || parts[0]?.[1] || 'G').toUpperCase();
}

function _normalizeUser(user) {
  if (!user) return null;
  if (typeof user === 'string') return { username: user };
  return user;
}

function _userDisplay(user) {
  const u = _normalizeUser(user) || {};
  return String(u.username || u.full_name || u.id || '').replace(/^@+/, '');
}

function _avatarHtml(user, fallback = 'IG') {
  const u = _normalizeUser(user) || {};
  const label = _userDisplay(u) || fallback;
  const src = u.profile_pic_url || u.profile_pic_url_hd || '';
  return `<span class="instagram-avatar">${src
    ? `<img src="${esc(src)}" alt="${esc(label)}" loading="lazy">`
    : esc(_initials(label))}</span>`;
}

function _threadUsers(thread) {
  return (thread.users || []).map(_normalizeUser).filter(u => u && _userDisplay(u));
}

function _threadTitleFromUsers(users) {
  return users.map(_userDisplay).filter(Boolean).slice(0, 4).join(', ');
}

function _userForMessage(thread, msg) {
  const users = _threadUsers(thread);
  const id = String(msg.from_user_id || '');
  const username = String(msg.from_username || '').replace(/^@+/, '').toLowerCase();
  return users.find(u => String(u.id || '') === id)
    || users.find(u => String(u.username || '').replace(/^@+/, '').toLowerCase() === username)
    || { username: msg.from_username || msg.from_user_id || 'unknown', profile_pic_url: msg.from_profile_pic_url || '' };
}

function _previewThread(thread) {
  const msg = (thread.messages || [])[0] || {};
  if (msg.text) return msg.text;
  if (msg.media_count) return `${msg.media_count} media item${msg.media_count === 1 ? '' : 's'}`;
  return thread.thread_id || '';
}

function _storeMedia(item) {
  const key = `m${++_mediaSeq}`;
  _mediaStore.set(key, item);
  return key;
}

function _isLocalInstagramMediaUrl(value) {
  const text = String(value || '');
  return text.startsWith('/api/instagram/media-file/') || text.startsWith(`${API_BASE}/api/instagram/media-file/`);
}

function _primaryMedia(item) {
  const resources = Array.isArray(item?.resources) ? item.resources : [];
  const first = resources[0] || item || {};
  const firstLocalUrl = first.local_url || '';
  const itemLocalUrl = item?.local_url || '';
  return {
    image: first.local_image_url
      || (String(first.local_content_type || '').startsWith('image/') ? firstLocalUrl : '')
      || (_isLocalInstagramMediaUrl(first.image_url) ? first.image_url : '')
      || item?.local_image_url
      || (String(item?.local_content_type || '').startsWith('image/') ? itemLocalUrl : '')
      || (_isLocalInstagramMediaUrl(item?.image_url) ? item.image_url : '')
      || '',
    video: first.local_video_url
      || (String(first.local_content_type || '').startsWith('video/') ? firstLocalUrl : '')
      || (_isLocalInstagramMediaUrl(first.video_url) ? first.video_url : '')
      || item?.local_video_url
      || (String(item?.local_content_type || '').startsWith('video/') ? itemLocalUrl : '')
      || (_isLocalInstagramMediaUrl(item?.video_url) ? item.video_url : '')
      || '',
  };
}

function _hasLocalMedia(item) {
  const media = _primaryMedia(item);
  return Boolean(media.image || media.video);
}

async function _cacheMediaItem(item) {
  if (!item || _hasLocalMedia(item)) return item;
  const data = await _fetchJson(`${API_BASE}/api/instagram/media/cache`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ account: _account || undefined, media: item }),
  });
  return data.media || item;
}

function _mediaCardInnerHtml(item, { grid = false } = {}) {
  const media = _primaryMedia(item);
  const label = item.kind || item.source || 'media';
  const title = item.title || item.caption || item.code || label;
  const visual = media.video
    ? `<video src="${esc(media.video)}" muted playsinline preload="metadata" poster="${esc(media.image)}"></video>`
    : media.image
      ? `<img src="${esc(media.image)}" alt="${esc(title)}" loading="lazy">`
      : `<div class="instagram-empty" style="padding:18px 8px;">Preparing media...</div>`;
  const meta = grid ? `<div class="instagram-grid-meta">
    <div style="font-weight:650;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${esc(title || label)}</div>
    <div style="opacity:.55;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${esc(item.username ? '@' + item.username : item.taken_at || item.pk || '')}</div>
  </div>` : '';
  return `${visual}
    <span class="instagram-media-label">${esc(label)}${item.resources?.length ? ` · ${item.resources.length}` : ''}</span>
    ${meta}`;
}

function _mediaCardHtml(item, { grid = false } = {}) {
  const key = _storeMedia(item);
  const label = item.kind || item.source || 'media';
  const title = item.title || item.caption || item.code || label;
  return `<button type="button" class="instagram-media-card ${grid ? 'instagram-grid-card' : ''}" data-media-key="${key}" title="${esc(title || label)}">
    ${_mediaCardInnerHtml(item, { grid })}
  </button>`;
}

function _mediaItemsHtml(items) {
  if (!items || !items.length) return '';
  return `<div class="instagram-media-strip">${items.map(item => _mediaCardHtml(item)).join('')}</div>`;
}

function _wireMediaClicks(root = document) {
  root.querySelectorAll('.instagram-media-card[data-media-key]').forEach(btn => {
    if (btn.dataset.wired === '1') return;
    btn.dataset.wired = '1';
    btn.addEventListener('click', async (e) => {
      e.preventDefault();
      const item = _mediaStore.get(btn.dataset.mediaKey);
      if (item) {
        try {
          await _openMediaViewer(item);
        } catch (err) {
          uiModule?.showError?.(err.message || 'Could not load Instagram media');
        }
      }
    });
  });
  _hydrateMediaCards(root);
}

function _hydrateMediaCards(root = document) {
  root.querySelectorAll('.instagram-media-card[data-media-key]').forEach(btn => {
    const key = btn.dataset.mediaKey;
    const item = _mediaStore.get(key);
    if (!item || _hasLocalMedia(item) || btn.dataset.cacheState === 'loading') return;
    btn.dataset.cacheState = 'loading';
    btn.classList.add('loading');
    _mediaHydrationChain = _mediaHydrationChain.then(() => _cacheMediaItem(item), () => _cacheMediaItem(item));
    _mediaHydrationChain.then(cached => {
      _mediaStore.set(key, cached);
      btn.innerHTML = _mediaCardInnerHtml(cached, { grid: btn.classList.contains('instagram-grid-card') });
      btn.dataset.cacheState = 'ready';
      btn.classList.remove('loading');
    }).catch(() => {
      btn.dataset.cacheState = 'failed';
      btn.classList.remove('loading');
    });
  });
}

async function _openMediaViewer(item) {
  item = await _cacheMediaItem(item);
  const modal = document.getElementById('instagram-modal');
  const content = modal?.querySelector('.instagram-modal-content');
  if (!content) return;
  content.querySelector('.instagram-media-viewer')?.remove();
  const resources = Array.isArray(item.resources) && item.resources.length ? item.resources : [item];
  const active = resources[0] || item;
  const media = _primaryMedia(active);
  const title = item.title || item.caption || item.code || item.kind || 'Instagram media';
  const stage = media.video
    ? `<video src="${esc(media.video)}" poster="${esc(media.image)}" controls autoplay playsinline></video>`
    : media.image
      ? `<img src="${esc(media.image)}" alt="${esc(title)}">`
      : '<div class="instagram-empty" style="color:#fff;">No preview URL available.</div>';
  const resourceHtml = resources.length > 1
    ? `<div class="instagram-resource-row">${resources.map(res => _mediaCardHtml(res)).join('')}</div>`
    : '';
  const overlay = document.createElement('div');
  overlay.className = 'instagram-media-viewer';
  overlay.innerHTML = `
    <div class="instagram-media-viewer-card" role="dialog" aria-label="Instagram media viewer">
      <div class="modal-header">
        <h4 style="display:flex;align-items:center;gap:6px;">${IG_ICON} ${esc(title || 'Media')}</h4>
        <span style="flex:1"></span>
        ${item.url ? `<a class="instagram-btn" href="${esc(item.url)}" target="_blank" rel="noopener noreferrer">Open</a>` : ''}
        <button class="close-btn" id="instagram-media-close">x</button>
      </div>
      <div class="instagram-media-viewer-body">
        <div class="instagram-media-stage">${stage}</div>
        <div class="instagram-media-detail">
          <div style="font-weight:700;margin-bottom:6px;">${esc(title || item.kind || 'Media')}</div>
          ${item.username ? `<div style="opacity:.65;margin-bottom:6px;">@${esc(item.username)}</div>` : ''}
          ${item.caption ? `<div style="white-space:pre-wrap;margin-bottom:8px;">${linkify(item.caption)}</div>` : ''}
          ${item.taken_at ? `<div style="opacity:.55;margin-bottom:4px;">${esc(item.taken_at)}</div>` : ''}
          ${item.pk ? `<div style="opacity:.45;overflow-wrap:anywhere;">${esc(item.pk)}</div>` : ''}
          ${resourceHtml}
        </div>
      </div>
    </div>`;
  content.appendChild(overlay);
  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) overlay.remove();
  });
  overlay.querySelector('#instagram-media-close')?.addEventListener('click', () => overlay.remove());
  _wireMediaClicks(overlay);
}

function _renderThreadList() {
  const list = document.getElementById('instagram-thread-list');
  if (!list) return;
  if (!_threads.length) {
    list.innerHTML = '<div class="instagram-empty">No Instagram threads found.</div>';
    return;
  }
  list.innerHTML = _threads.map(thread => {
    const users = _threadUsers(thread);
    const title = thread.thread_title || _threadTitleFromUsers(users) || '(untitled thread)';
    const primary = users[0] || { username: title };
    const active = String(thread.thread_id) === String(_activeThreadId);
    return `<button class="instagram-thread ${active ? 'active' : ''}" data-thread-id="${esc(thread.thread_id)}">
      ${_avatarHtml(primary, title)}
      <span class="instagram-thread-main">
        <span class="instagram-thread-title">${esc(title)}</span>
        <span class="instagram-thread-users">${users.slice(0, 4).map(u => `<span class="instagram-thread-user">@${esc(_userDisplay(u))}</span>`).join('')}</span>
        <span class="instagram-thread-sub">${esc(_previewThread(thread))}</span>
        ${_tagHtml(thread.tags || [])}
      </span>
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
  if (head) head.innerHTML = `<div class="email-reader-header"><div class="email-reader-meta"><div class="email-reader-meta-row"><strong>Instagram</strong><span style="opacity:.65">${IG_ICON}</span></div></div></div>`;
  if (msgs) msgs.innerHTML = `<div class="instagram-empty">${message}</div>`;
  if (reply) reply.style.display = 'none';
}

function _recipientChips(users) {
  const values = (users || []).filter(Boolean);
  if (!values.length) return '<span style="opacity:.5">No users</span>';
  return values.map(u => `<span class="recipient-chip"><span class="recipient-chip-label">@${esc(_userDisplay(u))}</span></span>`).join('');
}

function _renderThread(thread, accountUsername = '') {
  _activeThreadId = thread.thread_id || '';
  _renderThreadList();
  const head = document.getElementById('instagram-reader-head');
  const msgs = document.getElementById('instagram-messages');
  const reply = document.getElementById('instagram-replybar');
  const users = _threadUsers(thread);
  const title = thread.thread_title || _threadTitleFromUsers(users) || 'Instagram thread';
  if (head) {
    head.innerHTML = `
      <div class="email-reader-header">
        <div class="email-reader-meta">
          <div class="email-reader-meta-row"><strong>Thread:</strong><span>${esc(title)}</span></div>
          <div class="email-reader-meta-row"><strong>People:</strong><span class="recipient-chips">${_recipientChips(users)}</span></div>
        </div>
        <div class="email-reader-actions">
          <button class="instagram-btn" id="instagram-back">Back</button>
          <button class="instagram-btn" id="instagram-thread-refresh">${REFRESH_ICON}</button>
        </div>
      </div>`;
    head.querySelector('#instagram-back')?.addEventListener('click', () => {
      document.querySelector('.instagram-sidebar')?.classList.remove('thread-open');
      document.querySelector('.instagram-reader')?.classList.remove('thread-open');
    });
    head.querySelector('#instagram-thread-refresh')?.addEventListener('click', () => _readThread(_activeThreadId).catch(err => uiModule?.showError?.(err.message)));
  }
  if (msgs) {
    const own = String(accountUsername || _currentAccountUsername()).toLowerCase();
    const messages = [...(thread.messages || [])].reverse();
    msgs.innerHTML = messages.length ? messages.map(msg => {
      const fromUser = _userForMessage(thread, msg);
      const from = _userDisplay(fromUser) || msg.from_username || msg.from_user_id || '';
      const mine = own && String(from).toLowerCase() === own;
      const displayFrom = mine ? 'me' : (from || 'unknown');
      const avatar = _avatarHtml(mine ? { username: 'me' } : fromUser, displayFrom);
      return `<div class="instagram-msg-row ${mine ? 'mine' : ''}">
        ${avatar}
        <div class="instagram-msg-card">
          <div class="instagram-msg-meta"><span class="instagram-msg-user">${esc(displayFrom)}</span><span class="instagram-msg-time">${esc(msg.timestamp || '')}</span>${msg.item_type ? `<span>${esc(msg.item_type)}</span>` : ''}</div>
          ${msg.text ? `<div class="instagram-msg-text">${linkify(msg.text || '')}</div>` : ''}
          ${_mediaItemsHtml(msg.media_items || [])}
          ${_tagHtml(msg.tags || [])}
          ${msg.triage_reason ? `<div style="font-size:10px;opacity:.55;margin-top:5px;">${esc(msg.triage_reason)}</div>` : ''}
        </div>
      </div>`;
    }).join('') : '<div class="instagram-empty">No messages in this thread.</div>';
    _wireMediaClicks(msgs);
    msgs.scrollTop = msgs.scrollHeight;
  }
  if (reply) reply.style.display = 'flex';
  document.querySelector('.instagram-sidebar')?.classList.add('thread-open');
  document.querySelector('.instagram-reader')?.classList.add('thread-open');
}

async function _loadAccounts() {
  const data = await _fetchJson(`${API_BASE}/api/instagram/accounts`);
  _accounts = data.accounts || [];
  const def = _accounts.find(a => a.is_default) || _accounts[0] || null;
  _account = _account || (def ? (def.id || def.username || def.name || '') : '');
}

async function _loadThreads() {
  const list = document.getElementById('instagram-thread-list');
  if (list) list.innerHTML = '<div class="instagram-empty">Loading threads...</div>';
  const query = _accountParam();
  const data = await _fetchJson(`${API_BASE}/api/instagram/threads?max_results=30${query ? '&' + query : ''}`);
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
  const data = await _fetchJson(`${API_BASE}/api/instagram/search?${params.toString()}`);
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
  const data = await _fetchJson(`${API_BASE}/api/instagram/threads/${encodeURIComponent(threadId)}?${params.toString()}`);
  _renderThread(data.thread, _currentAccountUsername());
}

async function _sendReply() {
  const textarea = document.getElementById('instagram-reply');
  const send = document.getElementById('instagram-send');
  const text = textarea?.value?.trim() || '';
  if (!_activeThreadId || !text) return;
  send.disabled = true;
  try {
    await _fetchJson(`${API_BASE}/api/instagram/send`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ account: _account || undefined, thread_id: _activeThreadId, text }),
    });
    textarea.value = '';
    uiModule?.showToast?.('Instagram message sent');
    await _readThread(_activeThreadId);
  } catch (err) {
    uiModule?.showError?.(err.message || 'Send failed');
  } finally {
    send.disabled = false;
  }
}

function _targetUsername(id, { fallbackCurrent = true } = {}) {
  const input = document.getElementById(id);
  const value = String(input?.value || '').trim().replace(/^@+/, '');
  return value || (fallbackCurrent ? _currentAccountUsername() : '');
}

function _renderMediaGrid(containerId, items, emptyText) {
  const el = document.getElementById(containerId);
  if (!el) return;
  if (!items.length) {
    el.innerHTML = `<div class="instagram-empty">${esc(emptyText)}</div>`;
    return;
  }
  el.innerHTML = `<div class="instagram-grid">${items.map(item => _mediaCardHtml(item, { grid: true })).join('')}</div>`;
  _wireMediaClicks(el);
}

async function _loadStories() {
  const grid = document.getElementById('instagram-stories-grid');
  if (grid) grid.innerHTML = '<div class="instagram-empty">Loading stories...</div>';
  const params = new URLSearchParams({ max_results: '40' });
  if (_account) params.set('account', _account);
  const username = _targetUsername('instagram-story-user', { fallbackCurrent: false });
  if (username) params.set('username', username);
  const data = await _fetchJson(`${API_BASE}/api/instagram/stories?${params.toString()}`);
  _stories = data.stories || [];
  _renderMediaGrid('instagram-stories-grid', _stories, 'No viewable stories found.');
}

async function _loadPosts() {
  const grid = document.getElementById('instagram-posts-grid');
  if (grid) grid.innerHTML = '<div class="instagram-empty">Loading posts...</div>';
  const params = new URLSearchParams({ max_results: '36' });
  if (_account) params.set('account', _account);
  const username = _targetUsername('instagram-post-user');
  if (username) params.set('username', username);
  const data = await _fetchJson(`${API_BASE}/api/instagram/posts?${params.toString()}`);
  _posts = data.posts || [];
  _renderMediaGrid('instagram-posts-grid', _posts, 'No posts found.');
}

function _renderSelectedFiles() {
  const out = document.getElementById('instagram-create-files');
  const input = document.getElementById('instagram-create-file');
  const pathInput = document.getElementById('instagram-create-path');
  const names = [
    ...Array.from(input?.files || []).map(f => f.name),
    ...String(pathInput?.value || '').split(/[\n,]+/).map(s => s.trim()).filter(Boolean),
  ];
  if (!out) return;
  out.innerHTML = names.length
    ? names.map(name => `<span class="instagram-upload-pill">${esc(name)}</span>`).join('')
    : '<span style="opacity:.55">No media selected</span>';
}

async function _uploadCreatorFiles() {
  const input = document.getElementById('instagram-create-file');
  const files = Array.from(input?.files || []);
  if (!files.length) return [];
  const fd = new FormData();
  files.forEach(file => fd.append('files', file));
  const data = await _fetchJson(`${API_BASE}/api/upload`, { method: 'POST', body: fd });
  return (data.files || []).map(file => ({ id: file.id, filename: file.name, content_type: file.mime }));
}

async function _createPost() {
  const btn = document.getElementById('instagram-create-submit');
  const msg = document.getElementById('instagram-create-msg');
  const target = document.getElementById('instagram-create-target')?.value || 'feed';
  const caption = document.getElementById('instagram-create-caption')?.value || '';
  const pathInput = document.getElementById('instagram-create-path');
  btn.disabled = true;
  if (msg) { msg.textContent = 'Publishing...'; msg.style.color = ''; }
  try {
    const uploaded = await _uploadCreatorFiles();
    const paths = String(pathInput?.value || '').split(/[\n,]+/).map(s => s.trim()).filter(Boolean);
    const attachments = [...uploaded, ...paths];
    if (!attachments.length) throw new Error('Select media first');
    const data = await _fetchJson(`${API_BASE}/api/instagram/posts`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ account: _account || undefined, target, caption, attachments }),
    });
    if (msg) { msg.textContent = 'Published'; msg.style.color = 'var(--green,#50fa7b)'; }
    document.getElementById('instagram-create-caption').value = '';
    if (pathInput) pathInput.value = '';
    const input = document.getElementById('instagram-create-file');
    if (input) input.value = '';
    _renderSelectedFiles();
    if (data.result?.media) await _openMediaViewer(data.result.media);
  } catch (err) {
    if (msg) { msg.textContent = err.message || 'Publish failed'; msg.style.color = 'var(--red)'; }
    uiModule?.showError?.(err.message || 'Publish failed');
  } finally {
    btn.disabled = false;
  }
}

function _switchTab(tab, { load = true } = {}) {
  _activeTab = tab;
  document.querySelectorAll('[data-instagram-tab]').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.instagramTab === tab);
  });
  document.querySelectorAll('[data-instagram-panel]').forEach(panel => {
    panel.classList.toggle('active', panel.dataset.instagramPanel === tab);
  });
  if (!load) return;
  if (tab === 'dm') _loadThreads().catch(err => uiModule?.showError?.(err.message));
  else if (tab === 'stories') _loadStories().catch(err => uiModule?.showError?.(err.message));
  else if (tab === 'posts') _loadPosts().catch(err => uiModule?.showError?.(err.message));
}

function _tabsHtml() {
  const tabs = [
    ['dm', `${DM_ICON} DMs`],
    ['stories', `${STORY_ICON} Stories`],
    ['posts', `${GRID_ICON} Posts`],
    ['create', `${PLUS_ICON} Create`],
  ];
  return `<div class="lib-tabs instagram-tabs">${tabs.map(([key, label]) =>
    `<button type="button" class="lib-tab ${key === _activeTab ? 'active' : ''}" data-instagram-tab="${key}">${label}</button>`
  ).join('')}</div>`;
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
  const username = _currentAccountUsername();
  content.innerHTML = `
    <div class="modal-header">
      <h4 style="display:flex;align-items:center;gap:6px;">${IG_ICON} Instagram</h4>
      <span style="flex:1"></span>
      ${_accountSelectHtml()}
      <button class="instagram-btn" id="instagram-refresh" title="Refresh">${REFRESH_ICON}</button>
      <button class="close-btn" id="instagram-close">x</button>
    </div>
    ${_tabsHtml()}
    <div class="instagram-tab-panels">
      <section class="instagram-tab-panel ${_activeTab === 'dm' ? 'active' : ''}" data-instagram-panel="dm">
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
              <textarea id="instagram-reply" class="instagram-input instagram-reply" placeholder="Reply"></textarea>
              <button class="instagram-btn primary" id="instagram-send">Send</button>
            </div>
          </div>
        </div>
      </section>
      <section class="instagram-tab-panel ${_activeTab === 'stories' ? 'active' : ''}" data-instagram-panel="stories">
        <div class="instagram-content-panel">
          <div class="instagram-content-toolbar">
            <input id="instagram-story-user" class="instagram-input" value="" placeholder="stories tray or @username" style="width:220px;">
            <button class="instagram-btn" id="instagram-story-refresh">${REFRESH_ICON} Refresh</button>
          </div>
          <div id="instagram-stories-grid"></div>
        </div>
      </section>
      <section class="instagram-tab-panel ${_activeTab === 'posts' ? 'active' : ''}" data-instagram-panel="posts">
        <div class="instagram-content-panel">
          <div class="instagram-content-toolbar">
            <input id="instagram-post-user" class="instagram-input" value="${esc(username)}" placeholder="username" style="width:220px;">
            <button class="instagram-btn" id="instagram-post-refresh">${REFRESH_ICON} Refresh</button>
          </div>
          <div id="instagram-posts-grid"></div>
        </div>
      </section>
      <section class="instagram-tab-panel ${_activeTab === 'create' ? 'active' : ''}" data-instagram-panel="create">
        <div class="instagram-content-panel">
          <div class="instagram-create-wrap">
            <div class="instagram-create-row">
              <label for="instagram-create-target">Target</label>
              <select id="instagram-create-target" class="instagram-select" style="max-width:none;">
                <option value="feed">Feed post</option>
                <option value="story">Story</option>
                <option value="reel">Reel</option>
              </select>
            </div>
            <div class="instagram-create-row">
              <label for="instagram-create-file">Media</label>
              <input id="instagram-create-file" class="instagram-input" type="file" accept="image/*,video/*" multiple>
            </div>
            <div class="instagram-create-row">
              <label for="instagram-create-path">Path or upload ID</label>
              <textarea id="instagram-create-path" class="instagram-textarea" style="min-height:58px;" placeholder="one per line"></textarea>
            </div>
            <div class="instagram-create-row">
              <label>Selected</label>
              <div id="instagram-create-files" class="instagram-upload-list"><span style="opacity:.55">No media selected</span></div>
            </div>
            <div class="instagram-create-row">
              <label for="instagram-create-caption">Caption</label>
              <textarea id="instagram-create-caption" class="instagram-textarea" placeholder="Caption"></textarea>
            </div>
            <div style="display:flex;align-items:center;gap:8px;justify-content:flex-end;">
              <span id="instagram-create-msg" style="font-size:11px;flex:1;"></span>
              <button class="instagram-btn primary" id="instagram-create-submit">${PLUS_ICON} Publish</button>
            </div>
          </div>
        </div>
      </section>
    </div>`;
  content.querySelector('#instagram-close')?.addEventListener('click', closeInstagramPanel);
  content.querySelector('#instagram-refresh')?.addEventListener('click', () => _switchTab(_activeTab));
  content.querySelector('#instagram-account')?.addEventListener('change', (e) => {
    _account = e.target.value || '';
    _activeThreadId = '';
    _threads = [];
    _stories = [];
    _posts = [];
    _renderShell();
    _switchTab(_activeTab);
  });
  content.querySelectorAll('[data-instagram-tab]').forEach(btn => {
    btn.addEventListener('click', () => _switchTab(btn.dataset.instagramTab));
  });
  content.querySelector('#instagram-search')?.addEventListener('input', (e) => {
    clearTimeout(_searchTimer);
    _searchTimer = setTimeout(() => _searchThreads(e.target.value || '').catch(err => uiModule?.showError?.(err.message)), 250);
  });
  content.querySelector('#instagram-send')?.addEventListener('click', _sendReply);
  content.querySelector('#instagram-reply')?.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') _sendReply();
  });
  content.querySelector('#instagram-story-refresh')?.addEventListener('click', () => _loadStories().catch(err => uiModule?.showError?.(err.message)));
  content.querySelector('#instagram-post-refresh')?.addEventListener('click', () => _loadPosts().catch(err => uiModule?.showError?.(err.message)));
  content.querySelector('#instagram-story-user')?.addEventListener('keydown', (e) => { if (e.key === 'Enter') _loadStories().catch(err => uiModule?.showError?.(err.message)); });
  content.querySelector('#instagram-post-user')?.addEventListener('keydown', (e) => { if (e.key === 'Enter') _loadPosts().catch(err => uiModule?.showError?.(err.message)); });
  content.querySelector('#instagram-create-file')?.addEventListener('change', _renderSelectedFiles);
  content.querySelector('#instagram-create-path')?.addEventListener('input', _renderSelectedFiles);
  content.querySelector('#instagram-create-submit')?.addEventListener('click', _createPost);
  _switchTab(_activeTab, { load: false });
}

export async function openInstagramPanel(opts = {}) {
  _pendingThreadId = opts.threadId || opts.thread_id || '';
  if (_pendingThreadId) _activeTab = 'dm';
  if (Modals.isRegistered('instagram-modal')) {
    Modals.restore('instagram-modal');
    _switchTab(_activeTab, { load: false });
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
  makeWindowDraggable(modal, { content, header: content, skipSelector: 'button, input, select, textarea, a, video' });
  modal.addEventListener('click', (e) => {
    if (e.target === modal) closeInstagramPanel();
  });
  try {
    await _loadAccounts();
    _renderShell();
    _switchTab(_activeTab);
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
  _mediaStore = new Map();
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
