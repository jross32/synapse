const state = {
  config: null,
  meta: null,
  projects: [],
  currentCase: null,
  currentBenchmark: null,
  currentBundle: null,
  currentGraph: null,
  pollHandle: null,
  query: new URLSearchParams(window.location.search),
};

const els = {
  runtimePill: document.getElementById("runtime-pill"),
  primaryProject: document.getElementById("primary-project"),
  missionProfile: document.getElementById("mission-profile"),
  neighborList: document.getElementById("neighbor-list"),
  caseMode: document.getElementById("case-mode"),
  recipeId: document.getElementById("recipe-id"),
  caseGoal: document.getElementById("case-goal"),
  caseSuccess: document.getElementById("case-success"),
  createCase: document.getElementById("create-case"),
  runCase: document.getElementById("run-case"),
  stopCase: document.getElementById("stop-case"),
  metaBranch: document.getElementById("meta-branch"),
  metaWorktree: document.getElementById("meta-worktree"),
  missionProfileValue: document.getElementById("mission-profile-value"),
  graphSummary: document.getElementById("graph-summary"),
  phaseValue: document.getElementById("phase-value"),
  statusValue: document.getElementById("status-value"),
  workerCount: document.getElementById("worker-count"),
  timelineStream: document.getElementById("timeline-stream"),
  contradictionCount: document.getElementById("contradiction-count"),
  contradictionList: document.getElementById("contradiction-list"),
  claimCount: document.getElementById("claim-count"),
  claimList: document.getElementById("claim-list"),
  minorityCopy: document.getElementById("minority-copy"),
  verdictCopy: document.getElementById("verdict-copy"),
  scorecardList: document.getElementById("scorecard-list"),
  benchmarkLeaderboard: document.getElementById("benchmark-leaderboard"),
  benchmarkComparisons: document.getElementById("benchmark-comparisons"),
  similarityList: document.getElementById("similarity-list"),
  blastRadius: document.getElementById("blast-radius"),
  handoffPack: document.getElementById("handoff-pack"),
  flash: document.getElementById("flash"),
};

document.querySelectorAll("[data-export]").forEach((button) => {
  button.addEventListener("click", () => exportCurrentCase(button.dataset.export));
});
els.createCase.addEventListener("click", createCase);
els.runCase.addEventListener("click", runCurrentCase);
els.stopCase.addEventListener("click", stopCurrentCase);
els.primaryProject.addEventListener("change", renderNeighborOptions);
els.missionProfile.addEventListener("change", onMissionProfileChange);

bootstrap().catch((error) => {
  setRuntime(`Offline: ${error.message}`, true);
  flash(error.message, true);
});

async function bootstrap() {
  state.config = await fetch("/config").then((response) => response.json());
  if (!state.config.synapseToken) {
    throw new Error("Synapse token not available for this app.");
  }
  setRuntime("Connected to Synapse");
  state.meta = await api("/ai-cases/meta");
  await refreshProjects();
  renderMetaOptions();
  await loadInitialCase();
  await loadInitialBenchmarkRun();
  startPolling();
}

async function api(path, options = {}) {
  const response = await fetch(`${state.config.synapseApi}${path}`, {
    method: options.method || "GET",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
      "X-Synapse-Token": state.config.synapseToken,
      ...(options.headers || {}),
    },
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.message || `Request failed with ${response.status}`);
  }
  return response.status === 204 ? null : response.json();
}

async function refreshProjects() {
  const payload = await api("/projects");
  state.projects = payload.projects || [];
  renderProjectOptions();
}

function renderMetaOptions() {
  const profiles = state.meta?.mission_profiles || [];
  const requestedProfile = state.query.get("mission_profile_id") || profiles[0]?.id || "";
  els.missionProfile.innerHTML = profiles
    .map((profile) => {
      const selected = profile.id === requestedProfile ? "selected" : "";
      return `<option value="${escapeHtml(profile.id)}" ${selected}>${escapeHtml(profile.title)}</option>`;
    })
    .join("");
  const requestedMode = state.query.get("case_mode") || profiles.find((item) => item.id === requestedProfile)?.case_mode || state.meta?.case_modes?.[0] || "generate";
  els.caseMode.innerHTML = (state.meta?.case_modes || [])
    .map((mode) => {
      const selected = mode === requestedMode ? "selected" : "";
      return `<option value="${escapeHtml(mode)}" ${selected}>${escapeHtml(startCase(mode))}</option>`;
    })
    .join("");
  els.recipeId.innerHTML = [`<option value="">Auto / none</option>`]
    .concat(
      (state.meta?.recipes || []).map((recipe) => `<option value="${escapeHtml(recipe.id)}">${escapeHtml(recipe.name)}</option>`)
    )
    .join("");
  onMissionProfileChange();
}

