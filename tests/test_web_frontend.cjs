const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../frontend/app.js'), 'utf8').replace(
  '  boot();',
  '  window.testing = { state, api, refreshSession, logout, onCredential, syncAccountAccess, visiblePipes, planPipe, setPlanPipe, histSource, histBoth, loadPerf, loadPlans, loadEvidence, renderEvidence, loadPipelineSettings, loadUsers, route, location, $, product, renderGoals, renderProductPanels, loadTodo };');
const user = { email: 'viewer@example.com', role: 'viewer', allowed_pipelines: ['v342', 'v362', 'v315'] };
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
    if (!elements.has(id)) elements.set(id, { innerHTML: '', childElementCount: 1, hidden: false,
      dataset: {}, style: {}, querySelectorAll: () => [], classList: { toggle() {}, add() {}, remove() {} } });
    return elements.get(id);
  };
  const window = { APP_CONFIG: {}, addEventListener() {}, LightweightCharts: {
    PriceScaleMode: { Logarithmic: 1, Normal: 0 },
    createChart: () => ({ remove() {}, addAreaSeries: () => ({ setData() {} }), timeScale: () => ({ fitContent() {} }) }),
  } };
  const context = { window, document: { getElementById, querySelectorAll: () => [], addEventListener() {} },
    localStorage, navigator: { locks: sharedLocks }, fetch, WebSocket: class { close() {} }, setInterval() {}, setTimeout() {}, clearTimeout() {},
    location: { reload() {} }, google: { accounts: { id: { disableAutoSelect() {} } } }, console };
  vm.runInNewContext(source, context);
  window.testing.state.user = { ...user, allowed_pipelines: [...user.allowed_pipelines] };
  window.testing.state.session = localStorage.initial;
  window.testing.state.token = localStorage.initial.access_token;
  return window.testing;
}

