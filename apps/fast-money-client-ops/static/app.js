function escapeHtml(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function money(value) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(value || 0);
}

function tile(title, subtitle, chips, action) {
  const meta = (chips || [])
    .filter(Boolean)
    .map((chip) => '<span class="chip">' + escapeHtml(chip) + "</span>")
    .join("");
  const actionHtml = action ? '<div class="tile-actions">' + action + "</div>" : "";
  return '<article class="tile"><h4>' + escapeHtml(title) +
    '</h4><p class="muted">' + escapeHtml(subtitle) +
    '</p><div class="meta">' + meta + "</div>" + actionHtml + "</article>";
}

function setStatus(id, message, tone) {
  const status = document.getElementById(id);
  if (!status) return;
  status.textContent = message || "";
  status.dataset.tone = tone || "neutral";
}

function ensurePortalStatus() {
  const quotes = document.getElementById("portal-quotes");
  if (!quotes) return null;
  let status = document.getElementById("portal-status");
  if (!status) {
    status = document.createElement("p");
    status.id = "portal-status";
    status.className = "status-message";
    status.setAttribute("role", "status");
    status.setAttribute("aria-live", "polite");
    quotes.before(status);
  }
  return status;
}

function setPortalStatus(message, tone) {
  ensurePortalStatus();
  setStatus("portal-status", message, tone);
}

function setOpsStatus(message, tone) {
  setStatus("ops-status", message, tone);
}

async function loadWorkspaceState() {
  const response = await fetch("/api/workspace-state", {
    headers: { Accept: "application/json" },
    cache: "no-store",
  });
  if (response.status === 401) {
    window.location.replace("/signin");
    throw new Error("Session expired. Sign in again.");
  }
  if (!response.ok) throw new Error("Workspace state could not be loaded.");
  const payload = await response.json();
  if (!payload || !payload.data) throw new Error("Workspace state response was invalid.");
  return payload;
}

async function postWorkflowAction(path, body) {
  const auth = window.fastMoneyAuth;
  const csrfToken = auth && typeof auth.getCsrfToken === "function"
    ? await auth.getCsrfToken()
    : null;
  if (!csrfToken) {
    window.location.replace("/signin");
    throw new Error("Session expired. Sign in again.");
  }

  const options = {
    method: "POST",
    headers: {
      Accept: "application/json",
      "X-CSRF-Token": csrfToken,
    },
  };
  if (body) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  const response = await fetch(path, options);
  const payload = await response.json().catch(() => ({}));
  if (response.status === 401) {
    window.location.replace("/signin");
    throw new Error(payload.error || "Session expired. Sign in again.");
  }
  if (!response.ok || !payload.ok || !payload.workspace) {
    throw new Error(payload.error || "Workflow action failed.");
  }
  workspace = payload.workspace;
  data = workspace.data || {};
  return payload.result || {};
}

async function approveQuote(quoteId) {
  return postWorkflowAction(
    "/api/quotes/" + encodeURIComponent(quoteId) + "/approve"
  );
}

function bindQuoteActions() {
  document.querySelectorAll(".approve-quote").forEach((button) => {
    button.addEventListener("click", async () => {
      const quoteId = button.dataset.quoteId;
      if (!quoteId) return;
      button.disabled = true;
      button.textContent = "Approving...";
      try {
        const result = await approveQuote(quoteId);
        renderPortal(data);
        setPortalStatus(
          result.already_approved
            ? "This quote was already approved."
            : "Quote approved. A kickoff job is now ready to schedule.",
          "success"
        );
      } catch (error) {
        button.disabled = false;
        button.textContent = "Approve quote";
        setPortalStatus(error.message || "Approval failed.", "error");
      }
    });
  });
}

function defaultScheduleValue() {
  const date = new Date();
  date.setDate(date.getDate() + 1);
  date.setHours(10, 0, 0, 0);
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 16);
}

