/* ── State ──────────────────────────────────────────────── */
const state = {
  activeTopicId: null,
  activeCourseId: null,
};

const quizState = {
  category: 'all',   // 'all' | 'topic' | 'course'
  filterId: null,
  types: new Set(['true_false', 'multiple_choice', 'short_answer']),
  status: 'due',     // 'due' | 'new' | 'all'
};

/* ── API helpers ─────────────────────────────────────────── */
async function api(method, path, body) {
  const opts = {
    method,
    headers: { "Content-Type": "application/json" },
  };
  if (body !== undefined) opts.body = JSON.stringify(body);
  const res = await fetch("/api" + path, opts);
  if (res.status === 204) return null;
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "Request failed");
  return data;
}

/* ── Render helpers ──────────────────────────────────────── */
function updateHeader() {
  const bc = document.getElementById("breadcrumb");
  const fc = document.getElementById("fact-count");

  const topicName = state.activeTopicId
    ? document.querySelector(`[data-topic-id="${state.activeTopicId}"] .list-item-name`)?.textContent
    : null;
  const courseName = state.activeCourseId
    ? document.querySelector(`[data-course-id="${state.activeCourseId}"] .list-item-name`)?.textContent
    : null;

  if (topicName && courseName) {
    bc.textContent = `${topicName} › ${courseName}`;
  } else if (topicName) {
    bc.textContent = topicName;
  } else {
    bc.textContent = "";
  }

  const factCards = document.querySelectorAll(".fact-card").length;
  fc.textContent = factCards ? `${factCards} fact${factCards !== 1 ? "s" : ""}` : "";
}

/* ── Topics panel (primary) ──────────────────────────────── */
async function renderTopics() {
  const topics = await api("GET", "/topics");
  const list = document.getElementById("topic-list");
  list.innerHTML = "";

  if (!topics.length) {
    list.innerHTML = '<div class="empty-state">No topics yet</div>';
    updateHeader();
    return;
  }

  for (const t of topics) {
    const item = document.createElement("div");
    item.className = "list-item" + (t.id === state.activeTopicId ? " active" : "");
    item.dataset.topicId = t.id;
    item.innerHTML = `
      <span class="list-item-name">${escHtml(t.name)}</span>
      <span class="list-item-badge">${t.fact_count}</span>
      <button class="btn-delete-item" title="Delete topic" data-id="${t.id}">✕</button>
    `;
    item.addEventListener("click", (e) => {
      if (e.target.closest(".btn-delete-item")) return;
      selectTopic(t.id);
    });
    item.querySelector(".btn-delete-item").addEventListener("click", (e) => {
      e.stopPropagation();
      confirmDelete(e.currentTarget, () => deleteTopic(t.id));
    });
    list.appendChild(item);
  }
  updateHeader();
}

async function addTopic() {
  const input = document.getElementById("new-topic-name");
  const name = input.value.trim();
  if (!name) return;
  try {
    await api("POST", "/topics", { name });
    input.value = "";
    await renderTopics();
  } catch (err) {
    alert(err.message);
  }
}

async function deleteTopic(id) {
  await api("DELETE", `/topics/${id}`);
  if (state.activeTopicId === id) {
    state.activeTopicId = null;
    renderFacts([]);
    enableFactInput(false);
  }
  await renderTopics();
}

async function selectTopic(id) {
  viewingFlaggedFacts = false;
  document.getElementById("flagged-facts-item").classList.remove("active");
  state.activeTopicId = id;
  await renderTopics();
  const facts = await api("GET", `/topics/${id}/facts`);
  renderFacts(facts);
  enableFactInput(true);
  updateHeader();
}

/* ── Courses panel (secondary, toggle) ───────────────────── */
async function renderCourses() {
  const courses = await api("GET", "/courses");
  const list = document.getElementById("course-list");
  list.innerHTML = "";

  if (!courses.length) {
    list.innerHTML = '<div class="empty-state">No courses yet</div>';
    updateHeader();
    return;
  }

  for (const c of courses) {
    const item = document.createElement("div");
    item.className = "list-item" + (c.id === state.activeCourseId ? " active" : "");
    item.dataset.courseId = c.id;
    item.innerHTML = `
      <span class="list-item-name">${escHtml(c.name)}</span>
      <button class="btn-delete-item" title="Delete course" data-id="${c.id}">✕</button>
    `;
    item.addEventListener("click", (e) => {
      if (e.target.closest(".btn-delete-item")) return;
      selectCourse(c.id);
    });
    item.querySelector(".btn-delete-item").addEventListener("click", (e) => {
      e.stopPropagation();
      confirmDelete(e.currentTarget, () => deleteCourse(c.id));
    });
    list.appendChild(item);
  }
  updateHeader();
}

async function addCourse() {
  const input = document.getElementById("new-course-name");
  const name = input.value.trim();
  if (!name) return;
  try {
    await api("POST", "/courses", { name });
    input.value = "";
    await renderCourses();
  } catch (err) {
    alert(err.message);
  }
}

async function deleteCourse(id) {
  await api("DELETE", `/courses/${id}`);
  if (state.activeCourseId === id) {
    state.activeCourseId = null;
  }
  await renderCourses();
  // Refresh facts to drop course badges for the deleted course
  if (state.activeTopicId) {
    const facts = await api("GET", `/topics/${state.activeTopicId}/facts`);
    renderFacts(facts);
  }
}

function selectCourse(id) {
  // Toggle: clicking the active course deselects it
  state.activeCourseId = (state.activeCourseId === id) ? null : id;
  renderCourses();
}

/* ── Facts panel ─────────────────────────────────────────── */
function renderFacts(facts) {
  const list = document.getElementById("facts-list");
  list.innerHTML = "";

  if (!facts.length) {
    list.innerHTML = '<div class="empty-state">No facts yet — add one above</div>';
    updateHeader();
    return;
  }

  for (const f of facts) {
    list.appendChild(buildFactCard(f));
  }
  updateHeader();
}

