/**
 * Classification suggestions UI.
 * API layer is abstracted: swap getSuggestions() implementation when backend is ready.
 */

/**
 * Classification suggestion (matches backend Suggestion schema).
 * @typedef {{ client_id: string, matter_id: string, client_name: string, matter_name: string, score: number, semantic_score: number, keyword_score: number, affinity: number, recency: number, rationale?: string, llm_rationale?: string, llm_status?: 'disabled'|'pending'|'ready'|'error' }} ClassificationSuggestion
 */

/**
 * Fetch classification suggestions for a time entry (Phase 2: real API).
 * @param {Object} entry - Time entry payload (snake_case for API)
 * @returns {Promise<{ low_confidence: boolean, suggestions: ClassificationSuggestion[] }>}
 */
async function getSuggestions(entry) {
  const res = await fetch("/suggestions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(entry),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Request failed: ${res.status}`);
  }
  return res.json();
}

/**
 * POST feedback (accept/reject) for a suggestion.
 * @param {{ user_id: string, entry_id: string, client_id: string, matter_id: string, action: 'accepted'|'rejected' }} payload
 */
async function postFeedback(payload) {
  const res = await fetch("/feedback", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
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

// Cancel / supersede in-flight LLM polling when user resubmits.
let _llmPoll = {
  token: 0,
  controller: null,
};

function show(el) {
  el.classList.remove("hidden");
}

function hide(el) {
  el.classList.add("hidden");
}

function formatScore(score) {
  return `${Math.round(score * 100)}%`;
}

function formatPct01(x) {
  return `${Math.round((x || 0) * 100)}%`;
}

function renderRichText(text) {
  // Minimal rich text: escape then support **bold** and newlines.
  const escaped = escapeHtml(text || "");
  return escaped
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\n/g, "<br />");
}

/**
 * @param {ClassificationSuggestion} suggestion
 * @param {number} index
 * @param {{ user_id: string, entry_id: string }} entry
 * @returns {HTMLLIElement}
 */
function renderSuggestion(suggestion, index, entry) {
  const li = document.createElement("li");
  li.className = "suggestion-item";
  li.setAttribute("role", "listitem");
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
    <div class="suggestion-meta muted">
      Semantic: ${formatPct01(suggestion.semantic_score)} · Keywords: ${formatPct01(suggestion.keyword_score)}
      · Affinity: ${formatPct01(suggestion.affinity)} · Recency: ${formatPct01(suggestion.recency)}
    </div>
    ${suggestion.rationale ? `<p class="suggestion-rationale">${escapeHtml(suggestion.rationale)}</p>` : ""}
    <div class="llm-block" data-llm>
      <div class="llm-header muted">LLM interpretation</div>
      <div class="llm-loading" data-llm-loading>
        <div class="skeleton-line"></div>
        <div class="skeleton-line"></div>
      </div>
      <div class="llm-text hidden" data-llm-text></div>
      <div class="llm-error hidden error" data-llm-error></div>
    </div>
    <div class="suggestion-actions">
      <button type="button" class="btn btn-sm btn-accept" data-action="accept">Accept</button>
      <button type="button" class="btn btn-sm btn-reject" data-action="reject">Reject</button>
    </div>
  `;

  const acceptBtn = li.querySelector('[data-action="accept"]');
  const rejectBtn = li.querySelector('[data-action="reject"]');

  acceptBtn.addEventListener("click", () => setFeedback(li, "accepted"));
  rejectBtn.addEventListener("click", () => setFeedback(li, "rejected"));

  return li;
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

async function setFeedback(itemEl, status) {
  const user_id = itemEl.dataset.userId;
  const entry_id = itemEl.dataset.entryId;
  const client_id = itemEl.dataset.clientId;
  const matter_id = itemEl.dataset.matterId;

  try {
    await postFeedback({
      user_id,
      entry_id,
      client_id,
      matter_id,
      action: status,
    });
  } catch (err) {
    console.error("Failed to record feedback:", err);
    return;
  }

  itemEl.classList.remove("accepted", "rejected");
  itemEl.classList.add(status);
  const actions = itemEl.querySelector(".suggestion-actions");
  if (actions) {
    const feedback = document.createElement("div");
    feedback.className = "feedback";
    feedback.textContent = status === "accepted" ? "Accepted" : "Rejected";
    actions.replaceWith(feedback);
  }
}

function buildEntryPayload() {
  const narrative = $("narrative").value.trim();
  const hours = parseFloat($("hours").value) || 0;
  const entryDate = $("entry-date").value;
  const clientName = $("client-name").value.trim() || null;
  const matterName = $("matter-name").value.trim() || null;

  return {
    user_id: "current-user",
    entry_id: `entry-${Date.now()}`,
    narrative,
    hours,
    entry_date: entryDate || new Date().toISOString().slice(0, 10),
    client_name: clientName,
    matter_name: matterName,
  };
}

function showEmpty() {
  hide($("suggestions-loading"));
  hide($("suggestions-error"));
  hide($("suggestions-list"));
  show($("suggestions-empty"));
}

function showLoading() {
  hide($("suggestions-empty"));
  hide($("suggestions-error"));
  hide($("suggestions-list"));
  show($("suggestions-loading"));
}

function showError(message) {
  hide($("suggestions-empty"));
  hide($("suggestions-loading"));
  hide($("suggestions-list"));
  $("suggestions-error").textContent = message;
  show($("suggestions-error"));
}

function showSuggestions(result, entry) {
  hide($("suggestions-empty"));
  hide($("suggestions-loading"));
  hide($("suggestions-error"));

  const low = $("suggestions-low-confidence");
  if (result.low_confidence) show(low);
  else hide(low);

  const list = $("suggestions-list");
  list.innerHTML = "";
  result.suggestions.forEach((s, i) =>
    list.appendChild(renderSuggestion(s, i, entry)),
  );
  show(list);

  // Start async LLM hydration after initial render.
  hydrateLlms(entry, result.suggestions, _llmPoll.token, _llmPoll.controller);
}

async function fetchLlms(user_id, entry_id, signal) {
  const url = `/suggestions/llm?user_id=${encodeURIComponent(user_id)}&entry_id=${encodeURIComponent(entry_id)}`;
  const res = await fetch(url, { signal });
  if (!res.ok) throw new Error(`LLM poll failed: ${res.status}`);
  return res.json();
}

function applyLlmsToDom(entry, mapping) {
  const items = $("suggestions-list").querySelectorAll(".suggestion-item");
  items.forEach((li) => {
    const key = `${li.dataset.clientId}::${li.dataset.matterId}`;
    const llm = mapping[key];
    const loading = li.querySelector("[data-llm-loading]");
    const text = li.querySelector("[data-llm-text]");
    const err = li.querySelector("[data-llm-error]");
    if (!loading || !text || !err) return;
    if (llm && llm.llm_rationale) {
      loading.classList.add("hidden");
      err.classList.add("hidden");
      text.classList.remove("hidden");
      text.innerHTML = renderRichText(llm.llm_rationale);
    }
  });
}

async function hydrateLlms(entry, suggestions, token, controller) {
  // If LLM is disabled, hide loaders.
  const anyPending = suggestions.some((s) => s.llm_status === "pending");
  if (!anyPending) {
    const items = $("suggestions-list").querySelectorAll("[data-llm-loading]");
    items.forEach((el) => el.classList.add("hidden"));
    return;
  }

  const start = Date.now();
  // Ollama can easily take 20s+ on first load / CPU. Give it more time.
  const timeoutMs = 60000;
  const intervalMs = 1000;

  while (Date.now() - start < timeoutMs) {
    if (_llmPoll.token !== token) return; // superseded by a new submit
    let data;
    try {
      data = await fetchLlms(entry.user_id, entry.entry_id, controller?.signal);
    } catch (e) {
      if (e && e.name === "AbortError") return;
      // keep showing skeleton; try again
      await new Promise((r) => setTimeout(r, intervalMs));
      continue;
    }

    if (data.status === "ready") {
      const mapping = {};
      (data.rationales || []).forEach((r) => {
        mapping[`${r.client_id}::${r.matter_id}`] = r;
      });
      applyLlmsToDom(entry, mapping);
      return;
    }

    if (data.status === "error") {
      const items = $("suggestions-list").querySelectorAll(".suggestion-item");
      items.forEach((li) => {
        const loading = li.querySelector("[data-llm-loading]");
        const err = li.querySelector("[data-llm-error]");
        if (!loading || !err) return;
        loading.classList.add("hidden");
        err.classList.remove("hidden");
        err.textContent = "LLM interpretation failed to load.";
      });
      return;
    }

    await new Promise((r) => setTimeout(r, intervalMs));
  }

  // Timed out: keep skeleton visible; user can resubmit or wait longer.
}

async function onSubmit(e) {
  e.preventDefault();
  const btn = $("submit-btn");
  btn.disabled = true;
  showLoading();

  try {
    // Cancel any previous polling loop + request.
    _llmPoll.token += 1;
    if (_llmPoll.controller) _llmPoll.controller.abort();
    _llmPoll.controller = new AbortController();

    const entry = buildEntryPayload();
    const result = await getSuggestions(entry);
    showSuggestions(result, entry);
  } catch (err) {
    showError(err.message || "Failed to load suggestions.");
  } finally {
    btn.disabled = false;
  }
}

function initDateInput() {
  const dateInput = $("entry-date");
  if (!dateInput.value) {
    dateInput.value = new Date().toISOString().slice(0, 10);
  }
}

$("entry-form").addEventListener("submit", onSubmit);
initDateInput();
