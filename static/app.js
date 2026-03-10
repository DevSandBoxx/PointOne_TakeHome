/**
 * Classification suggestions UI.
 * API layer is abstracted: swap getSuggestions() implementation when backend is ready.
 */

/**
 * Classification suggestion (matches backend Suggestion schema).
 * @typedef {{ client_id: string, matter_id: string, client_name: string, matter_name: string, score: number, rationale?: string }} ClassificationSuggestion
 */

/**
 * Fetch classification suggestions for a time entry (Phase 2: real API).
 * @param {Object} entry - Time entry payload (snake_case for API)
 * @returns {Promise<ClassificationSuggestion[]>}
 */
async function getSuggestions(entry) {
  const res = await fetch('/suggestions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(entry),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Request failed: ${res.status}`);
  }
  const data = await res.json();
  return data.suggestions;
}

/**
 * POST feedback (accept/reject) for a suggestion.
 * @param {{ user_id: string, entry_id: string, client_id: string, matter_id: string, action: 'accepted'|'rejected' }} payload
 */
async function postFeedback(payload) {
  const res = await fetch('/feedback', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Feedback failed: ${res.status}`);
  }
  return res.json();
}

function $(id) {
  return document.getElementById(id);
}

function show(el) {
  el.classList.remove('hidden');
}

function hide(el) {
  el.classList.add('hidden');
}

function formatScore(score) {
  return `${Math.round(score * 100)}%`;
}

/**
 * @param {ClassificationSuggestion} suggestion
 * @param {number} index
 * @param {{ user_id: string, entry_id: string }} entry
 * @returns {HTMLLIElement}
 */
function renderSuggestion(suggestion, index, entry) {
  const li = document.createElement('li');
  li.className = 'suggestion-item';
  li.setAttribute('role', 'listitem');
  li.dataset.index = String(index);
  li.dataset.clientId = suggestion.client_id;
  li.dataset.matterId = suggestion.matter_id;
  li.dataset.userId = entry.user_id;
  li.dataset.entryId = entry.entry_id;

  const clientMatter = `${suggestion.client_name} — ${suggestion.matter_name}`;
  li.innerHTML = `
    <div class="suggestion-header">
      <span class="suggestion-client-matter">${escapeHtml(clientMatter)}</span>
      <span class="suggestion-score">${formatScore(suggestion.score)}</span>
    </div>
    ${suggestion.rationale ? `<p class="suggestion-rationale">${escapeHtml(suggestion.rationale)}</p>` : ''}
    <div class="suggestion-actions">
      <button type="button" class="btn btn-sm btn-accept" data-action="accept">Accept</button>
      <button type="button" class="btn btn-sm btn-reject" data-action="reject">Reject</button>
    </div>
  `;

  const acceptBtn = li.querySelector('[data-action="accept"]');
  const rejectBtn = li.querySelector('[data-action="reject"]');

  acceptBtn.addEventListener('click', () => setFeedback(li, 'accepted'));
  rejectBtn.addEventListener('click', () => setFeedback(li, 'rejected'));

  return li;
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

async function setFeedback(itemEl, status) {
  const user_id = itemEl.dataset.userId;
  const entry_id = itemEl.dataset.entryId;
  const client_id = itemEl.dataset.clientId;
  const matter_id = itemEl.dataset.matterId;

  try {
    await postFeedback({ user_id, entry_id, client_id, matter_id, action: status });
  } catch (err) {
    console.error('Failed to record feedback:', err);
    return;
  }

  itemEl.classList.remove('accepted', 'rejected');
  itemEl.classList.add(status);
  const actions = itemEl.querySelector('.suggestion-actions');
  if (actions) {
    const feedback = document.createElement('div');
    feedback.className = 'feedback';
    feedback.textContent = status === 'accepted' ? 'Accepted' : 'Rejected';
    actions.replaceWith(feedback);
  }
}

function buildEntryPayload() {
  const narrative = $('narrative').value.trim();
  const hours = parseFloat($('hours').value) || 0;
  const entryDate = $('entry-date').value;
  const clientName = $('client-name').value.trim() || null;
  const matterName = $('matter-name').value.trim() || null;

  return {
    user_id: 'current-user',
    entry_id: `entry-${Date.now()}`,
    narrative,
    hours,
    entry_date: entryDate || new Date().toISOString().slice(0, 10),
    client_name: clientName,
    matter_name: matterName,
  };
}

function showEmpty() {
  hide($('suggestions-loading'));
  hide($('suggestions-error'));
  hide($('suggestions-list'));
  show($('suggestions-empty'));
}

function showLoading() {
  hide($('suggestions-empty'));
  hide($('suggestions-error'));
  hide($('suggestions-list'));
  show($('suggestions-loading'));
}

function showError(message) {
  hide($('suggestions-empty'));
  hide($('suggestions-loading'));
  hide($('suggestions-list'));
  $('suggestions-error').textContent = message;
  show($('suggestions-error'));
}

function showSuggestions(suggestions, entry) {
  hide($('suggestions-empty'));
  hide($('suggestions-loading'));
  hide($('suggestions-error'));

  const list = $('suggestions-list');
  list.innerHTML = '';
  suggestions.forEach((s, i) => list.appendChild(renderSuggestion(s, i, entry)));
  show(list);
}

async function onSubmit(e) {
  e.preventDefault();
  const btn = $('submit-btn');
  btn.disabled = true;
  showLoading();

  try {
    const entry = buildEntryPayload();
    const suggestions = await getSuggestions(entry);
    showSuggestions(suggestions, entry);
  } catch (err) {
    showError(err.message || 'Failed to load suggestions.');
  } finally {
    btn.disabled = false;
  }
}

function initDateInput() {
  const dateInput = $('entry-date');
  if (!dateInput.value) {
    dateInput.value = new Date().toISOString().slice(0, 10);
  }
}

$('entry-form').addEventListener('submit', onSubmit);
initDateInput();