function buildFactCard(fact) {
  const card = document.createElement("div");
  card.className = "fact-card";
  card.dataset.factId = fact.id;

  const badgeHtml = fact.course_name
    ? `<span class="course-badge">${escHtml(fact.course_name)}</span>`
    : "";

  const flagHtml = fact.accuracy_flag
    ? `<div class="fact-flag-warning"><span class="fact-flag-icon">⚠</span><span>${escHtml(fact.accuracy_flag)}</span></div>`
    : "";

  if (fact.accuracy_flag) card.classList.add("fact-flagged");

  card.innerHTML = `
    <div class="fact-card-content">${escHtml(fact.content)}</div>
    ${badgeHtml}
    ${flagHtml}
    <div class="fact-card-actions">
      ${fact.accuracy_flag ? '<button class="btn-dismiss-flag">Dismiss</button>' : ""}
      <button class="btn-edit">Edit</button>
      <button class="btn-delete-fact">Delete</button>
    </div>
  `;

  if (fact.accuracy_flag) {
    card.querySelector(".btn-dismiss-flag").addEventListener("click", async () => {
      await api("POST", `/facts/${fact.id}/dismiss-flag`);
      fact.accuracy_flag = null;
      const newCard = buildFactCard(fact);
      card.replaceWith(newCard);
      await refreshFlaggedItem();
    });
  }

  card.querySelector(".btn-edit").addEventListener("click", () => startEditFact(card, fact));
  card.querySelector(".btn-delete-fact").addEventListener("click", (e) => {
    confirmDelete(e.currentTarget, () => deleteFact(fact.id));
  });

  return card;
}

function startEditFact(card, fact) {
  const content = card.querySelector(".fact-card-content");
  const actions = card.querySelector(".fact-card-actions");

  // Swap content div for textarea
  const editDiv = document.createElement("div");
  editDiv.className = "fact-card-edit";
  const ta = document.createElement("textarea");
  ta.value = fact.content;
  editDiv.appendChild(ta);
  content.replaceWith(editDiv);

  // Swap action buttons
  actions.innerHTML = `
    <button class="btn-cancel-edit">Cancel</button>
    <button class="btn-save-edit">Save</button>
  `;
  actions.querySelector(".btn-cancel-edit").addEventListener("click", () => {
    editDiv.replaceWith(content);
    actions.innerHTML = `
      <button class="btn-edit">Edit</button>
      <button class="btn-delete-fact">Delete</button>
    `;
    actions.querySelector(".btn-edit").addEventListener("click", () => startEditFact(card, fact));
    actions.querySelector(".btn-delete-fact").addEventListener("click", (e) => {
      confirmDelete(e.currentTarget, () => deleteFact(fact.id));
    });
  });
  actions.querySelector(".btn-save-edit").addEventListener("click", async () => {
    const newContent = ta.value.trim();
    if (!newContent) { alert("Fact cannot be empty"); return; }
    try {
      const updated = await api("PUT", `/facts/${fact.id}`, { content: newContent, course_id: fact.course_id });
      const newCard = buildFactCard(updated);
      card.replaceWith(newCard);
      updateHeader();
    } catch (err) {
      alert(err.message);
    }
  });

  ta.focus();
  ta.setSelectionRange(ta.value.length, ta.value.length);
}

async function addFact() {
  if (!state.activeTopicId) return;
  const ta = document.getElementById("new-fact-content");
  const content = ta.value.trim();
  if (!content) return;
  try {
    await api("POST", `/topics/${state.activeTopicId}/facts`, { content, course_id: state.activeCourseId });
    ta.value = "";
    const facts = await api("GET", `/topics/${state.activeTopicId}/facts`);
    renderFacts(facts);
    // Refresh topic badge count
    await renderTopics();
  } catch (err) {
    alert(err.message);
  }
}

async function deleteFact(id) {
  await api("DELETE", `/facts/${id}`);
  const facts = await api("GET", `/topics/${state.activeTopicId}/facts`);
  renderFacts(facts);
  await renderTopics();
}

function enableFactInput(enabled) {
  const ta = document.getElementById("new-fact-content");
  const btn = document.getElementById("add-fact-btn");
  ta.disabled = !enabled;
  btn.disabled = !enabled;
}

/* ── Two-click confirm delete ────────────────────────────── */
function confirmDelete(btn, action) {
  if (btn.dataset.confirming === "1") {
    action();
  } else {
    btn.dataset.confirming = "1";
    const orig = btn.textContent;
    btn.classList.add("confirm");
    btn.textContent = "Confirm?";
    setTimeout(() => {
      btn.dataset.confirming = "";
      btn.classList.remove("confirm");
      btn.textContent = orig;
    }, 2500);
  }
}