function jobAction(item) {
  if (item.status === "completed") {
    return '<span class="approval-ok">Completed Â· invoice created</span>';
  }
  if (item.status === "scheduled") {
    return '<button class="button small primary complete-job" type="button" data-job-id="' +
      escapeHtml(item.id) + '">Mark complete</button>';
  }
  return '<form class="inline-form schedule-job" data-job-id="' + escapeHtml(item.id) + '">' +
    '<label class="inline-field"><span>Owner</span><input name="owner" maxlength="80" required placeholder="Owner name"></label>' +
    '<label class="inline-field"><span>Kickoff</span><input name="scheduled_for" type="datetime-local" required value="' +
    defaultScheduleValue() + '"></label>' +
    '<button class="button small primary" type="submit">Schedule kickoff</button>' +
    "</form>";
}

function invoiceAction(item) {
  if (item.status === "paid" && item.payment_verified === true) {
    return '<span class="approval-ok">Stripe payment verified</span>';
  }
  if (item.status === "paid") {
    return '<span class="muted">Legacy paid status — verification unavailable</span>';
  }
  if (item.status === "sent") {
    return '<span class="muted">Awaiting verified Stripe payment</span>';
  }
  if (item.status === "draft") {
    return '<button class="button small primary invoice-action" type="button" data-action="send" data-invoice-id="' +
      escapeHtml(item.id) + '">Send invoice</button>';
  }
  return "";
}

function bindJobActions() {
  document.querySelectorAll(".schedule-job").forEach((form) => {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const jobId = form.dataset.jobId;
      const submit = form.querySelector('button[type="submit"]');
      const formData = new FormData(form);
      if (!jobId) return;
      if (submit) {
        submit.disabled = true;
        submit.textContent = "Scheduling...";
      }
      try {
        const result = await postWorkflowAction(
          "/api/jobs/" + encodeURIComponent(jobId) + "/schedule",
          {
            owner: formData.get("owner"),
            scheduled_for: formData.get("scheduled_for"),
          }
        );
        renderOps(data, workspace);
        setOpsStatus(
          result.already_scheduled ? "That kickoff was already scheduled." : "Kickoff scheduled.",
          "success"
        );
      } catch (error) {
        if (submit) {
          submit.disabled = false;
          submit.textContent = "Schedule kickoff";
        }
        setOpsStatus(error.message || "Scheduling failed.", "error");
      }
    });
  });

  document.querySelectorAll(".complete-job").forEach((button) => {
    button.addEventListener("click", async () => {
      const jobId = button.dataset.jobId;
      if (!jobId) return;
      button.disabled = true;
      button.textContent = "Completing...";
      try {
        const result = await postWorkflowAction(
          "/api/jobs/" + encodeURIComponent(jobId) + "/complete"
        );
        renderOps(data, workspace);
        setOpsStatus(
          result.already_completed
            ? "That job was already complete."
            : "Job completed. A draft invoice is ready to send.",
          "success"
        );
      } catch (error) {
        button.disabled = false;
        button.textContent = "Mark complete";
        setOpsStatus(error.message || "Completion failed.", "error");
      }
    });
  });
}

function bindInvoiceActions() {
  document.querySelectorAll(".invoice-action").forEach((button) => {
    button.addEventListener("click", async () => {
      const invoiceId = button.dataset.invoiceId;
      const action = button.dataset.action;
      if (!invoiceId || !action) return;
      button.disabled = true;
      button.textContent = action === "send" ? "Sending..." : "Updating...";
      try {
        const result = await postWorkflowAction(
          "/api/invoices/" + encodeURIComponent(invoiceId) + "/" + action
        );
        renderOps(data, workspace);
        setOpsStatus(
          action === "send"
            ? (result.already_sent ? "Invoice was already sent." : "Invoice sent.")
            : (result.already_paid ? "Invoice was already paid." : "Invoice paid. Renewal handoff is ready."),
          "success"
        );
      } catch (error) {
        button.disabled = false;
        button.textContent = action === "send" ? "Send invoice" : "Mark paid";
        setOpsStatus(error.message || "Invoice update failed.", "error");
      }
    });
  });
}

