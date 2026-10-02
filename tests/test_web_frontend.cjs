const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../frontend/app.js'), 'utf8').replace(
  '  boot();',
  '  window.testing = { state, api, refreshSession, logout, visiblePipes, planPipe, loadPlans, loadEvidence, renderEvidence, loadPipelineSettings, $ };');
const user = { email: 'viewer@example.com', role: 'viewer', allowed_pipelines: ['v285', 'v269', 'v266'] };
const expired = { access_token: 'old', expires_at: 1, user };
const fresh = { access_token: 'new', expires_at: Date.now() / 1000 + 900, user };
const response = (status, body) => ({ status, ok: status >= 200 && status < 300, json: async () => body });

function storage(pair = expired) {
  const values = new Map();
  return { initial: pair, getItem: k => values.get(k) ?? null, setItem: (k, v) => values.set(k, v), removeItem: k => values.delete(k) };
}
function locks() {
  let tail = Promise.resolve();
  return { request: (_name, fn) => {
    const current = tail.then(fn);
    tail = current.catch(() => {});
    return current;
  } };
}
function app(fetch, localStorage = storage(), sharedLocks = locks()) {
  const elements = new Map();
  const getElementById = id => {
    if (!elements.has(id)) elements.set(id, { innerHTML: '', childElementCount: 1, hidden: false });
    return elements.get(id);
  };
  const window = { APP_CONFIG: {}, addEventListener() {} };
  const context = { window, document: { getElementById, querySelectorAll: () => [], addEventListener() {} },
    localStorage, navigator: { locks: sharedLocks }, fetch, setInterval() {}, setTimeout() {}, clearTimeout() {},
    location: { reload() {} }, google: { accounts: { id: { disableAutoSelect() {} } } }, console };
  vm.runInNewContext(source, context);
  window.testing.state.user = { ...user, allowed_pipelines: [...user.allowed_pipelines] };
  window.testing.state.session = localStorage.initial;
  window.testing.state.token = localStorage.initial.access_token;
  return window.testing;
}

test('viewer selection ignores a saved restricted pipeline and only fetches allowed plans', async () => {
  const saved = storage(fresh); saved.setItem('planPipe6', 'v301');
  const paths = [];
  const ui = app(async p => { paths.push(p); return response(200, {}); }, saved);
  assert.deepEqual(Array.from(ui.visiblePipes(), p => p.v), user.allowed_pipelines);
  assert.equal(ui.planPipe(), 'v285');
  await ui.loadPlans();
  assert.equal(paths.length, 4);
  assert.ok(paths.every(p => user.allowed_pipelines.some(v => p === `/api/trade_plan?pipeline=${v}`)));
});

test('parallel API requests share one proactive refresh', async () => {
  let refreshes = 0;
  const ui = app(async (p, options) => {
    if (p === '/api/auth/refresh') { refreshes++; await Promise.resolve(); return response(200, fresh); }
    assert.equal(options.headers.Authorization, 'Bearer new');
    return response(200, { ok: true });
  });
  await Promise.all(Array.from({ length: 10 }, () => ui.api('/api/trade_plan')));
  assert.equal(refreshes, 1);
});

test('two tabs serialize HttpOnly cookie rotation', async () => {
  const saved = storage(), sharedLocks = locks();
  let refreshes = 0, active = false;
  const fetch = async (p, options) => {
    if (p === '/api/auth/refresh') { assert.equal(active, false); active = true; refreshes++;
      assert.equal(options.credentials, 'include'); await Promise.resolve(); active = false; return response(200, fresh); }
    assert.equal(options.headers.Authorization, 'Bearer new');
    return response(200, {});
  };
  const first = app(fetch, saved, sharedLocks), second = app(fetch, saved, sharedLocks);
  await Promise.all([first.api('/api/trade_plan'), second.api('/api/trade_plan')]);
  assert.equal(refreshes, 2);
  assert.equal(second.state.token, 'new');
  assert.equal(saved.getItem('aal_session'), null);
  assert.equal(saved.getItem('aal_token'), null);
});

test('401 refreshes and retries the protected request once', async () => {
  let attempts = 0, refreshes = 0;
  const ui = app(async p => {
    if (p === '/api/auth/refresh') { refreshes++; return response(200, { ...fresh, access_token: 'retry' }); }
    attempts++; return response(attempts === 1 ? 401 : 200, { ok: true });
  }, storage(fresh));
  assert.equal((await ui.api('/api/trade_plan')).ok, true);
  assert.equal(attempts, 2); assert.equal(refreshes, 1);
});