/* ── Utility ─────────────────────────────────────────────── */
function escHtml(str) {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/* ── Questions mode ──────────────────────────────────────── */
let questionsActiveTopic = null;  // {id, name} | null for "all"

function enterQuestionsMode() {
  document.querySelector("main").classList.add("hidden");
  document.getElementById("breadcrumb").classList.add("hidden");
  document.getElementById("fact-count").classList.add("hidden");
  document.getElementById("quiz-panel").classList.add("hidden");
  document.getElementById("questions-panel").classList.remove("hidden");
  document.getElementById("btn-questions").classList.add("active");
  document.getElementById("btn-study").classList.remove("active");
  document.getElementById("btn-quiz").classList.remove("active");
  showQuestionsTab();
}

function showQuestionsTab() {
  document.getElementById("questions-view").classList.remove("hidden");
  document.getElementById("flagged-view").classList.add("hidden");
  document.getElementById("qtab-questions").classList.add("active");
  document.getElementById("qtab-flagged").classList.remove("active");
  renderQuestionsSidebar();
}

function showFlaggedTab() {
  document.getElementById("questions-view").classList.add("hidden");
  document.getElementById("flagged-view").classList.remove("hidden");
  document.getElementById("qtab-flagged").classList.add("active");
  document.getElementById("qtab-questions").classList.remove("active");
  loadFlaggedQuestions();
}

async function loadFlaggedQuestions() {
  const content = document.getElementById("flagged-content");
  content.innerHTML = '<div class="quiz-placeholder">Loading…</div>';

  const flags = await api("GET", "/questions/flags");

  // Update count badge
  const pending = flags.filter(f => f.verdict === "pending").length;
  const badge = document.getElementById("flagged-count");
  if (pending > 0) {
    badge.textContent = pending;
    badge.classList.remove("hidden");
  } else {
    badge.classList.add("hidden");
  }

  content.innerHTML = "";

  if (!flags.length) {
    content.innerHTML = '<div class="quiz-placeholder">No flagged questions.</div>';
    return;
  }

  for (const flag of flags) {
    content.appendChild(buildFlagCard(flag));
  }
}

function buildFlagCard(flag) {
  const card = document.createElement("div");
  card.className = "flag-review-card";
  card.dataset.flagId = flag.id;

  const verdictLabel = { pending: "Under Review", dismissed: "AI: Valid", confirmed: "AI: Removed" };
  const verdictClass = flag.verdict;

  const isMC = flag.type === "multiple_choice";
  const isSA = flag.type === "short_answer";
  let questionHtml = "";
  if (isMC) {
    const letters = "ABCD";
    const optsHtml = (flag.options || []).map((opt, i) =>
      `<div class="flag-mc-opt${opt.is_correct ? " correct" : ""}">${letters[i]}. ${escHtml(opt.option_text)}${opt.is_correct ? " ✓" : ""}</div>`
    ).join("");
    questionHtml = `
      <div class="flag-review-top">
        <span class="question-badge mc">MC</span>
        <span class="question-statement">${escHtml(flag.statement)}</span>
        <span class="flag-verdict-badge ${verdictClass}">${verdictLabel[flag.verdict] || flag.verdict}</span>
      </div>
      <div class="flag-mc-options">${optsHtml}</div>
    `;
  } else if (isSA) {
    questionHtml = `
      <div class="flag-review-top">
        <span class="question-badge sa">SA</span>
        <span class="question-statement">${escHtml(flag.statement)}</span>
        <span class="flag-verdict-badge ${verdictClass}">${verdictLabel[flag.verdict] || flag.verdict}</span>
      </div>
    `;
  } else {
    const tf = Boolean(flag.is_true);
    questionHtml = `
      <div class="flag-review-top">
        <span class="question-badge ${tf ? 'true' : 'false'}">${tf ? "True" : "False"}</span>
        <span class="question-statement">${escHtml(flag.statement)}</span>
        <span class="flag-verdict-badge ${verdictClass}">${verdictLabel[flag.verdict] || flag.verdict}</span>
      </div>
    `;
  }

  const reasonHtml = `
    <div class="flag-reason-row">
      🚩 <strong>${escHtml(flag.reason_label)}</strong>
      ${flag.reason_text ? `— ${escHtml(flag.reason_text)}` : ""}
    </div>
  `;

  const aiHtml = flag.verdict_explanation
    ? `<div class="flag-ai-explanation"><strong>AI Review:</strong> ${escHtml(flag.verdict_explanation)}</div>`
    : (flag.verdict === "pending" ? `<div class="flag-ai-explanation">AI review in progress…</div>` : "");

  const sourceHtml = `
    <div class="flag-source-fact">
      <div class="fact-topic">Source fact · ${escHtml(flag.topic_name)}</div>
      ${escHtml(flag.fact_content)}
    </div>
  `;

  card.innerHTML = questionHtml + reasonHtml + aiHtml + sourceHtml + `<div class="flag-override-row"></div>`;

  const overrideRow = card.querySelector(".flag-override-row");

  if (flag.verdict !== "confirmed") {
    const keepBtn = document.createElement("button");
    keepBtn.className = "btn-override-keep";
    keepBtn.textContent = flag.verdict === "dismissed" ? "Keep (confirm AI)" : "Keep Question";
    keepBtn.addEventListener("click", async () => {
      await api("POST", `/questions/flags/${flag.id}/override`, { action: "keep" });
      card.remove();
      updateFlaggedCount();
    });
    overrideRow.appendChild(keepBtn);
  }

  const removeBtn = document.createElement("button");
  removeBtn.className = "btn-override-remove";
  removeBtn.textContent = "Remove Question";
  removeBtn.addEventListener("click", async () => {
    await api("POST", `/questions/flags/${flag.id}/override`, { action: "remove" });
    card.remove();
    updateFlaggedCount();
  });
  overrideRow.appendChild(removeBtn);

  return card;
}

function updateFlaggedCount() {
  const remaining = document.querySelectorAll(".flag-review-card").length;
  const badge = document.getElementById("flagged-count");
  if (remaining > 0) {
    badge.textContent = remaining;
    badge.classList.remove("hidden");
  } else {
    badge.classList.add("hidden");
    document.getElementById("flagged-content").innerHTML =
      '<div class="quiz-placeholder">No flagged questions.</div>';
  }
}

async function renderQuestionsSidebar() {
  const list = document.getElementById("questions-topic-list");
  list.innerHTML = "";

  const allItem = document.createElement("div");
  allItem.className = "list-item" + (questionsActiveTopic === null ? " active" : "");
  allItem.innerHTML = '<span class="list-item-name">All Topics</span>';
  allItem.addEventListener("click", () => {
    questionsActiveTopic = null;
    renderQuestionsSidebar();
    loadQuestions();
  });
  list.appendChild(allItem);

  const topics = await api("GET", "/topics");
  for (const t of topics) {
    const item = document.createElement("div");
    item.className = "list-item" + (questionsActiveTopic?.id === t.id ? " active" : "");
    item.innerHTML = `<span class="list-item-name">${escHtml(t.name)}</span>`;
    item.addEventListener("click", () => {
      questionsActiveTopic = t;
      renderQuestionsSidebar();
      loadQuestions();
    });
    list.appendChild(item);
  }

  loadQuestions();
}

function dueBadgeText(q) {
  if (!q.next_due_at) return "Live";
  const due = new Date(q.next_due_at + "Z");
  const diffMs = due - Date.now();
  if (diffMs <= 0) return "Live";
  const days = Math.ceil(diffMs / 86400000);
  if (days === 1) return "1d";
  if (days < 30) return `${days}d`;
  if (days < 365) return `${Math.round(days / 30)}mo`;
  return `${Math.round(days / 365)}yr`;
}

function dueBadgeClass(q) {
  if (!q.next_due_at) return "due-now";
  const due = new Date(q.next_due_at + "Z");
  return due <= new Date() ? "due-now" : "due-later";
}

async function loadQuestions() {
  const content = document.getElementById("questions-content");
  content.innerHTML = '<div class="quiz-placeholder">Loading…</div>';

  const params = questionsActiveTopic ? `?topic_id=${questionsActiveTopic.id}` : "";
  const questions = await api("GET", `/questions${params}`);

  content.innerHTML = "";
  content.className = "questions-content";

  if (!questions.length) {
    content.innerHTML = '<div class="quiz-placeholder">No questions yet — add facts to generate them.</div>';
    return;
  }

  // Group by fact
  const byFact = new Map();
  for (const q of questions) {
    if (!byFact.has(q.fact_id)) byFact.set(q.fact_id, { content: q.fact_content, items: [] });
    byFact.get(q.fact_id).items.push(q);
  }

  for (const [, group] of byFact) {
    const label = document.createElement("div");
    label.className = "question-group-label";
    label.textContent = `Fact: ${group.content.length > 80 ? group.content.slice(0, 80) + "…" : group.content}`;
    content.appendChild(label);

    for (const q of group.items) {
      const card = document.createElement("div");
      const isMC = q.type === "multiple_choice";
      card.className = "question-card" + (isMC ? " mc-card" : "");

      if (isMC) {
        const letters = "ABCD";
        const optHtml = (q.options || []).map((opt, i) =>
          `<div class="mc-option-item${opt.is_correct ? " mc-correct-opt" : ""}">${letters[i]}. ${escHtml(opt.option_text)}${opt.is_correct ? " ✓" : ""}</div>`
        ).join("");
        card.innerHTML = `
          <div class="question-card-top">
            <span class="question-badge mc">MC</span>
            <span class="question-statement">${escHtml(q.statement)}</span>
            <span class="question-progress-badge ${dueBadgeClass(q)}">${dueBadgeText(q)}</span>
          </div>
          <div class="mc-option-list">${optHtml}</div>
        `;
      } else if (q.type === "short_answer") {
        card.innerHTML = `
          <span class="question-badge sa">SA</span>
          <span class="question-statement">${escHtml(q.statement)}</span>
          <span class="question-progress-badge ${dueBadgeClass(q)}">${dueBadgeText(q)}</span>
        `;
      } else {
        card.innerHTML = `
          <span class="question-badge ${q.is_true ? 'true' : 'false'}">${q.is_true ? "True" : "False"}</span>
          <span class="question-statement">${escHtml(q.statement)}</span>
          <span class="question-progress-badge ${dueBadgeClass(q)}">${dueBadgeText(q)}</span>
        `;
      }
      content.appendChild(card);
    }
  }
}

/* ── Quiz game state ─────────────────────────────────────── */
let quizQuestions = [];   // [{displayContent, isTrue}, ...]
let quizIndex = 0;
let quizScore = 0;

/* ── Quiz mode ───────────────────────────────────────────── */
function enterQuizMode() {
  document.querySelector("main").classList.add("hidden");
  document.getElementById("breadcrumb").classList.add("hidden");
  document.getElementById("fact-count").classList.add("hidden");
  document.getElementById("questions-panel").classList.add("hidden");
  document.getElementById("quiz-panel").classList.remove("hidden");
  document.getElementById("btn-quiz").classList.add("active");
  document.getElementById("btn-study").classList.remove("active");
  document.getElementById("btn-questions").classList.remove("active");
  populateQuizFilterSelect();
}

function enterStudyMode() {
  document.querySelector("main").classList.remove("hidden");
  document.getElementById("breadcrumb").classList.remove("hidden");
  document.getElementById("fact-count").classList.remove("hidden");
  document.getElementById("quiz-panel").classList.add("hidden");
  document.getElementById("questions-panel").classList.add("hidden");
  document.getElementById("btn-study").classList.add("active");
  document.getElementById("btn-quiz").classList.remove("active");
  document.getElementById("btn-questions").classList.remove("active");
}

async function populateQuizFilterSelect() {
  const sel = document.getElementById("quiz-filter-select");
  if (quizState.category === 'all') {
    sel.classList.add("hidden");
    return;
  }

  const endpoint = quizState.category === 'topic' ? '/topics' : '/courses';
  const items = await api("GET", endpoint);

  sel.innerHTML = '<option value="">— select —</option>';
  for (const item of items) {
    const opt = document.createElement("option");
    opt.value = item.id;
    opt.textContent = item.name;
    sel.appendChild(opt);
  }

  quizState.filterId = null;
  sel.value = "";
  sel.classList.remove("hidden");
}

function selectQuizCategory(value) {
  quizState.category = value;
  document.querySelectorAll("#quiz-cat-ctrl .seg-btn").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.value === value);
  });
  populateQuizFilterSelect();
}

