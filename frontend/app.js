const API_BASE = 'http://127.0.0.1:8000';
const POLL_INTERVAL_MS = 30_000;

let lastMessagesTotal = -1;
let agentEnabled = false;

// Maps Trans.eu event_type → panel id
const EVENT_PANEL = {
  'freights.freight.offer_received':              'offer_received',
  'freight_orders.order.created':                 'order_created',
  'freight_orders.order.loading_confirmed':       'loading_confirmed',
  'freight_orders.order.unloading_confirmed':     'loading_confirmed',
  'freight_orders.order.delivery_was_confirmed':  'delivery_confirmed',
  'freight_orders.order.transports_was_finished': 'delivery_confirmed',
  'freights.freight.published':                   'new_freight',
};

// ── API ───────────────────────────────────────────────────────────────────────

async function callApi(path, method = 'GET', body = null) {
  const opts = { method, headers: { 'Content-Type': 'application/json' } };
  if (body) opts.body = JSON.stringify(body);
  try {
    const res = await fetch(`${API_BASE}${path}`, opts);
    const text = await res.text();
    try { return { ok: res.ok, status: res.status, body: JSON.parse(text) }; }
    catch { return { ok: res.ok, status: res.status, body: text }; }
  } catch (err) {
    return { ok: false, status: 0, body: err.message };
  }
}

function debug(msg) {
  document.getElementById('debugOutput').textContent = msg;
}

function fmt(iso) {
  if (!iso) return '';
  try { return new Date(iso).toLocaleString('pl-PL', { dateStyle: 'short', timeStyle: 'medium' }); }
  catch { return iso; }
}