function renderPortal(currentData) {
  const quotes = document.getElementById("portal-quotes");
  const jobs = document.getElementById("portal-jobs");
  ensurePortalStatus();

  if (quotes) {
    quotes.innerHTML = (currentData.quotes || [])
      .map((item) => {
        const action = item.status === "approved"
          ? '<span class="approval-ok">Approved in workspace</span>'
          : '<button class="button small approve-quote" type="button" data-quote-id="' +
            escapeHtml(item.id) + '">Approve quote</button>';
        return tile(
          item.package,
          item.status + " â€¢ " + money(item.amount_usd),
          [item.id, item.lead_id],
          action
        );
      })
      .join("");
    bindQuoteActions();
  }

  if (jobs) {
    const rows = (currentData.jobs || []).concat(currentData.invoices || []);
    jobs.innerHTML = rows
      .map((item) =>
        tile(
          item.client,
          item.next_step || item.status + " â€¢ " + money(item.amount_usd),
          [item.id, item.status]
        )
      )
      .join("");
  }
}

function renderAudit(currentWorkspace) {
  const container = document.getElementById("ops-audit");
  if (!container) return;
  const entries = (currentWorkspace.audit_log || []).slice().reverse();
  if (!entries.length) {
    container.innerHTML = '<p class="muted">No workflow changes recorded yet.</p>';
    return;
  }
  container.innerHTML = entries.slice(0, 12)
    .map((entry) => {
      const when = entry.occurred_at
        ? new Date(entry.occurred_at).toLocaleString()
        : "Time unavailable";
      return tile(
        entry.message || entry.type || "Workflow update",
        when,
        [entry.type, entry.quote_id, entry.job_id, entry.invoice_id]
      );
    })
    .join("");
}

function renderOps(currentData, currentWorkspace) {
  const leads = document.getElementById("ops-leads");
  const jobs = document.getElementById("ops-jobs");
  const invoices = document.getElementById("ops-invoices");

  if (leads) {
    leads.innerHTML = (currentData.leads || [])
      .map((item) =>
        tile(
          item.company,
          item.contact + " â€¢ " + money(item.value_usd),
          [item.stage, item.id]
        )
      )
      .join("");
  }

  if (jobs) {
    jobs.innerHTML = (currentData.jobs || [])
      .map((item) =>
        tile(
          item.client,
          item.next_step || item.status,
          [item.status, item.owner, item.id],
          jobAction(item)
        )
      )
      .join("");
  }

  if (invoices) {
    invoices.innerHTML = (currentData.invoices || [])
      .map((item) =>
        tile(
          item.client,
          (item.next_step || item.status) + " â€¢ " + money(item.amount_usd),
          [item.status, item.renewal_status, item.id],
          invoiceAction(item)
        )
      )
      .join("");
  }

  renderAudit(currentWorkspace);
  bindJobActions();
  bindInvoiceActions();
}

function renderCatalog(currentData, config) {
  const container = document.getElementById("catalog-items");
  if (!container || !config.include_catalog_editor) return;
  container.innerHTML = (currentData.catalog || [])
    .map((item) =>
      tile(
        item.name,
        item.category + " â€¢ from " + money(item.price_from_usd),
        [item.id]
      )
    )
    .join("");
}

const config = window.FAST_MONEY_CONFIG || {};
let workspace = {
  schema_version: 2,
  workspace_id: "local-default",
  updated_at: null,
  data: JSON.parse(JSON.stringify(window.FAST_MONEY_DATA || {})),
  audit_log: [],
};
let data = workspace.data;
const page = document.body.getAttribute("data-page");

async function bootstrap() {
  if (!["portal", "ops", "catalog"].includes(page)) return;
  try {
    workspace = await loadWorkspaceState();
    data = workspace.data || {};
  } catch (error) {
    if (page === "portal") {
      setPortalStatus("Workspace storage is unavailable. Showing read-only seed data.", "error");
    }
    if (page === "ops") {
      setOpsStatus("Workspace storage is unavailable. Showing read-only seed data.", "error");
    }
  }
  if (page === "portal") renderPortal(data);
  if (page === "ops") renderOps(data, workspace);
  if (page === "catalog") renderCatalog(data, config);
}

bootstrap();