function toggleQuizType(value) {
  if (quizState.types.has(value)) {
    if (quizState.types.size === 1) return; // keep at least one selected
    quizState.types.delete(value);
  } else {
    quizState.types.add(value);
  }
  document.querySelectorAll("#quiz-type-ctrl .seg-btn").forEach(btn => {
    btn.classList.toggle("active", quizState.types.has(btn.dataset.value));
  });
}

function selectQuizStatus(value) {
  quizState.status = value;
  document.querySelectorAll("#quiz-status-ctrl .seg-btn").forEach(btn => {
    btn.classList.remove("active");
    if (btn.dataset.value === value) btn.classList.add("active");
  });
}

async function startQuiz() {
  const content = document.getElementById("quiz-content");
  content.innerHTML = '<div class="quiz-placeholder">Loading…</div>';

  const params = new URLSearchParams();
  if (quizState.category === 'topic' && quizState.filterId) {
    params.set('topic_id', quizState.filterId);
  } else if (quizState.category === 'course' && quizState.filterId) {
    params.set('course_id', quizState.filterId);
  }

  params.set('status', quizState.status);
  params.set('types', [...quizState.types].join(','));

  let questions;
  try {
    questions = await api("GET", `/questions?${params}`);
  } catch (err) {
    content.innerHTML = `<div class="quiz-placeholder">Error: ${escHtml(err.message)}</div>`;
    return;
  }

  if (!questions.length) {
    content.innerHTML = '<div class="quiz-placeholder">No questions due right now — check back later!</div>';
    return;
  }

  quizQuestions = [...questions].sort(() => Math.random() - 0.5);
  quizIndex = 0;
  quizScore = 0;
  document.getElementById("quiz-panel").classList.add("quiz-running");
  showQuestion();
}