function renderProjectOptions() {
  const requestedPrimary = state.query.get("primary_project_id");
  const currentPrimary = els.primaryProject.value || requestedPrimary;
  els.primaryProject.innerHTML = state.projects
    .map((project) => {
      const selected = project.id === currentPrimary ? "selected" : "";
      return `<option value="${escapeHtml(project.id)}" ${selected}>${escapeHtml(project.name)}</option>`;
    })
    .join("");
  renderNeighborOptions();
}

function renderNeighborOptions() {
  const primaryId = els.primaryProject.value;
  const requested = new Set(
    (state.query.get("neighbor_project_ids") || "")
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean)
  );
  const markup = state.projects
    .filter((project) => project.id !== primaryId)
    .map((project) => {
      const checked = requested.has(project.id) ? "checked" : "";
      return `
        <label class="neighbor-option">
          <input type="checkbox" value="${escapeHtml(project.id)}" ${checked} />
          <span>
            <strong>${escapeHtml(project.name)}</strong>
            <small>${escapeHtml(project.path)}</small>
          </span>
        </label>
      `;
    })
    .join("");
  els.neighborList.innerHTML = markup || '<div class="empty">No neighbor projects available.</div>';
}

function onMissionProfileChange() {
  const profileId = els.missionProfile.value;
  const profile = (state.meta?.mission_profiles || []).find((item) => item.id === profileId);
  if (profile?.case_mode) {
    els.caseMode.value = profile.case_mode;
  }
}

function selectedNeighborIds() {
  return [...els.neighborList.querySelectorAll("input[type=checkbox]:checked")].map((input) => input.value);
}

async function loadInitialCase() {
  const queryCaseId = state.query.get("case_id");
  if (queryCaseId) {
    await refreshCurrentCase(queryCaseId);
    return;
  }
  const list = await api("/ai-cases");
  if (Array.isArray(list.cases) && list.cases.length > 0) {
    await refreshCurrentCase(list.cases[0].case.id);
  } else {
    renderCurrentCase();
  }
}

async function loadInitialBenchmarkRun() {
  const benchmarkRunId = state.query.get("benchmark_run_id");
  if (!benchmarkRunId) {
    renderBenchmarkRun();
    return;
  }
  await refreshBenchmarkRun(benchmarkRunId);
}

async function createCase() {
  try {
    const payload = {
      case_mode: els.caseMode.value,
      mission_profile_id: els.missionProfile.value || null,
      intent: {
        goal_md: els.caseGoal.value.trim(),
        success_criteria_md: els.caseSuccess.value.trim(),
        autonomy_mode: "full_autopilot",
      },
      targets: {
        primary_project_id: els.primaryProject.value,
        neighbor_project_ids: selectedNeighborIds(),
      },
      directives: {
        selected_recipe_id: els.recipeId.value || null,
        generation_mode: els.caseMode.value === "generate" ? "local_fullstack" : "prototype",
      },
    };
    const detail = await api("/ai-cases", { method: "POST", body: payload });
    state.currentCase = detail.case;
    await refreshCurrentCase(detail.case.id);
    flash("Case created.");
  } catch (error) {
    flash(error.message, true);
  }
}

async function runCurrentCase() {
  if (!state.currentCase) return;
  try {
    const response = await api(`/ai-cases/${encodeURIComponent(state.currentCase.id)}/run`, {
      method: "POST",
      body: {},
    });
    state.currentCase = response.case.case;
    await refreshCurrentCase(state.currentCase.id);
    flash("Case launched in Synapse.");
  } catch (error) {
    flash(error.message, true);
  }
}

