const API_BASE = 'http://127.0.0.1:8000';
const POLL_INTERVAL_MS = 30_000;
let PAGE_SIZE = 30;  // overwritten from /config on startup

let lastMessagesTotal = -1;
let agentEnabled = false;

// Local caches — plain objects for fast lookup
let messageCache  = {};  // id → msg
let responseCache = {};  // message_id → response

// Per-panel server totals (how many of each type exist on the server)
const panelTotals = {
  offer_received: 0, order_created: 0, loading_confirmed: 0,
  delivery_confirmed: 0, new_freight: 0, other: 0,
};

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

function debug(msg) { console.debug('[transport]', msg); }

function fmt(iso) {
  if (!iso) return '';
  try { return new Date(iso).toLocaleString('pl-PL', { dateStyle: 'short', timeStyle: 'medium' }); }
  catch { return iso; }
}

function esc(s) {
  return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// ── canary ────────────────────────────────────────────────────────────────────

const DOT = { idle: 'green', new: 'blue', error: 'red', init: 'grey' };

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

// ── edit / send response ──────────────────────────────────────────────────────

const editingState = {};  // messageId → { text: string }
const draftTexts   = {};  // messageId → saved-but-not-sent text

function startEdit(messageId) {
  const resp = responseCache[messageId];
  const current = draftTexts[messageId] ?? (resp ? resp.response : '');
  editingState[messageId] = { text: current };
  renderAll();
}

function saveEdit(messageId) {
  const ta = document.querySelector(`[data-edit-ta="${messageId}"]`);
  if (ta) draftTexts[messageId] = ta.value;
  delete editingState[messageId];
  renderAll();
}

function cancelEdit(messageId) {
  delete editingState[messageId];
  renderAll();
}

function discardDraft(messageId) {
  delete draftTexts[messageId];
  renderAll();
}

async function sendResponse(messageId) {
  // If in edit mode, read current textarea value
  const editing = editingState[messageId];
  const ta = document.querySelector(`[data-edit-ta="${messageId}"]`);
  if (ta && editing) editing.text = ta.value;

  const btn = document.querySelector(`[data-send="${messageId}"]`);
  if (btn) { btn.disabled = true; btn.textContent = 'Wysyłanie…'; }

  const textToSend = editing?.text ?? draftTexts[messageId] ?? null;
  const body = textToSend ? { text: textToSend } : null;
  const r = await callApi(`/responses/${messageId}/send`, 'POST', body);

  if (r.ok) {
    delete editingState[messageId];
    delete draftTexts[messageId];
    if (responseCache[messageId]) {
      responseCache[messageId].sent = true;
      responseCache[messageId].sent_text = r.body.sent_text ?? null;
    }
    renderAll();
  } else {
    if (btn) { btn.disabled = false; btn.textContent = '▷ Wyślij'; }
    debug(`Send failed: ${r.status}`);
  }
}

// ── rendering ─────────────────────────────────────────────────────────────────

function msgBadgeClass(msg) {
  const src = (msg.source || '').toLowerCase();
  if (src === 'email') return 'badge-email';
  if (msg.event_type) return 'badge-transeu';
  return 'badge-other';
}

function msgBadgeLabel(msg) {
  const src = (msg.source || '').toLowerCase();
  if (src === 'email') return 'E-mail';
  if (msg.event_type) return 'Trans.eu';
  return 'Ręczna';
}

function panelFor(msg) {
  if (msg.event_type && EVENT_PANEL[msg.event_type]) return EVENT_PANEL[msg.event_type];
  return 'other';
}

function buildCard(msg, response) {
  const badgeClass = msgBadgeClass(msg);
  const badgeLabel = msgBadgeLabel(msg);

  let responseHtml;
  if (response) {
    const editing = editingState[msg.id];
    if (response.sent) {
      const wasEdited = response.sent_text && response.sent_text !== response.response;
      responseHtml = `
        <div class="msg-section response">
          <div class="response-label">▷ Wysłana odpowiedź</div>
          <div class="response-text">${esc(response.sent_text ?? response.response)}</div>
          <div class="response-actions">
            <span class="sent-label">✓ Wysłano</span>
            ${wasEdited ? '<span class="sent-edited-badge">edytowana</span>' : ''}
          </div>
        </div>`;
    } else if (editing) {
      responseHtml = `
        <div class="msg-section response">
          <div class="response-label">✏️ Edytujesz odpowiedź</div>
          <textarea class="response-textarea" data-edit-ta="${esc(msg.id)}">${esc(editing.text)}</textarea>
          <div class="response-actions">
            <button class="send-btn" data-send="${esc(msg.id)}" onclick="sendResponse('${esc(msg.id)}')">▷ Wyślij</button>
            <button class="edit-btn" onclick="saveEdit('${esc(msg.id)}')">💾 Zapisz</button>
            <button class="cancel-btn" onclick="cancelEdit('${esc(msg.id)}')">Anuluj</button>
          </div>
        </div>`;
    } else {
      const hasDraft = !!draftTexts[msg.id];
      const displayText = hasDraft ? draftTexts[msg.id] : response.response;
      const label = hasDraft ? '✏️ Zapisana wersja robocza' : '▷ Sugerowana odpowiedź agenta';
      responseHtml = `
        <div class="msg-section response">
          <div class="response-label">${label}</div>
          <div class="response-text">${esc(displayText)}</div>
          <div class="response-actions">
            <button class="send-btn" data-send="${esc(msg.id)}" onclick="sendResponse('${esc(msg.id)}')">▷ Wyślij</button>
            <button class="edit-btn" onclick="startEdit('${esc(msg.id)}')">✏️ Edytuj</button>
            ${hasDraft ? `<button class="cancel-btn" onclick="discardDraft('${esc(msg.id)}')">↩ Przywróć oryginał</button>` : ''}
          </div>
        </div>`;
    }
  } else {
    responseHtml = `
      <div class="msg-section response">
        <div class="no-response">Brak odpowiedzi — agent nie przetworzył.</div>
      </div>`;
  }

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

const EMPTY_TEXTS = {
  offer_received:    'Brak ofert.',
  order_created:     'Brak zleceń.',
  loading_confirmed: 'Brak potwierdzeń załadunku.',
  delivery_confirmed:'Brak potwierdzonych dostaw.',
  new_freight:       'Brak nowych ładunków.',
  other:             'Brak wiadomości.',
};

function renderAll() {
  // Preserve any open textarea values before re-render
  for (const [msgId, state] of Object.entries(editingState)) {
    const ta = document.querySelector(`[data-edit-ta="${msgId}"]`);
    if (ta) state.text = ta.value;
  }
  renderPanels(Object.values(messageCache), responseCache);
}

function renderPanels(messages, respMap) {
  const groups = {
    offer_received: [], order_created: [], loading_confirmed: [],
    delivery_confirmed: [], new_freight: [], other: [],
  };
  for (const msg of messages) groups[panelFor(msg)].push(msg);

  for (const [panelId, msgs] of Object.entries(groups)) {
    const listEl  = document.getElementById(`list-${panelId}`);
    const countEl = document.getElementById(`count-${panelId}`);
    if (!listEl) continue;

    const total = panelTotals[panelId] ?? msgs.length;
    countEl.textContent = total || msgs.length;
    countEl.className   = `panel-count ${msgs.length > 0 ? 'has-items' : ''}`;

    let html = '';
    if (!msgs.length) {
      html = `<div class="empty-panel">${EMPTY_TEXTS[panelId] ?? 'Brak.'}</div>`;
    } else {
      html = [...msgs]
        .sort((a, b) => (b.datetime ?? '').localeCompare(a.datetime ?? ''))
        .map(msg => buildCard(msg, respMap[msg.id]))
        .join('');
    }

    // Per-panel load more — only when there are more on the server
    const remaining = total - msgs.length;
    if (remaining > 0) {
      html += `<button class="panel-load-more" id="plm-${panelId}"
                       onclick="loadMore('${panelId}')">
        ↓ Załaduj starsze (${remaining})
      </button>`;
    }

    listEl.innerHTML = html;
  }
}

// ── sync ──────────────────────────────────────────────────────────────────────

async function syncAll() {
  const [msgR, respR, totalsR] = await Promise.all([
    callApi(`/messages?limit=${PAGE_SIZE}`),
    callApi('/responses'),
    callApi('/messages/totals'),
  ]);
  if (!msgR.ok || !respR.ok) {
    debug(`Sync błąd: messages=${msgR.status} responses=${respR.status}`);
    return;
  }

  for (const msg of msgR.body.messages ?? []) messageCache[msg.id] = msg;

  responseCache = {};
  for (const r of respR.body.responses ?? []) responseCache[r.message_id] = r;

  if (totalsR.ok) {
    for (const [panel, n] of Object.entries(totalsR.body)) {
      if (panel in panelTotals) panelTotals[panel] = n;
    }
  }

  const globalTotal = msgR.body.total ?? 0;
  lastMessagesTotal = globalTotal;
  renderAll();
  debug(`Sync: ${Object.keys(messageCache).length} w cache, totals: ${JSON.stringify(panelTotals)}`);
}

async function loadMore(panelId) {
  const btn = document.getElementById(`plm-${panelId}`);
  if (btn) { btn.disabled = true; btn.textContent = 'Ładowanie…'; }

  // offset = how many of this panel's messages are already in cache
  const offset = Object.values(messageCache).filter(m => panelFor(m) === panelId).length;
  const r = await callApi(`/messages?panel=${panelId}&limit=${PAGE_SIZE}&offset=${offset}`);
  if (!r.ok) { renderAll(); return; }

  for (const msg of r.body.messages ?? []) messageCache[msg.id] = msg;
  // update total in case it changed
  if (typeof r.body.total === 'number') panelTotals[panelId] = r.body.total;

  renderAll();
  debug(`LoadMore ${panelId}: +${r.body.messages?.length ?? 0}, cached=${offset + (r.body.messages?.length ?? 0)}`);
}

// ── chat widget ──────────────────────────────────────────────────────────────

let chatOpen = false;
let chatHistory = [];   // [{role, content}]

function toggleChat() {
  chatOpen = !chatOpen;
  document.getElementById('chatPanel').classList.toggle('open', chatOpen);
  document.getElementById('chatFab').classList.toggle('open', chatOpen);
  if (chatOpen) {
    document.getElementById('chatInput').focus();
    scrollChatToBottom();
  }
}

function scrollChatToBottom() {
  const el = document.getElementById('chatMessages');
  if (el) el.scrollTop = el.scrollHeight;
}

function appendBubble(role, text) {
  const empty = document.getElementById('chatEmpty');
  if (empty) empty.remove();

  const div = document.createElement('div');
  div.className = `chat-bubble ${role}`;
  div.textContent = text;
  document.getElementById('chatMessages').appendChild(div);
  scrollChatToBottom();
  return div;
}

async function sendChat() {
  const input = document.getElementById('chatInput');
  const sendBtn = document.getElementById('chatSend');
  const text = input.value.trim();
  if (!text) return;

  input.value = '';
  input.disabled = true;
  sendBtn.disabled = true;

  appendBubble('user', text);

  // Typing indicator
  const typingEl = document.createElement('div');
  typingEl.className = 'chat-bubble typing';
  typingEl.textContent = 'Asystent pisze…';
  document.getElementById('chatMessages').appendChild(typingEl);
  scrollChatToBottom();

  const r = await callApi('/chat', 'POST', { message: text, history: chatHistory });

  typingEl.remove();
  input.disabled = false;
  sendBtn.disabled = false;
  input.focus();

  if (r.ok) {
    const reply = r.body.response ?? '';
    chatHistory.push({ role: 'user', content: text });
    chatHistory.push({ role: 'assistant', content: reply });
    appendBubble('assistant', reply);
  } else {
    appendBubble('assistant', `Błąd połączenia (${r.status}). Sprawdź czy serwer działa.`);
  }
}

// ── init ──────────────────────────────────────────────────────────────────────

window.addEventListener('load', async () => {
  const cfgR = await callApi('/config');
  if (cfgR.ok && cfgR.body.page_size) PAGE_SIZE = cfgR.body.page_size;

  refreshAgentStatus();
  pollCanary();
  setInterval(pollCanary, POLL_INTERVAL_MS);
});