function showQuestion() {
  const content = document.getElementById("quiz-content");
  const total = quizQuestions.length;

  if (quizIndex >= total) {
    showQuizResults();
    return;
  }

  const q = quizQuestions[quizIndex];
  const pct = (quizIndex / total * 100).toFixed(1);
  const progressHeader = `
    <div>
      <div class="quiz-progress">
        <button class="btn-quiz-back" title="Back to settings">← Settings</button>
        Question ${quizIndex + 1} of ${total}
        <button class="btn-flag" title="Flag this question">⚑ Flag</button>
      </div>
      <div class="quiz-progress-bar"><div class="quiz-progress-fill" style="width:${pct}%"></div></div>
    </div>`;

  const card = document.createElement("div");
  card.className = "quiz-card";

  if (q.type === "multiple_choice") {
    const shuffled = [...q.options].sort(() => Math.random() - 0.5);
    const letters = "ABCD";
    const optHtml = shuffled.map((opt, i) =>
      `<button class="btn-mc-option quiz-answer-area" data-correct="${Boolean(opt.is_correct)}">${letters[i]}. ${escHtml(opt.option_text)}</button>`
    ).join("");
    card.innerHTML = `
      ${progressHeader}
      <div class="quiz-statement">${escHtml(q.statement)}</div>
      <div class="mc-options quiz-answer-area">${optHtml}</div>
    `;
    card.querySelectorAll(".btn-mc-option").forEach(btn => {
      btn.addEventListener("click", () => answerMC(btn, card, q));
    });
  } else if (q.type === "short_answer") {
    card.innerHTML = `
      ${progressHeader}
      <div class="quiz-statement">${escHtml(q.statement)}</div>
      <div class="quiz-answer-row quiz-sa-area" style="flex-direction:column;gap:10px">
        <textarea class="sa-answer-input" placeholder="Type your answer here…" rows="4"></textarea>
        <button class="btn-sa-submit" disabled>Submit Answer</button>
      </div>
    `;
    const ta = card.querySelector(".sa-answer-input");
    const submitBtn = card.querySelector(".btn-sa-submit");
    ta.addEventListener("input", () => { submitBtn.disabled = ta.value.trim().length === 0; });
    submitBtn.addEventListener("click", () => answerSA(card, q));
  } else {
    const isTrue = Boolean(q.is_true);
    card.innerHTML = `
      ${progressHeader}
      <div class="quiz-statement">${escHtml(q.statement)}</div>
      <div class="quiz-answer-row quiz-answer-area">
        <button class="btn-tf btn-tf-true" data-answer="true">True</button>
        <button class="btn-tf btn-tf-false" data-answer="false">False</button>
      </div>
    `;
    card.querySelectorAll(".btn-tf").forEach(btn => {
      btn.addEventListener("click", () => answerQuestion(btn.dataset.answer === "true", isTrue, q.id));
    });
  }

  card.querySelector(".btn-flag").addEventListener("click", () => showFlagForm(card, q.id));
  card.querySelector(".btn-quiz-back").addEventListener("click", exitQuiz);
  content.innerHTML = "";
  content.appendChild(card);
}

async function answerMC(selectedBtn, card, q) {
  const correct = selectedBtn.dataset.correct === "true";
  if (correct) quizScore++;

  card.querySelectorAll(".btn-mc-option").forEach(btn => {
    btn.disabled = true;
    if (btn.dataset.correct === "true") btn.classList.add("mc-correct");
    else if (btn === selectedBtn)       btn.classList.add("mc-wrong");
  });

  if (correct) {
    try { await api("POST", `/questions/${q.id}/answer`, { correct: true }); } catch (_) {}
  }

  const feedback = document.createElement("div");
  feedback.className = "quiz-feedback " + (correct ? "correct" : "wrong");
  feedback.textContent = correct ? "Correct!" : "Wrong.";
  card.querySelector(".mc-options").insertAdjacentElement("afterend", feedback);

  const nextBtn = document.createElement("button");
  nextBtn.className = "btn-quiz-next";
  nextBtn.textContent = quizIndex + 1 < quizQuestions.length ? "Next →" : "See Results";
  nextBtn.addEventListener("click", () => { quizIndex++; showQuestion(); });
  card.appendChild(nextBtn);
}

async function answerQuestion(userSaysTrue, isTrue, questionId) {
  const correct = userSaysTrue === isTrue;
  if (correct) quizScore++;

  const card = document.querySelector(".quiz-card");

  card.querySelectorAll(".btn-tf").forEach(btn => {
    btn.disabled = true;
    if ((btn.dataset.answer === "true") === isTrue) {
      btn.style.outline = "3px solid #48bb78";
    }
  });

  const feedback = document.createElement("div");
  feedback.className = "quiz-feedback " + (correct ? "correct" : "wrong");

  if (correct) {
    try { await api("POST", `/questions/${questionId}/answer`, { correct: true }); } catch (_) {}
  }

  feedback.textContent = correct
    ? `Correct! This statement is ${isTrue ? "TRUE" : "FALSE"}.`
    : `Wrong. This statement is ${isTrue ? "TRUE" : "FALSE"}.`;
  card.querySelector(".quiz-answer-row").insertAdjacentElement("afterend", feedback);

  const nextBtn = document.createElement("button");
  nextBtn.className = "btn-quiz-next";
  nextBtn.textContent = quizIndex + 1 < quizQuestions.length ? "Next →" : "See Results";
  nextBtn.addEventListener("click", () => { quizIndex++; showQuestion(); });
  card.appendChild(nextBtn);
}


