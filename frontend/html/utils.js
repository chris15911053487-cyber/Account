// ── API 基础 ───────────────────────────────────────────
const API = '/api';

function getToken() { return localStorage.getItem('token'); }
function getUser()  { return JSON.parse(localStorage.getItem('user') || 'null'); }
function setAuth(token, user) {
  localStorage.setItem('token', token);
  localStorage.setItem('user', JSON.stringify(user));
}
function clearAuth() {
  localStorage.removeItem('token');
  localStorage.removeItem('user');
}

async function apiFetch(path, opts = {}) {
  const token = getToken();
  const headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  const res = await fetch(API + path, { ...opts, headers });
  // silent 模式：不自动跳转，直接抛异常让调用方处理
  if (res.status === 401) {
    if (opts.silent) throw new Error('401');
    clearAuth(); location.href = '/login.html'; return;
  }
  if (!res.ok) {
    let msg = `请求失败 (${res.status})`;
    try { const d = await res.json(); msg = d.detail || msg; } catch {}
    throw new Error(msg);
  }
  if (res.status === 204) return null;
  return res.json();
}

// ── 主题 ──────────────────────────────────────────────
function initTheme() {
  const theme = localStorage.getItem('theme') || 'light';
  document.documentElement.setAttribute('data-theme', theme);
}
function toggleTheme() {
  const cur = document.documentElement.getAttribute('data-theme');
  const next = cur === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  localStorage.setItem('theme', next);
  document.querySelectorAll('.theme-btn').forEach(btn => {
    btn.textContent = next === 'dark' ? '☀️' : '🌙';
  });
}
initTheme();

// ── Toast ─────────────────────────────────────────────
function toast(msg, type = 'info') {
  const el = document.createElement('div');
  el.className = `toast toast-${type}`;
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 3000);
}

// ── 认证守卫 ──────────────────────────────────────────
function requireAuth() {
  if (!getToken()) { location.href = '/login.html'; return null; }
  return getUser();
}
function requireAdmin() {
  const user = requireAuth();
  if (user && !user.is_admin) { location.href = '/dashboard.html'; return null; }
  return user;
}