async function stopCurrentCase() {
  if (!state.currentCase) return;
  try {
    await api(`/ai-cases/${encodeURIComponent(state.currentCase.id)}/stop`, { method: "POST" });
    await refreshCurrentCase(state.currentCase.id);
    flash("Case stopped.");
  } catch (error) {
    flash(error.message, true);
  }
}

async function exportCurrentCase(kind) {
  if (!state.currentCase) return;
  try {
    const result = await api(
      `/ai-cases/${encodeURIComponent(state.currentCase.id)}/export/${encodeURIComponent(kind)}`,
      { method: "POST" }
    );
    const summary = result.path ? `${kind} exported to ${result.path}` : `${kind} exported.`;
    flash(summary);
  } catch (error) {
    flash(error.message, true);
  }
}

async function refreshCurrentCase(caseId) {
  const [detail, bundle, graph] = await Promise.all([
    api(`/ai-cases/${encodeURIComponent(caseId)}`),
    api(`/ai-cases/${encodeURIComponent(caseId)}/bundle`),
    api(`/ai-cases/${encodeURIComponent(caseId)}/graph`),
  ]);
  state.currentCase = detail.case;
  state.currentBundle = bundle;
  state.currentGraph = graph;
  renderCurrentCase(detail);
}

async function refreshBenchmarkRun(runId) {
  const detail = await api(`/benchmarks/runs/${encodeURIComponent(runId)}`);
  state.currentBenchmark = detail;
  renderBenchmarkRun();
}

function renderCurrentCase(detail) {
  const caseData = detail?.case || state.currentCase;
  const bundle = state.currentBundle;
  const graph = state.currentGraph;
  const activeWorkers = detail?.active_workers || [];

  els.runCase.disabled = !caseData;
  els.stopCase.disabled = !caseData || caseData.status !== "running";
  document.querySelectorAll("[data-export]").forEach((button) => {
    button.disabled = !caseData;
  });

  els.metaBranch.textContent = caseData?.branch_name || "Not allocated";
  els.metaWorktree.textContent = caseData?.worktree_path || "Not allocated";
  els.phaseValue.textContent = startCase(caseData?.phase || "setup");
  els.statusValue.textContent = startCase(caseData?.status || "draft");
  els.workerCount.textContent = String(activeWorkers.length);
  els.missionProfileValue.textContent = startCase(caseData?.mission_profile_id || "not set");
  els.graphSummary.textContent = graph?.nodes?.length
    ? `${graph.nodes.length} case(s) · ${graph.edges.length} edge(s)`
    : "No lineage yet";

  if (!bundle) {
    els.timelineStream.innerHTML = '<div class="empty">Create a case to begin.</div>';
    els.claimList.innerHTML = '<div class="empty">No claim cards yet.</div>';
    els.contradictionList.innerHTML = '<div class="empty">No contradictions recorded yet.</div>';
    els.scorecardList.innerHTML = '<div class="empty">No scorecard recorded yet.</div>';
    renderBenchmarkRun();
    els.similarityList.innerHTML = '<div class="empty">No similarity report recorded yet.</div>';
    els.claimCount.textContent = "0";
    els.contradictionCount.textContent = "0 open";
    els.minorityCopy.textContent = "No minority report captured yet.";
    els.verdictCopy.textContent = "No verdict captured yet.";
    els.blastRadius.innerHTML = '<div class="empty">No blast radius recorded yet.</div>';
    els.handoffPack.innerHTML = '<div class="empty">No handoff pack recorded yet.</div>';
    return;
  }

  els.caseGoal.value = caseData.intent?.goal_md || els.caseGoal.value;
  els.caseSuccess.value = caseData.intent?.success_criteria_md || els.caseSuccess.value;
  if (caseData?.mission_profile_id) {
    els.missionProfile.value = caseData.mission_profile_id;
  }
  if (caseData?.case_mode) {
    els.caseMode.value = caseData.case_mode;
  }
  if (caseData?.directives?.selected_recipe_id) {
    els.recipeId.value = caseData.directives.selected_recipe_id;
  }
  els.timelineStream.innerHTML = renderTimeline(bundle.timeline, graph);
  els.claimList.innerHTML = renderClaims(bundle.claim_cards);
  els.contradictionList.innerHTML = renderContradictions(bundle.contradiction_docket);
  els.scorecardList.innerHTML = renderScorecard(bundle.scorecard);
  renderBenchmarkRun();
  els.similarityList.innerHTML = renderSimilarity(bundle.similarity_report);
  els.claimCount.textContent = String(bundle.claim_cards.length);
  const openContradictions = bundle.contradiction_docket.filter((item) => item.status !== "resolved").length;
  els.contradictionCount.textContent = `${openContradictions} open`;
  els.minorityCopy.textContent =
    bundle.minority_report.summary ||
    bundle.minority_report.strongest_losing_argument ||
    "No minority report captured yet.";
  els.verdictCopy.textContent =
    bundle.verdict.summary ||
    bundle.verdict.chosen_direction ||
    "No verdict captured yet.";
  els.blastRadius.innerHTML = renderListGroup([
    ...bundle.blast_radius.touched_areas.map((item) => `Touched: ${item}`),
    ...bundle.blast_radius.contracts.map((item) => `Contract: ${item}`),
    ...bundle.blast_radius.tests.map((item) => `Test: ${item}`),
    ...bundle.blast_radius.likely_regressions.map((item) => `Regression risk: ${item}`),
  ]);
  els.handoffPack.innerHTML = renderListGroup([
    ...bundle.handoff_pack.first_steps.map((item) => `First step: ${item}`),
    ...bundle.handoff_pack.tests.map((item) => `Verify: ${item}`),
    ...bundle.handoff_pack.rollback_notes.map((item) => `Rollback: ${item}`),
    ...bundle.handoff_pack.unresolved_questions.map((item) => `Open question: ${item}`),
  ]);
}