async function answerSA(card, q) {
  const ta = card.querySelector(".sa-answer-input");
  const submitBtn = card.querySelector(".btn-sa-submit");
  const answer = ta.value.trim();

  ta.disabled = true;
  submitBtn.disabled = true;
  submitBtn.textContent = "Grading…";

  let result;
  try {
    result = await api("POST", `/questions/${q.id}/grade`, { answer });
  } catch (err) {
    submitBtn.textContent = "Submit Answer";
    submitBtn.disabled = false;
    ta.disabled = false;
    return;
  }

  if (result.correct) quizScore++;

  const feedback = document.createElement("div");
  feedback.className = "quiz-feedback " + (result.correct ? "correct" : "wrong");
  feedback.textContent = result.feedback;
  submitBtn.replaceWith(feedback);

  const nextBtn = document.createElement("button");
  nextBtn.className = "btn-quiz-next";
  nextBtn.textContent = quizIndex + 1 < quizQuestions.length ? "Next →" : "See Results";
  nextBtn.addEventListener("click", () => { quizIndex++; showQuestion(); });
  card.appendChild(nextBtn);
}

function showFlagForm(card, questionId) {
  // Hide answer area, show flag form inline
  const answerArea = card.querySelector(".quiz-answer-row, .mc-options");
  if (answerArea) answerArea.classList.add("hidden");

  const form = document.createElement("div");
  form.className = "flag-form";
  form.innerHTML = `
    <div class="flag-form-title">Why are you flagging this question?</div>
    <div class="flag-options">
      <label class="flag-option"><input type="radio" name="flag-reason" value="wrong_answer" /> Wrong answer</label>
      <label class="flag-option"><input type="radio" name="flag-reason" value="not_related" /> Not covered</label>
      <label class="flag-option"><input type="radio" name="flag-reason" value="no_sense" /> Doesn't make sense</label>
      <label class="flag-option"><input type="radio" name="flag-reason" value="other" /> Other</label>
    </div>
    <input type="text" class="flag-other-input hidden" placeholder="Describe the issue…" maxlength="300" />
    <div class="flag-form-actions">
      <button class="btn-flag-cancel">Cancel</button>
      <button class="btn-flag-submit">Submit Flag</button>
    </div>
  `;

  // Show text field only when "Other" is selected
  const radios = form.querySelectorAll("input[name='flag-reason']");
  const otherInput = form.querySelector(".flag-other-input");
  radios.forEach(r => r.addEventListener("change", () => {
    otherInput.classList.toggle("hidden", r.value !== "other" || !r.checked);
    if (r.value === "other" && r.checked) otherInput.focus();
  }));

  form.querySelector(".btn-flag-cancel").addEventListener("click", () => {
    form.remove();
    if (answerArea) answerArea.classList.remove("hidden");
  });

  form.querySelector(".btn-flag-submit").addEventListener("click", async () => {
    const selected = form.querySelector("input[name='flag-reason']:checked");
    if (!selected) { otherInput.placeholder = "Please select a reason first."; return; }
    const reasonType = selected.value;
    const reasonText = reasonType === "other" ? otherInput.value.trim() : null;

    form.querySelector(".btn-flag-submit").disabled = true;
    try {
      await api("POST", `/questions/${questionId}/flag`, { reason_type: reasonType, reason_text: reasonText });
    } catch (e) { /* best-effort */ }

    form.innerHTML = '<div class="flag-confirmed">Flagged — we\'ll review and replace this question if needed.</div>';
    setTimeout(() => { quizIndex++; showQuestion(); }, 1800);
  });

  card.querySelector(".quiz-statement").insertAdjacentElement("afterend", form);
}

function exitQuiz() {
  document.getElementById("quiz-panel").classList.remove("quiz-running");
  document.getElementById("quiz-content").innerHTML =
    '<div class="quiz-placeholder">Configure settings and press Start Quiz.</div>';
}

function showQuizResults() {
  const content = document.getElementById("quiz-content");
  const total = quizQuestions.length;
  const pct = Math.round(quizScore / total * 100);

  const card = document.createElement("div");
  card.className = "quiz-card quiz-results";
  card.innerHTML = `
    <div class="quiz-results-title">Quiz Complete!</div>
    <div class="quiz-results-score">${quizScore} / ${total}</div>
    <div class="quiz-results-label">${pct}% correct</div>
    <div style="display:flex;gap:10px;justify-content:center">
      <button class="btn-quiz-back">← Settings</button>
      <button class="btn-quiz-restart">Try Again</button>
    </div>
  `;
  card.querySelector(".btn-quiz-restart").addEventListener("click", startQuiz);
  card.querySelector(".btn-quiz-back").addEventListener("click", exitQuiz);

  content.innerHTML = "";
  content.appendChild(card);
}

/* ── Flagged facts ───────────────────────────────────────── */
let viewingFlaggedFacts = false;

async function refreshFlaggedItem() {
  const facts = await api("GET", "/facts/flagged");
  const item = document.getElementById("flagged-facts-item");
  const badge = document.getElementById("flagged-facts-count");
  if (facts.length > 0) {
    badge.textContent = facts.length;
    item.classList.remove("hidden");
  } else {
    item.classList.add("hidden");
    if (viewingFlaggedFacts) {
      viewingFlaggedFacts = false;
      item.classList.remove("active");
      renderFacts([]);
      enableFactInput(false);
    }
  }
}

async function showFlaggedFacts() {
  viewingFlaggedFacts = true;
  // Deselect any active topic
  state.activeTopicId = null;
  document.querySelectorAll("#topic-list .list-item.active").forEach(el => el.classList.remove("active"));
  document.getElementById("flagged-facts-item").classList.add("active");

  const facts = await api("GET", "/facts/flagged");
  const list = document.getElementById("facts-list");
  list.innerHTML = "";
  enableFactInput(false);

  if (!facts.length) {
    list.innerHTML = '<div class="empty-state">No flagged facts</div>';
    return;
  }

  for (const f of facts) {
    list.appendChild(buildFlaggedFactCard(f));
  }

  const fc = document.getElementById("fact-count");
  fc.textContent = "";
  document.getElementById("breadcrumb").textContent = "Flagged Facts";
}

