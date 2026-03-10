/**
 * Classification suggestions UI.
 * API layer is abstracted: swap getSuggestions() implementation when backend is ready.
 */

/**
 * Classification suggestion (matches backend Suggestion schema: client_name, matter_name, score, rationale).
 * @typedef {{ client_name: string, matter_name: string, score: number, rationale?: string }} ClassificationSuggestion
 */

/**
 * Fetch classification suggestions for a time entry.
 * Abstracted: replace with real API call when backend is ready.
 * @param {Object} entry - Time entry payload (snake_case for API)
 * @returns {Promise<ClassificationSuggestion[]>}
 */
async function getSuggestions(entry) {
  // When backend is ready, use:
  // const res = await fetch('/suggestions', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(entry) });
  // if (!res.ok) throw new Error(await res.text());
  // const data = await res.json();
  // return data.suggestions;

  // Mock delay and data
  await new Promise((r) => setTimeout(r, 600));
  return [
    {
      client_name: 'Smith & Associates LLC',
      matter_name: 'Contract Dispute - Johnson Supply Agreement',
      score: 0.92,
      rationale: 'Narrative mentions "Smith" and "contract dispute"; strong match to this matter.',
    },
    {
      client_name: 'Acme Corporation',
      matter_name: 'Securities Investigation - SEC Inquiry',
      score: 0.71,
      rationale: 'Keywords overlap with regulatory and investigation matter.',
    },
    {
      client_name: 'Northgate Holdings Inc.',
      matter_name: 'IP Licensing - Patent Portfolio',
      score: 0.58,
      rationale: 'Possible research context; lower confidence.',
    },
  ];
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
 * @returns {HTMLLIElement}
 */
function renderSuggestion(suggestion, index) {
  const li = document.createElement('li');
  li.className = 'suggestion-item';
  li.setAttribute('role', 'listitem');
  li.dataset.index = String(index);

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

function setFeedback(itemEl, status) {
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

function showSuggestions(suggestions) {
  hide($('suggestions-empty'));
  hide($('suggestions-loading'));
  hide($('suggestions-error'));

  const list = $('suggestions-list');
  list.innerHTML = '';
  suggestions.forEach((s, i) => list.appendChild(renderSuggestion(s, i)));
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
    showSuggestions(suggestions);
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