function renderBenchmarkRun() {
  const report = state.currentBenchmark?.report;
  if (!report?.official_quality_ranking?.length) {
    els.benchmarkLeaderboard.innerHTML = '<div class="empty">No benchmark run loaded yet.</div>';
    els.benchmarkComparisons.innerHTML = '<div class="empty">No benchmark comparisons loaded yet.</div>';
    return;
  }
  els.benchmarkLeaderboard.innerHTML = report.official_quality_ranking
    .map(
      (item, index) => `
        <article class="card-item">
          <div class="section-head">
            <h3>#${index + 1} ${escapeHtml(String(item.candidate_key || "candidate"))}</h3>
            <span class="pill">${escapeHtml(String(item.confidence_label || "n/a"))}</span>
          </div>
          <p>Quality ${escapeHtml(String(item.median_quality_score_100 ?? "n/a"))} · Tokens ${escapeHtml(String(item.median_total_tokens ?? "n/a"))} · Elapsed ${escapeHtml(String(item.median_elapsed_seconds ?? "n/a"))}</p>
          <small>Pass rate ${escapeHtml(String(item.pass_rate ?? "n/a"))}${item.efficiency_frontier ? " · Pareto frontier" : ""}</small>
        </article>
      `
    )
    .join("");
  els.benchmarkComparisons.innerHTML = (report.comparisons || [])
    .map(
      (item) => `
        <article class="card-item">
          <div class="section-head">
            <h3>${escapeHtml(String(item.scenario_id || "scenario"))} / ${escapeHtml(String(item.runtime_id || "runtime"))}</h3>
            <span class="pill">${escapeHtml(String(item.confidence_label || "n/a"))}</span>
          </div>
          <p>Winner: ${escapeHtml(String(item.winner_candidate_key || "n/a"))}</p>
          <small>${item.noisy ? "Noisy comparison -- avoid strong token claims." : "Stable comparison."}${item.notes ? " " + escapeHtml(String(item.notes)) : ""}</small>
        </article>
      `
    )
    .join("") || '<div class="empty">No benchmark comparisons loaded yet.</div>';
}