function buildFlaggedFactCard(fact) {
  const card = document.createElement("div");
  card.className = "fact-card fact-flagged";
  card.dataset.factId = fact.id;

  card.innerHTML = `
    <div class="fact-flag-topic">${escHtml(fact.topic_name || "")}</div>
    <div class="fact-card-content">${escHtml(fact.content)}</div>
    <div class="fact-flag-warning">
      <span class="fact-flag-icon">⚠</span>
      <span>${escHtml(fact.accuracy_flag)}</span>
    </div>
    <div class="fact-card-actions">
      <button class="btn-dismiss-flag">Dismiss</button>
      <button class="btn-delete-fact">Delete</button>
    </div>
  `;

  card.querySelector(".btn-dismiss-flag").addEventListener("click", async () => {
    await api("POST", `/facts/${fact.id}/dismiss-flag`);
    card.remove();
    await refreshFlaggedItem();
    if (!document.querySelector(".fact-card")) {
      document.getElementById("facts-list").innerHTML =
        '<div class="empty-state">No flagged facts</div>';
    }
  });

  card.querySelector(".btn-delete-fact").addEventListener("click", e => {
    confirmDelete(e.currentTarget, async () => {
      await api("DELETE", `/facts/${fact.id}`);
      card.remove();
      await refreshFlaggedItem();
      await renderTopics();
      if (!document.querySelector(".fact-card")) {
        document.getElementById("facts-list").innerHTML =
          '<div class="empty-state">No flagged facts</div>';
      }
    });
  });

  return card;
}

/* ── PDF Import Modal ────────────────────────────────────── */
const importState = {
  depth: 'easy',
  selectedFile: null,
};

function openImportModal() {
  const modal = document.getElementById('import-modal');
  modal.classList.remove('hidden');
  populateImportDropdowns();
}

function closeImportModal() {
  document.getElementById('import-modal').classList.add('hidden');
  document.getElementById('extract-results').classList.add('hidden');
  document.getElementById('extracted-facts-list').innerHTML = '';
  document.getElementById('pdf-file-input').value = '';
  document.getElementById('pdf-filename').textContent = 'No file selected';
  document.getElementById('extract-btn').disabled = true;
  document.getElementById('import-btn').disabled = true;
  importState.selectedFile = null;
}

async function populateImportDropdowns() {
  const topicSel = document.getElementById('import-topic-select');
  const courseSel = document.getElementById('import-course-select');

  const [topics, courses] = await Promise.all([
    api('GET', '/topics'),
    api('GET', '/courses'),
  ]);

  topicSel.innerHTML = '<option value="">— select course —</option>';
  for (const t of topics) {
    const opt = document.createElement('option');
    opt.value = t.id;
    opt.textContent = t.name;
    // Pre-select the currently active topic if any
    if (t.id === state.activeTopicId) opt.selected = true;
    topicSel.appendChild(opt);
  }

  courseSel.innerHTML = '<option value="">None</option>';
  for (const c of courses) {
    const opt = document.createElement('option');
    opt.value = c.id;
    opt.textContent = c.name;
    if (c.id === state.activeCourseId) opt.selected = true;
    courseSel.appendChild(opt);
  }

  updateExtractBtn();
}

function updateExtractBtn() {
  const hasFile = !!importState.selectedFile;
  const hasTopic = !!document.getElementById('import-topic-select').value;
  document.getElementById('extract-btn').disabled = !(hasFile && hasTopic);
}

async function runExtraction() {
  const startPage = parseInt(document.getElementById('start-page-input').value) || 1;
  const endPage = parseInt(document.getElementById('end-page-input').value) || 20;
  const pageRange = endPage - startPage + 1;

  if (pageRange > 100) {
    alert('The selected page range is more than 100 pages. Please upload a smaller file or narrow your page range.');
    return;
  }
  if (pageRange > 25) {
    if (!confirm(`The selected page range is ${pageRange} pages, which may take a moment and use more API credits. Continue?`)) {
      return;
    }
  }

  const btn = document.getElementById('extract-btn');
  const resultsDiv = document.getElementById('extract-results');

  btn.disabled = true;
  btn.textContent = 'Extracting…';

  const formData = new FormData();
  formData.append('file', importState.selectedFile);
  formData.append('max_facts', document.querySelector('#max-facts-ctrl .seg-btn.active').dataset.value);
  formData.append('focus', document.getElementById('focus-select').value);
  formData.append('depth', importState.depth);
  formData.append('start_page', document.getElementById('start-page-input').value || 1);
  formData.append('end_page', document.getElementById('end-page-input').value || 20);
  formData.append('avoid_duplicates', document.getElementById('avoid-dupes-check').checked ? 'true' : 'false');
  const topicId = document.getElementById('import-topic-select').value;
  if (topicId) formData.append('topic_id', topicId);

  let data;
  try {
    const res = await fetch('/api/extract/pdf', { method: 'POST', body: formData });
    data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Extraction failed');
  } catch (err) {
    alert('Error: ' + err.message);
    btn.disabled = false;
    btn.textContent = 'Extract Facts';
    return;
  }

  btn.disabled = false;
  btn.textContent = 'Extract Facts';

  const { facts, pages_processed, total_pages } = data;
  document.getElementById('results-label').textContent =
    `${facts.length} fact${facts.length !== 1 ? 's' : ''} extracted`;
  document.getElementById('results-meta').textContent =
    `${pages_processed} of ${total_pages} page${total_pages !== 1 ? 's' : ''} processed`;

  const list = document.getElementById('extracted-facts-list');
  list.innerHTML = '';
  for (const fact of facts) {
    list.appendChild(buildExtractedFactItem(fact));
  }

  updateImportBtn();
  resultsDiv.classList.remove('hidden');
}

function buildExtractedFactItem(text) {
  const item = document.createElement('div');
  item.className = 'extracted-fact-item';
  item.innerHTML = `
    <input type="checkbox" class="fact-check" checked />
    <textarea class="fact-text" rows="1">${escHtml(text)}</textarea>
  `;
  // Auto-resize textarea to fit content
  const ta = item.querySelector('.fact-text');
  ta.addEventListener('input', () => autoResize(ta));
  requestAnimationFrame(() => autoResize(ta));

  item.querySelector('.fact-check').addEventListener('change', updateImportBtn);
  return item;
}