function esc(s) {
  return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// ── canary ────────────────────────────────────────────────────────────────────

const DOT = { idle:'green', new:'blue', error:'red', init:'grey' };

function setCanary(state, text) {
  const el = document.getElementById('canary');
  if (!el) return;
  el.className = state;
  const dot = el.querySelector('.dot');
  if (dot) dot.className = 'dot ' + (DOT[state] ?? 'grey');
  const label = document.getElementById('canaryText');
  if (label) label.textContent = text;
}

async function pollCanary() {
  const r = await callApi('/poll');
  if (!r.ok) {
    setCanary('error', `Brak API (${r.status || 'timeout'})`);
    return;
  }
  const d = r.body;
  const total = typeof d.messages_total === 'number' ? d.messages_total : 0;
  const time = fmt(d.checked_at);

  if (lastMessagesTotal === -1) {
    lastMessagesTotal = total;
    setCanary('idle', `Aktywne · ${total} wiad. · ${time}`);
    await syncAll();
    return;
  }

  if (total > lastMessagesTotal) {
    const n = total - lastMessagesTotal;
    lastMessagesTotal = total;
    setCanary('new', `+${n} nowych · ${time}`);
    await syncAll();
  } else {
    setCanary('idle', `Aktywne · ${total} wiad. · ${time}`);
    debug(`Sprawdzono: ${time}`);
  }
}

// ── agent toggle ──────────────────────────────────────────────────────────────

function renderAgentToggle(enabled) {
  agentEnabled = enabled;
  const btn = document.getElementById('agentToggle');
  const text = btn.querySelector('.toggle-text');
  if (enabled) {
    btn.className = 'agent-toggle on';
    text.textContent = 'Agent aktywny';
  } else {
    btn.className = 'agent-toggle off';
    text.textContent = 'Agent wyłączony';
  }
}

async function refreshAgentStatus() {
  const r = await callApi('/agent/status');
  if (r.ok) renderAgentToggle(r.body.agent_enabled);
}

async function toggleAgent() {
  const path = agentEnabled ? '/agent/disable' : '/agent/enable';
  const r = await callApi(path, 'POST');
  if (r.ok) renderAgentToggle(r.body.agent_enabled);
}

// ── rendering ─────────────────────────────────────────────────────────────────

function msgBadgeClass(msg) {
  const src = (msg.source || '').toLowerCase();
  if (src === 'email') return 'badge-email';
  if (msg.event_type)  return 'badge-transeu';
  return 'badge-other';
}

function msgBadgeLabel(msg) {
  const src = (msg.source || '').toLowerCase();
  if (src === 'email') return 'E-mail';
  if (msg.event_type)  return 'Trans.eu';
  return 'Ręczna';
}

function panelFor(msg) {
  if (msg.event_type && EVENT_PANEL[msg.event_type]) return EVENT_PANEL[msg.event_type];
  return 'other';
}

function buildCard(msg, response) {
  const badgeClass = msgBadgeClass(msg);
  const badgeLabel = msgBadgeLabel(msg);

  const responseHtml = response
    ? `<div class="msg-section response">
         <div class="response-label">▷ Sugerowana odpowiedź agenta</div>
         <div class="response-text">${esc(response.response)}</div>
       </div>`
    : `<div class="msg-section response">
         <div class="no-response">Brak odpowiedzi — agent nie przetworzył.</div>
       </div>`;

  return `
    <div class="msg-card">
      <div class="msg-section incoming">
        <div class="msg-meta">
          <span class="msg-type-badge ${badgeClass}">${badgeLabel}</span>
          <span class="msg-sender">${esc(msg.sender)}</span>
          <span class="msg-time">${fmt(msg.datetime)}</span>
        </div>
        <div class="msg-text">${esc(msg.text)}</div>
        <div class="msg-id">${esc(msg.id)}</div>
      </div>
      ${responseHtml}
    </div>`;
}

function renderPanels(messages, respMap) {
  // group messages by panel
  const groups = { offer_received:[], order_created:[], loading_confirmed:[], delivery_confirmed:[], new_freight:[], other:[] };
  for (const msg of messages) {
    const panel = panelFor(msg);
    groups[panel].push(msg);
  }

  for (const [panelId, msgs] of Object.entries(groups)) {
    const listEl = document.getElementById(`list-${panelId}`);
    const countEl = document.getElementById(`count-${panelId}`);
    if (!listEl) continue;

    countEl.textContent = msgs.length;
    countEl.className = `panel-count ${msgs.length > 0 ? 'has-items' : ''}`;

    if (!msgs.length) {
      const emptyTexts = {
        offer_received: 'Brak ofert.',
        order_created: 'Brak zleceń.',
        loading_confirmed: 'Brak potwierdzeń załadunku.',
        delivery_confirmed: 'Brak potwierdzonych dostaw.',
        new_freight: 'Brak nowych ładunków.',
        other: 'Brak wiadomości.',
      };
      listEl.innerHTML = `<div class="empty-panel">${emptyTexts[panelId] ?? 'Brak.'}</div>`;
      continue;
    }

    // newest first
    listEl.innerHTML = [...msgs].reverse()
      .map(msg => buildCard(msg, respMap[msg.id]))
      .join('');
  }
}

// ── sync ──────────────────────────────────────────────────────────────────────

async function syncAll() {
  const [msgR, respR] = await Promise.all([
    callApi('/messages'),
    callApi('/responses'),
  ]);

  if (!msgR.ok || !respR.ok) {
    debug(`Sync błąd: messages=${msgR.status} responses=${respR.status}`);
    return;
  }

  const messages = msgR.body.messages ?? [];
  const responses = respR.body.responses ?? [];

  // build response lookup by message_id
  const respMap = {};
  for (const r of responses) respMap[r.message_id] = r;

  renderPanels(messages, respMap);
  lastMessagesTotal = messages.length;
  debug(`Sync: ${messages.length} wiad., ${responses.length} odp. · ${fmt(new Date().toISOString())}`);
}

// ── init ──────────────────────────────────────────────────────────────────────

window.addEventListener('load', () => {
  refreshAgentStatus();
  pollCanary();
  setInterval(pollCanary, POLL_INTERVAL_MS);
});