function renderTimeline(entries, graph) {
  const items = [];
  if (graph?.edges?.length) {
    items.push(`
      <article class="stream-item">
        <div class="pill">Graph</div>
        <p><strong>Case lineage</strong></p>
        <small>${escapeHtml(`${graph.nodes.length} case(s), ${graph.edges.length} edge(s)` )}</small>
      </article>
    `);
  }
  if (!entries?.length) {
    items.push('<div class="empty">No timeline yet.</div>');
  } else {
    items.push(
      ...[...entries]
        .reverse()
        .map(
          (entry) => `
            <article class="stream-item">
              <div class="pill">${escapeHtml(startCase(entry.phase))}</div>
              <p><strong>${escapeHtml(entry.label)}</strong></p>
              <small>${escapeHtml(entry.summary || "No summary.")}</small>
            </article>
          `
        )
    );
  }
  return items.join("");
}

function renderClaims(cards) {
  if (!cards?.length) return '<div class="empty">No claim cards yet.</div>';
  return cards
    .map(
      (card) => `
        <article class="card-item">
          <div class="section-head">
            <h3>${escapeHtml(card.title)}</h3>
            <span class="pill">${escapeHtml(card.kind)}</span>
          </div>
          <p>${escapeHtml(card.summary || "No summary.")}</p>
          <small>${escapeHtml(card.source_label || card.source_ref || "Untitled source")}</small>
        </article>
      `
    )
    .join("");
}

function renderContradictions(items) {
  if (!items?.length) return '<div class="empty">No contradictions recorded yet.</div>';
  return items
    .map(
      (item) => `
        <article class="contradiction-item">
          <div class="section-head">
            <h3>${escapeHtml(item.question)}</h3>
            <span class="pill">${escapeHtml(item.status)}</span>
          </div>
          <p>${escapeHtml(item.stakes || "No stakes recorded.")}</p>
          <small>${escapeHtml(item.ruling || "No ruling yet.")}</small>
        </article>
      `
    )
    .join("");
}

function renderScorecard(scorecard) {
  if (!scorecard?.items?.length) return '<div class="empty">No scorecard recorded yet.</div>';
  return scorecard.items
    .map(
      (item) => `
        <article class="card-item">
          <div class="section-head">
            <h3>${escapeHtml(item.label)}</h3>
            <span class="pill">${escapeHtml(item.status)}</span>
          </div>
          <p>${escapeHtml(item.summary || "Pending.")}</p>
        </article>
      `
    )
    .join("");
}

function renderSimilarity(report) {
  if (!report?.dimensions?.length) return '<div class="empty">No similarity report recorded yet.</div>';
  return report.dimensions
    .map(
      (item) => `
        <article class="card-item">
          <div class="section-head">
            <h3>${escapeHtml(item.label)}</h3>
            <span class="pill">${escapeHtml(item.score == null ? "n/a" : `${item.score}%`)}</span>
          </div>
          <p>${escapeHtml(item.notes || report.similarity_explanation_md || "No notes yet.")}</p>
        </article>
      `
    )
    .join("");
}

function renderListGroup(items) {
  if (!items?.length) return '<div class="empty">Nothing recorded yet.</div>';
  return items.map((item) => `<article class="card-item"><p>${escapeHtml(item)}</p></article>`).join("");
}

function startPolling() {
  if (state.pollHandle) window.clearInterval(state.pollHandle);
  state.pollHandle = window.setInterval(async () => {
    try {
      if (state.currentCase) {
        await refreshCurrentCase(state.currentCase.id);
      }
      const benchmarkRunId = state.query.get("benchmark_run_id");
      if (benchmarkRunId) {
        await refreshBenchmarkRun(benchmarkRunId);
      }
      setRuntime("Connected to Synapse");
    } catch {
      setRuntime("Reconnecting…", true);
    }
  }, 3000);
}

function setRuntime(text, warning = false) {
  els.runtimePill.textContent = text;
  els.runtimePill.style.color = warning ? "var(--warm)" : "var(--accent)";
}

function flash(message, error = false) {
  els.flash.textContent = message;
  els.flash.style.color = error ? "#ffd9d3" : "var(--text)";
  els.flash.style.borderColor = error ? "rgba(255, 130, 111, 0.32)" : "var(--panel-edge)";
  els.flash.classList.add("visible");
  window.clearTimeout(flash._timer);
  flash._timer = window.setTimeout(() => els.flash.classList.remove("visible"), 2600);
}

function startCase(value) {
  return String(value || "")
    .split("-")
    .join(" ")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function escapeHtml(text) {
  return String(text ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}