function autoResize(ta) {
  ta.style.height = 'auto';
  ta.style.height = ta.scrollHeight + 'px';
}

function updateImportBtn() {
  const checked = document.querySelectorAll('.fact-check:checked').length;
  const btn = document.getElementById('import-btn');
  btn.disabled = checked === 0;
  btn.textContent = checked ? `Import ${checked} Fact${checked !== 1 ? 's' : ''}` : 'Import Selected';
}

async function runImport() {
  const btn = document.getElementById('import-btn');
  btn.disabled = true;
  btn.textContent = 'Importing…';

  const items = document.querySelectorAll('.extracted-fact-item');
  const facts = [];
  items.forEach(item => {
    if (item.querySelector('.fact-check').checked) {
      facts.push(item.querySelector('.fact-text').value.trim());
    }
  });

  const topicId = Number(document.getElementById('import-topic-select').value);
  const courseVal = document.getElementById('import-course-select').value;
  const courseId = courseVal ? Number(courseVal) : null;

  try {
    const result = await api('POST', '/extract/import', { topic_id: topicId, course_id: courseId, facts });
    closeImportModal();
    // Refresh facts if the imported topic is currently active
    if (topicId === state.activeTopicId) {
      const updatedFacts = await api('GET', `/topics/${topicId}/facts`);
      renderFacts(updatedFacts);
      await renderTopics();
    }
    // Brief confirmation
    const notice = document.createElement('div');
    notice.style.cssText = 'position:fixed;bottom:24px;right:24px;background:#48bb78;color:#fff;padding:10px 18px;border-radius:8px;font-size:0.85rem;font-weight:600;z-index:2000;box-shadow:0 2px 10px rgba(0,0,0,0.15)';
    notice.textContent = `${result.added} fact${result.added !== 1 ? 's' : ''} imported — questions generating in background`;
    document.body.appendChild(notice);
    setTimeout(() => notice.remove(), 4000);
  } catch (err) {
    alert('Import failed: ' + err.message);
    btn.disabled = false;
    btn.textContent = `Import ${facts.length} Facts`;
  }
}

/* ── Bootstrap ───────────────────────────────────────────── */
document.addEventListener("DOMContentLoaded", () => {
  // Topic add
  document.getElementById("add-topic-btn").addEventListener("click", addTopic);
  document.getElementById("new-topic-name").addEventListener("keydown", (e) => {
    if (e.key === "Enter") addTopic();
  });

  // Course add
  document.getElementById("add-course-btn").addEventListener("click", addCourse);
  document.getElementById("new-course-name").addEventListener("keydown", (e) => {
    if (e.key === "Enter") addCourse();
  });

  // Fact add (Ctrl+Enter or button)
  document.getElementById("add-fact-btn").addEventListener("click", addFact);
  document.getElementById("new-fact-content").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) addFact();
  });

  // Mode toggle
  document.getElementById("btn-study").addEventListener("click", enterStudyMode);
  document.getElementById("btn-questions").addEventListener("click", enterQuestionsMode);
  document.getElementById("btn-quiz").addEventListener("click", enterQuizMode);

  // Questions sub-tabs
  document.getElementById("qtab-questions").addEventListener("click", showQuestionsTab);
  document.getElementById("qtab-flagged").addEventListener("click", showFlaggedTab);

  // Quiz settings
  document.getElementById("quiz-cat-ctrl").addEventListener("click", e => {
    const btn = e.target.closest(".seg-btn");
    if (btn) selectQuizCategory(btn.dataset.value);
  });
  document.getElementById("quiz-type-ctrl").addEventListener("click", e => {
    const btn = e.target.closest(".seg-btn");
    if (btn) toggleQuizType(btn.dataset.value);
  });
  document.getElementById("quiz-status-ctrl").addEventListener("click", e => {
    const btn = e.target.closest(".seg-btn");
    if (btn) selectQuizStatus(btn.dataset.value);
  });
  document.getElementById("start-quiz-btn").addEventListener("click", startQuiz);
  document.getElementById("quiz-filter-select").addEventListener("change", e => {
    quizState.filterId = e.target.value ? Number(e.target.value) : null;
  });

  // PDF Import Modal
  document.getElementById('import-pdf-btn').addEventListener('click', openImportModal);
  document.getElementById('modal-close-btn').addEventListener('click', closeImportModal);
  document.getElementById('import-modal').addEventListener('click', e => {
    if (e.target === document.getElementById('import-modal')) closeImportModal();
  });
  document.getElementById('pdf-file-input').addEventListener('change', e => {
    importState.selectedFile = e.target.files[0] || null;
    document.getElementById('pdf-filename').textContent =
      importState.selectedFile ? importState.selectedFile.name : 'No file selected';
    updateExtractBtn();
  });
  document.getElementById('import-topic-select').addEventListener('change', updateExtractBtn);
  document.getElementById('max-facts-ctrl').addEventListener('click', e => {
    const btn = e.target.closest('.seg-btn');
    if (!btn) return;
    document.querySelectorAll('#max-facts-ctrl .seg-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
  });
  document.getElementById('depth-ctrl').addEventListener('click', e => {
    const btn = e.target.closest('.seg-btn');
    if (!btn) return;
    importState.depth = btn.dataset.value;
    document.querySelectorAll('#depth-ctrl .seg-btn').forEach(b =>
      b.classList.toggle('active', b === btn)
    );
  });
  document.getElementById('extract-btn').addEventListener('click', runExtraction);
  document.getElementById('select-all-btn').addEventListener('click', () => {
    document.querySelectorAll('.fact-check').forEach(cb => { cb.checked = true; });
    updateImportBtn();
  });
  document.getElementById('select-none-btn').addEventListener('click', () => {
    document.querySelectorAll('.fact-check').forEach(cb => { cb.checked = false; });
    updateImportBtn();
  });
  document.getElementById('import-btn').addEventListener('click', runImport);

  document.getElementById("flagged-facts-item").addEventListener("click", showFlaggedFacts);

  // Initial state
  enableFactInput(false);

  renderTopics();
  renderCourses();
  refreshFlaggedItem();
});