// ── 导航栏渲染 ────────────────────────────────────────
async function renderNav(activePage) {
  const user = getUser();
  if (!user) return;

  // 获取待审批数量，静默失败不跳转
  let pendingCount = 0;
  try {
    const pending = await apiFetch('/approvals/pending', { silent: true });
    pendingCount = pending ? pending.length : 0;
  } catch {}

  const theme = localStorage.getItem('theme') || 'light';
  const isAdmin = user.is_admin;

  // ── 顶部导航 ──
  const nav = document.getElementById('navbar');
  if (nav) {
    nav.innerHTML = `
      <button class="nav-hamburger" id="hamburgerBtn" onclick="openDrawer()" aria-label="菜单">
        <span></span><span></span><span></span>
      </button>
      <div class="nav-logo">💰 记账本</div>
      <nav class="nav-links">
        <a href="/dashboard.html" class="${activePage==='dashboard'?'active':''}">🏠 仪表盘</a>
        <a href="/transactions.html" class="${activePage==='transactions'?'active':''}">📋 流水记录</a>
        <a href="/approvals.html" class="${activePage==='approvals'?'active':''}">
          ✅ 审批中心
          ${pendingCount > 0 ? `<span class="badge">${pendingCount}</span>` : ''}
        </a>
        <a href="/accounts.html" class="${activePage==='accounts'?'active':''}">🏦 账户管理</a>
        ${isAdmin ? `<a href="/admin-users.html" class="${activePage==='admin'?'active':''}">👥 用户管理</a>` : ''}
      </nav>
      <div class="nav-user">
        <button class="theme-btn" onclick="toggleTheme()">${theme==='dark'?'☀️':'🌙'}</button>
        <div class="nav-avatar">${user.display_name.charAt(0)}</div>
        <span class="nav-username">${user.display_name}</span>
        <button class="logout-btn" onclick="logout()">退出</button>
      </div>
    `;
  }

  // ── 抽屉菜单（移动端） ──
  let drawer = document.getElementById('navDrawer');
  if (!drawer) {
    drawer = document.createElement('div');
    drawer.innerHTML = `
      <div class="nav-drawer-overlay" id="drawerOverlay" onclick="closeDrawer()"></div>
      <div class="nav-drawer" id="drawerPanel">
        <div class="nav-drawer-header">
          <span class="nav-drawer-logo">💰 记账本</span>
          <button class="nav-drawer-close" onclick="closeDrawer()">✕</button>
        </div>
        <div class="nav-drawer-user">
          <div class="nav-drawer-avatar">${user.display_name.charAt(0)}</div>
          <div>
            <div style="font-weight:600">${user.display_name}</div>
            <div style="font-size:.8rem;color:var(--text2)">${isAdmin ? '管理员' : '普通用户'}</div>
          </div>
        </div>
        <div class="nav-drawer-links">
          <a href="/dashboard.html" class="${activePage==='dashboard'?'active':''}">🏠 <span>仪表盘</span></a>
          <a href="/transactions.html" class="${activePage==='transactions'?'active':''}">📋 <span>流水记录</span></a>
          <a href="/approvals.html" class="${activePage==='approvals'?'active':''}">
            ✅ <span>审批中心</span>
            ${pendingCount > 0 ? `<span class="badge">${pendingCount}</span>` : ''}
          </a>
          <a href="/accounts.html" class="${activePage==='accounts'?'active':''}">🏦 <span>账户管理</span></a>
          ${isAdmin ? `<a href="/admin-users.html" class="${activePage==='admin'?'active':''}">👥 <span>用户管理</span></a>` : ''}
        </div>
        <div class="nav-drawer-footer">
          <button class="theme-btn" onclick="toggleTheme()">${theme==='dark'?'☀️':'🌙'}</button>
          <button class="logout-btn" onclick="logout()">退出登录</button>
        </div>
      </div>
    `;
    document.body.appendChild(drawer);
  }

  // ── 底部 Tab 栏（移动端） ──
  let bottomNav = document.getElementById('bottomNav');
  if (!bottomNav) {
    bottomNav = document.createElement('nav');
    bottomNav.className = 'bottom-nav';
    bottomNav.id = 'bottomNav';
    bottomNav.innerHTML = `
      <div class="bottom-nav-inner">
        <a href="/dashboard.html" class="bottom-nav-item ${activePage==='dashboard'?'active':''}">
          <span class="bn-icon">🏠</span>
          <span>首页</span>
        </a>
        <a href="/transactions.html" class="bottom-nav-item ${activePage==='transactions'?'active':''}">
          <span class="bn-icon">📋</span>
          <span>流水</span>
        </a>
        <a href="/new-transaction.html" class="bottom-nav-item ${activePage==='new-tx'?'active':''}" style="color:var(--primary)">
          <span class="bn-icon" style="background:var(--primary);color:#fff;border-radius:50%;width:40px;height:40px;display:flex;align-items:center;justify-content:center;font-size:1.4rem;margin-bottom:-2px">＋</span>
          <span>记账</span>
        </a>
        <a href="/approvals.html" class="bottom-nav-item ${activePage==='approvals'?'active':''}">
          <span class="bn-icon">✅</span>
          <span>审批</span>
          ${pendingCount > 0 ? `<span class="bn-badge">${pendingCount}</span>` : ''}
        </a>
        <a href="/accounts.html" class="bottom-nav-item ${activePage==='accounts'?'active':''}">
          <span class="bn-icon">🏦</span>
          <span>账户</span>
        </a>
      </div>
    `;
    document.body.appendChild(bottomNav);
  }
}

function openDrawer() {
  document.getElementById('drawerOverlay').classList.add('open');
  document.getElementById('drawerPanel').classList.add('open');
  document.body.style.overflow = 'hidden';
}
function closeDrawer() {
  document.getElementById('drawerOverlay').classList.remove('open');
  document.getElementById('drawerPanel').classList.remove('open');
  document.body.style.overflow = '';
}

function logout() {
  clearAuth();
  location.href = '/login.html';
}

// ── 格式化工具 ────────────────────────────────────────
function fmtMoney(val) {
  return '¥' + Number(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
function fmtDate(iso) {
  if (!iso) return '-';
  return new Date(iso).toLocaleString('zh-CN', { hour12: false });
}
function fmtDateShort(iso) {
  if (!iso) return '-';
  return new Date(iso).toLocaleDateString('zh-CN');
}

const TX_TYPE_LABELS = {
  spend: '支出', deposit: '流入', transfer_out: '转出', transfer_in: '转入'
};
const TX_STATUS_LABELS = {
  pending: '待审批', in_progress: '审批中', approved: '已通过', rejected: '已拒绝'
};

function typeBadge(type) {
  return `<span class="type-badge type-${type}">${TX_TYPE_LABELS[type]||type}</span>`;
}
function statusBadge(status) {
  return `<span class="status-badge status-${status}">${TX_STATUS_LABELS[status]||status}</span>`;
}
function amountDisplay(tx) {
  const sign = (tx.type === 'deposit' || tx.type === 'transfer_in') ? '+' : '-';
  const cls = sign === '+' ? 'amount-positive' : 'amount-negative';
  return `<span class="${cls}">${sign}${fmtMoney(tx.amount)}</span>`;
}