test('viewer selection ignores a saved restricted pipeline and only fetches allowed plans', async () => {
  const saved = storage(fresh); saved.setItem('planPipe6', 'v367');
  const paths = [];
  const ui = app(async p => { paths.push(p); return response(200, {}); }, saved);
  assert.deepEqual(Array.from(ui.visiblePipes(), p => p.v), Array.from(user.allowed_pipelines));
  assert.equal(ui.planPipe(), 'v342');
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
  const evidence = Object.fromEntries(['v367', 'v321', 'v342', 'v362', 'v315'].map((p, i) => [p, {
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
  assert.ok(html.includes('Test · 1 năm<br>Lãi ròng/tháng (%)') && html.includes('Train / chọn model<br>4 năm · Lãi ròng/tháng (%)'));
  assert.ok(html.includes('mailto:admin%40example.com'));
  assert.ok(!html.includes('data-pipe='));
});

test('admin moves pipeline without changing locks and saves with a Bearer header', async () => {
  const initial = { order: ['v367', 'v321', 'v342', 'v362', 'v315'], automatic: true, revision: 0,
    locked: { v367: true, v321: true, v342: false, v362: false, v315: false } };
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
  const lock = { dataset: { lock: 'v367' } };
  ui.$('pipelineSettingsTbl').onclick({ target: { closest: s => s === '[data-lock]' ? lock : null } });
  await ui.$('savePipelineSettings').onclick();
  assert.deepEqual(submitted.order, ['v321', 'v367', 'v342', 'v362', 'v315']);
  assert.deepEqual(submitted.locked, { ...initial.locked, v367: false });
  assert.equal(submitted.revision, 0);
  assert.ok(ui.$('pipelineSaveStatus').textContent.startsWith('Đã lưu.'));
  ui.logout(false);
  assert.equal(ui.$('pipelineSettingsTbl').innerHTML, '');
});

test('pipeline selection is shared by signal, history and performance, including private storage', async () => {
  const saved = storage(fresh);
  saved.setItem = () => { throw new Error('private storage'); };
  const paths = [];
  const ui = app(async p => {
    paths.push(p);
    if (p.includes('/api/trade_plan')) return response(200, { pipeline: 'new M4', coins: {} });
    return response(200, []);
  }, saved);
  ui.state.view = 'todo';
  ui.state.h.pipe = 'v342'; ui.state.perfPipe = 'v342';
  ui.state.live.paper = [['v362', { pipeline: 'stale cached M4', coins: {} }]];
  await ui.setPlanPipe('v362');
  assert.equal(ui.planPipe(), 'v362');
  assert.equal(ui.histSource(), 'tm_v362');
  await ui.histBoth('orders', 'BTCUSDT');
  assert.ok(paths.includes('/api/orders?symbol=BTCUSDT&source=tm_v362&limit=30000'));
  assert.ok(paths.includes('/api/orders?symbol=BTCUSDT&source=paper_v362&limit=30000'));
  assert.equal(ui.state.live.plan.pipeline, 'new M4');
  assert.ok(!ui.$('boardMeta').textContent.includes('M3'));
});

test('fast pipeline switches discard the old plan response and clear old results while loading', async () => {
  let finish;
  const ui = app(async p => {
    if (p.endsWith('pipeline=v362')) return new Promise(resolve => { finish = resolve; });
    return response(200, { pipeline: 'M1', coins: {} });
  }, storage(fresh));
  ui.state.view = 'todo'; ui.state.live.plan = { pipeline: 'old M3', coins: {} };
  ui.$('perfKpis').innerHTML = 'old M3 performance';
  const old = ui.setPlanPipe('v362');
  assert.equal(ui.state.live.plan, null);
  assert.equal(ui.$('perfKpis').innerHTML, '');
  assert.ok(ui.$('todoCards').innerHTML.includes('Đang tải kế hoạch lệnh'));
  await ui.setPlanPipe('v315');
  finish(response(200, { pipeline: 'late M4', coins: {} }));
  await old;
  assert.equal(ui.planPipe(), 'v315');
  assert.equal(ui.state.live.plan.pipeline, 'M1');
  assert.equal(ui.state.live.planLoading, false);
});

test('background plan refresh cannot overwrite a later selection', async () => {
  let delay = true;
  const pending = [];
  const ui = app(async p => {
    if (delay) return new Promise(resolve => pending.push(() => resolve(response(200, { pipeline: 'old M3', coins: {} }))));
    return response(200, { pipeline: 'M4', coins: {} });
  }, storage(fresh));
  ui.state.view = 'todo';
  const old = ui.loadPlans();
  await Promise.resolve();
  delay = false;
  await ui.setPlanPipe('v362');
  pending.forEach(resolve => resolve()); await old;
  assert.equal(ui.planPipe(), 'v362');
  assert.equal(ui.state.live.plan.pipeline, 'M4');
});

const evidence = () => Object.fromEntries(['v342', 'v362', 'v315'].map((p, i) => [p, {
  rank: i+1, locked: false, automatic_order: true, walkforward: {},
}]));

test('performance loads the globally selected pipeline and discards late KPI responses', async () => {
  let finishOld, markReady;
  const ready = new Promise(resolve => { markReady = resolve; });
  const paths = [];
  const ui = app(async p => {
    paths.push(p);
    if (p === '/api/pipelines_summary') return response(200, evidence());
    if (p === '/api/overview?pipeline=v342') {
      markReady(); return new Promise(resolve => { finishOld = resolve; });
    }
    if (p === '/api/overview?pipeline=v362') return response(200, { walkforward: { monthly_5y: 222 }, plan: {} });
    if (p.includes('/api/trade_plan')) return response(200, { coins: {} });
    return response(200, []);
  }, storage(fresh));
  ui.state.view = 'todo';
  const old = ui.loadPerf(); await ready;
  await ui.setPlanPipe('v362'); await ui.loadPerf();
  assert.ok(paths.includes('/api/equity?source=tm_v362&points=3000'));
  assert.ok(paths.includes('/api/orders/stats?source=tm_v362'));
  finishOld(response(200, { walkforward: { monthly_5y: 111 }, plan: {} })); await old;
  assert.ok(ui.$('perfKpis').innerHTML.includes('222'));
  assert.ok(!ui.$('perfKpis').innerHTML.includes('111'));
  assert.ok(ui.$('pipeSelectedNote').textContent.startsWith('Đang xem: M4'));
});

test('restricted selection sends no request and a lock change discards in-flight signals', async () => {
  let finish; const paths = [];
  const ui = app(async p => {
    paths.push(p);
    if (p === '/api/pipelines_summary') return response(200, { ...evidence(), v362: { rank: 2, locked: true, walkforward: {} } });
    return new Promise(resolve => { finish = resolve; });
  }, storage(fresh));
  ui.state.view = 'todo';
  await ui.setPlanPipe('v367'); assert.equal(paths.length, 0);
  const pending = ui.setPlanPipe('v362');
  await ui.loadEvidence();
  finish(response(200, { pipeline: 'revoked M4', coins: {} })); await pending;
  assert.equal(ui.state.live.plan, null);
  assert.equal(ui.planPipe(), 'v342');
});

test('admin can lock an additional free pipeline and save without changing the order', async () => {
  const initial = { order: ['v367','v321','v342','v362','v315'], automatic: true, revision: 4,
    locked: { v367: true, v321: true, v342: false, v362: false, v315: false } };
  let submitted;
  const ui = app(async (p, opts) => {
    assert.equal(opts.headers.Authorization, 'Bearer new');
    if (p === '/api/admin/pipelines' && opts.method === 'POST') {
      submitted = JSON.parse(opts.body); return response(200, { ...initial, ...submitted, revision: 5 });
    }
    if (p === '/api/admin/pipelines') return response(200, structuredClone(initial));
    return response(200, Object.fromEntries(initial.order.map((p,i) => [p, { rank:i+1, locked:false,
      locked_for_viewers: submitted.locked[p], walkforward:{} }])));
  }, storage(fresh));
  ui.state.user.role = 'admin';
  await ui.loadPipelineSettings();
  const lock = { dataset: { lock: 'v362' } };
  ui.$('pipelineSettingsTbl').onclick({ target: { closest: s => s === '[data-lock]' ? lock : null } });
  assert.ok(ui.$('pipelineSaveStatus').textContent.includes('chưa lưu'));
  await ui.$('savePipelineSettings').onclick();
  assert.deepEqual(submitted.locked, { ...initial.locked, v362: true });
  assert.equal(submitted.order, null); assert.equal(submitted.revision, 4);
  assert.ok(!ui.$('pipeEvid').innerHTML.includes('Đang khóa với người dùng thường'));
});

const fivePipelines = () => Object.fromEntries(['v367','v321','v342','v362','v315'].map((p,i) => [p, {
  rank:i+1, locked:i<2, automatic_order:true, walkforward:{}, admin_contact_email:'admin@example.com',
}]));

test('ordinary Google login immediately renders three free choices and fetches only allowed signals with a Bearer header', async () => {
  const paths = [];
  const ui = app(async (p, opts) => {
    paths.push(p);
    if (p === '/api/auth/google') {
      assert.equal(opts.credentials, 'include');
      assert.equal(JSON.parse(opts.body).credential, 'google-credential');
      return response(200, fresh);
    }
    assert.equal(opts.headers.Authorization, 'Bearer new');
    if (p === '/api/pipelines_summary') return response(200, fivePipelines());
    return response(200, {});
  }, storage(fresh));
  ui.state.user = null; ui.state.token = ''; ui.state.session = null;
  await ui.onCredential({ credential:'google-credential' });
  await new Promise(setImmediate);
  assert.equal(ui.$('tabs').hidden, false);
  assert.equal(ui.$('adminTab').hidden, true);
  const tables = () => ui.$('pipeEvid').innerHTML;
  for (const p of ['v342','v362','v315']) assert.ok(tables().includes(`data-pipe="${p}"`));
  assert.ok(!tables().includes('data-pipe="v367"'));
  assert.ok(tables().includes('Liên hệ admin qua email'));
  assert.ok(!ui.$('userBox').innerHTML.includes('class="role"'));
  assert.ok(paths.includes('/api/trade_plan?pipeline=v342'));
  assert.ok(paths.filter(p => p.includes('/api/trade_plan')).every(p => !/v367|v321/.test(p)));
  assert.ok(tables().includes('aria-pressed="true"'));
});

test('pending user can recheck account access and enter the free dashboard without signing in again', async () => {
  const ui = app(async p => {
    if (p === '/api/auth/me') return response(200, { ...user, admin_contact_email:'admin@example.com' });
    if (p === '/api/pipelines_summary') return response(200, fivePipelines());
    return response(200, {});
  }, storage(fresh));
  ui.state.user = { ...user, role:'pending', allowed_pipelines:[] };
  await ui.$('pendingRetry').onclick();
  await new Promise(setImmediate);
  assert.equal(ui.state.user.role, 'viewer');
  assert.equal(ui.$('tabs').hidden, false);
  assert.equal(ui.$('pendingRetry').disabled, false);
  assert.deepEqual(Array.from(ui.visiblePipes(), p => p.v), Array.from(user.allowed_pipelines));
});

test('admin account revocation clears visible signals and explains how to restore access', async () => {
  const ui = app(async p => {
    assert.equal(p, '/api/auth/me');
    return response(200, { ...user, role:'pending', access_revoked:true, allowed_pipelines:[], admin_contact_email:'admin@example.com' });
  }, storage(fresh));
  ui.$('board').innerHTML = 'old private signals';
  ui.$('perfKpis').innerHTML = 'old paper results';
  ui.state.live.plan = { coins:{} };
  await ui.syncAccountAccess();
  assert.equal(ui.$('board').innerHTML, '');
  assert.equal(ui.$('perfKpis').innerHTML, '');
  assert.equal(ui.state.live.plan, null);
  assert.equal(ui.$('tabs').hidden, true);
  assert.equal(ui.$('pendingTitle').textContent, 'Quyền xem đã được tạm khóa');
  assert.ok(ui.$('pendingReason').textContent.includes('thu hồi'));
  assert.equal(ui.$('pendingContact').href, 'mailto:admin%40example.com');
});

test('only admin sees the Admin tab; viewer admin hash and logout cannot retain admin controls', async () => {
  const paths = [];
  const adminUser = { ...user, role:'admin', allowed_pipelines:['v367','v321',...user.allowed_pipelines] };
  const ui = app(async p => {
    paths.push(p);
    if (p === '/api/auth/google') return response(200, { ...fresh, user:adminUser });
    if (p === '/api/auth/me') return response(200, user);
    if (p === '/api/pipelines_summary') return response(200, fivePipelines());
    return response(200, {});
  }, storage(fresh));
  await ui.onCredential({credential:'admin-google'});
  await new Promise(setImmediate);
  assert.equal(ui.$('adminTab').hidden, false);
  await ui.syncAccountAccess();
  assert.equal(ui.$('adminTab').hidden, true);
  paths.length = 0;
  ui.location.hash = '#admin';
  ui.route();
  await new Promise(setImmediate);
  assert.ok(!paths.some(p => p.startsWith('/api/admin/')));
  ui.logout(false);
  assert.equal(ui.$('adminTab').hidden, true);
  assert.equal(ui.$('tabs').hidden, true);
});

test('admin saves only the checked individual pipeline grants through a Bearer request', async () => {
  let submitted;
  const ui = app(async (p, options) => {
    assert.equal(p, '/api/admin/users');
    assert.equal(options.headers.Authorization, 'Bearer new');
    if (options.method === 'POST') { submitted = JSON.parse(options.body); return response(200, {}); }
    return response(200, [{email:user.email, approved:true, role:'viewer', granted_pipelines:['v367']}]);
  }, storage(fresh));
  ui.state.user.role = 'admin';
  await ui.loadUsers();
  assert.ok(ui.$('usersTbl').innerHTML.includes('data-grant="v367" checked'));
  const row = { querySelectorAll: selector => {
    assert.equal(selector, 'input[data-grant]:checked');
    return [{dataset:{grant:'v321'}}];
  } };
  const button = {dataset:{saveGrants:user.email}, closest: () => row};
  await ui.$('usersTbl').onclick({target:{closest: selector => selector === 'button[data-save-grants]' ? button : null}});
  assert.deepEqual(submitted, {email:user.email, pipelines:['v321']});
  assert.equal(button.disabled, false);
});

test('revoking a VIP grant clears already displayed private data and falls back to free pipelines', async () => {
  const ui = app(async p => {
    if (p === '/api/auth/me') return response(200, { ...user, allowed_pipelines:[...user.allowed_pipelines] });
    if (p === '/api/pipelines_summary') return response(200, fivePipelines());
    return response(200, {});
  }, storage(fresh));
  ui.state.user.allowed_pipelines = ['v367',...user.allowed_pipelines];
  ui.state.selectedPipeline = 'v367';
  ui.state.live.plan = {pipeline:'private VIP'};
  ui.$('board').innerHTML = 'private VIP signals';
  ui.$('perfKpis').innerHTML = 'private VIP paper results';
  await ui.syncAccountAccess();
  assert.equal(ui.$('board').innerHTML, '');
  assert.equal(ui.$('perfKpis').innerHTML, '');
  assert.notEqual(ui.state.live.plan?.pipeline, 'private VIP');
  assert.equal(ui.planPipe(), 'v342');
  assert.equal(ui.state.user.role, 'viewer');
});

test('Manual tab shows the MANUAL plan cards (locked ones offer unlock) and the order checklist; the Bot tab shows the BOT pipelines', async () => {
  const wf = { monthly_5y: 5.86, monthly_last_year: 5.22, gate_dd: 18.6, win_hidden: .686, win_dev: .65, win_all_hidden: .67,
    win_all_dev: .69, losing_years: 0, monthly_dev4: 6.0, yearly: [], trades_dev: 900, trades_hidden: 300 };
  const ev = Object.fromEntries(['v321', 'v301', 'v295', 'v367', 'v362', 'v342', 'v340', 'v315'].map((p, i) => [p, {
    rank: i + 1, locked: p === 'v362', automatic_order: true, walkforward: wf, prospective: { days: 2, live_pct: 0.4, percentile: 55 } }]));
  const plan = { decision_bar: '2026-10-04T00:00:00+00:00', next_decision: '2026-10-04T04:05:00+00:00', coins: {
    SOLUSDT: { state: 'pending', order: { side: 'BUY', price: 110, weight: 0.3, sl_if_filled: 100, tp_if_filled: 130, valid_until: '2026-10-04T12:00:00+00:00' },
      dips: [{ rung: 3, buy_limit: 105, tp: 107, stop: 95, size_frac: 0.3, active_until: '2026-10-04T03:59:00+00:00', filled: false }] } } };
  const ui = app(async p => response(200, p === '/api/pipelines_summary' ? ev : p === '/api/status' ? {} : plan), storage(fresh));
  ui.state.user.allowed_pipelines = ['v321', 'v301', 'v295', 'v367', 'v342', 'v315'];
  ui.state.user.bot_access = true;
  ui.state.view = 'todo';
  await ui.loadTodo();
  assert.equal(ui.product(), 'manual');
  assert.equal(ui.planPipe(), 'v367');
  let main = ui.$('pipeEvid').innerHTML;
  assert.ok(main.includes('data-pipe="v367"') && main.includes('data-pipe="v315"') && !main.includes('data-pipe="v321"') && main.includes('Win lệnh book'));
  const cards = ui.$('pipeCards').innerHTML;
  for (const p of ['v367', 'v342', 'v340', 'v315']) assert.ok(cards.includes(`data-pipe="${p}"`));
  assert.ok(!cards.includes('data-pipe="v362"') && cards.includes('Liên hệ mở khóa') && cards.includes('VIP') && cards.includes('Khuyên dùng'));
  assert.ok(cards.includes('5.9%') && cards.includes('+0.40%'));
  assert.equal(ui.$('goalPanel').hidden, true);  // research goal progress: admins only
  assert.ok(ui.$('goalPanel').innerHTML.includes('Mục tiêu 1') && ui.$('goalPanel').innerHTML.includes('đạt trên mô phỏng'));
  assert.equal(ui.$('manualChecklist').hidden, false);
  assert.ok(ui.$('manualChecklist').innerHTML.includes('Bắt đáy') && ui.$('manualChecklist').innerHTML.includes('Vào lệnh xu hướng'));
  ui.state.view = 'bot';
  await ui.loadTodo();
  assert.equal(ui.product(), 'bot');
  assert.equal(ui.planPipe(), 'v321');
  main = ui.$('pipeEvid').innerHTML;
  assert.ok(ui.$('pipeCards').innerHTML.includes('Bot Pro') && !ui.$('pipeCards').innerHTML.includes('VIP'));
  assert.ok(main.includes('data-pipe="v321"') && main.includes('data-pipe="v295"') && !main.includes('data-pipe="v367"') && main.includes('Win mọi lệnh'));
  assert.ok(ui.$('goalPanel').innerHTML.includes('Mục tiêu BOT') && ui.$('goalPanel').innerHTML.includes('chưa đạt'));
  assert.equal(ui.$('manualChecklist').hidden, true);
  assert.equal(ui.$('botNote').hidden, false);
});