test('logout during refresh cannot restore the session', async () => {
  let complete, started;
  const ready = new Promise(resolve => { started = resolve; });
  const ui = app(async p => {
    if (p === '/api/auth/refresh') {
      started(); return new Promise(resolve => { complete = resolve; });
    }
    return response(200, {});
  });
  const pending = ui.refreshSession();
  await ready; ui.logout(); complete(response(200, fresh));
  await assert.rejects(pending);
  assert.equal(ui.state.token, ''); assert.equal(ui.state.session, null);
});

test('failed refresh clears the pair, while a network failure preserves it', async () => {
  const ui = app(async p => response(p === '/api/auth/refresh' ? 401 : 200, {}));
  await assert.rejects(ui.api('/api/trade_plan'));
  assert.equal(ui.state.token, '');
  const offline = app(async () => { throw new Error('offline'); });
  await assert.rejects(offline.api('/api/trade_plan'));
  assert.equal(offline.state.token, 'old');
});

test('all locked pipelines keep their historical metrics visible and issue no plan requests', async () => {
  const evidence = Object.fromEntries(['v301', 'v295', 'v285', 'v269', 'v266'].map((p, i) => [p, {
    rank: i + 1, locked: true, automatic_order: true, admin_contact_email: 'admin@example.com',
    walkforward: { monthly_last_year: 5.349, monthly_dev4: 6.71, monthly_5y: 6.4, gate_dd: 17.09,
      win_hidden: .558, win_dev: .61, trades_dev: 200, trades_hidden: 55, losing_years: 0, yearly: [] },
  }]));
  const paths = [];
  const ui = app(async p => { paths.push(p); return response(200, evidence); }, storage(fresh));
  ui.state.live.plan = { coins: { secret: true } };
  await ui.loadEvidence(); await ui.loadPlans();
  assert.equal(ui.state.live.plan, null);
  assert.equal(ui.visiblePipes().length, 0);
  assert.deepEqual(paths, ['/api/pipelines_summary']);
  const html = ui.$('pipeEvid').innerHTML;
  assert.ok(html.includes('6.71') && html.includes('200 / 55'));
  assert.ok(html.includes('Năm kiểm chứng') && html.includes('4 năm phát triển'));
  assert.ok(html.includes('mailto:admin%40example.com'));
  assert.ok(!html.includes('data-pipe='));
});

test('admin moves pipeline without changing locks and saves with a Bearer header', async () => {
  const initial = { order: ['v301', 'v295', 'v285', 'v269', 'v266'], automatic: true, revision: 0,
    locked: { v301: true, v295: true, v285: false, v269: false, v266: false } };
  let submitted;
  const ui = app(async (p, opts) => {
    assert.equal(opts.headers.Authorization, 'Bearer new');
    assert.equal(opts.credentials, 'omit');
    if (p === '/api/admin/pipelines' && opts.method === 'POST') {
      submitted = JSON.parse(opts.body); return response(200, { ...submitted, automatic: false, revision: 1 });
    }
    if (p === '/api/admin/pipelines') return response(200, structuredClone(initial));
    return response(200, Object.fromEntries(submitted.order.map((p, i) => [p, { rank: i + 1, locked: false, locked_for_viewers: submitted.locked[p], walkforward: {} }])));
  }, storage(fresh));
  ui.state.user.role = 'admin';
  await ui.loadPipelineSettings();
  const move = { dataset: { move: '0', delta: '1' } };
  ui.$('pipelineSettingsTbl').onclick({ target: { closest: s => s === '[data-move]' ? move : null } });
  const lock = { dataset: { lock: 'v301' } };
  ui.$('pipelineSettingsTbl').onclick({ target: { closest: s => s === '[data-lock]' ? lock : null } });
  await ui.$('savePipelineSettings').onclick();
  assert.deepEqual(submitted.order, ['v295', 'v301', 'v285', 'v269', 'v266']);
  assert.deepEqual(submitted.locked, { ...initial.locked, v301: false });
  assert.equal(submitted.revision, 0);
  assert.ok(ui.$('pipelineSaveStatus').textContent.startsWith('Đã lưu.'));
  ui.logout(false);
  assert.equal(ui.$('pipelineSettingsTbl').innerHTML, '');
});
