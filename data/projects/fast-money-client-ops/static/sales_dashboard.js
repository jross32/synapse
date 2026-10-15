(async function () {
  const root = document.getElementById("sales-pipeline-board");
  if (!root) return;
  const esc = value => String(value == null ? "" : value).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const hunter = document.getElementById("client-hunter-board");
  if (hunter) {
    try {
      const res = await fetch("/api/client-hunter/readiness", {credentials:"same-origin",cache:"no-store"});
      if (!res.ok) throw new Error("Readiness endpoint unavailable");
      const d = await res.json();
      const runRes = await fetch("/api/client-hunter/latest-run", {credentials:"same-origin",cache:"no-store"});
      const latest = runRes.ok ? (await runRes.json()).report : null;
      const blockers = (d.blockers || []).map(x=>"<li>"+esc(x)+"</li>").join("");
      hunter.innerHTML = '<h3>Client Hunter — local outreach pilot</h3><p>Prepared drafts: '+Number(d.drafts || 0)+' · Verified sends: '+Number(d.verified_sent || 0)+' · Verified payments: '+Number(d.verified_payments || 0)+'</p><p><strong>'+(d.ready_for_outreach ? 'Ready for reviewed outreach' : 'Outreach blocked until requirements are satisfied')+'</strong></p>'+(blockers ? '<ul>'+blockers+'</ul>':'')+'<p class="muted">Read-only status. No messages sent or payments triggered by this dashboard.</p>';
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = "Run safe Client Hunter cycle";
      button.addEventListener("click", async () => {
        button.disabled = true;
        button.textContent = "Running...";
        try {
          const sessionRes = await fetch("/api/session", {credentials:"same-origin",cache:"no-store"});
          const sessionData = await sessionRes.json();
          const token = sessionData.session && sessionData.session.csrf_token;
          if (!sessionRes.ok || !token) throw new Error("Operator verification required");
          const runRes = await fetch("/api/client-hunter/run", {method:"POST",credentials:"same-origin",cache:"no-store",headers:{"X-CSRF-Token":token}});
          const run = await runRes.json();
          if (!runRes.ok) throw new Error(run.error || "Run failed");
          button.textContent = "Completed: " + run.processed + " prospects, 0 emails sent";
          const summary = document.getElementById("client-hunter-run-summary");
          if (summary) summary.textContent = "Last cycle: " + run.mode + " · " + run.processed + " prospects processed · " + run.external_messages_sent + " emails sent";
        } catch (error) { button.textContent = "Retry safe cycle"; const m=document.createElement("p");m.textContent=error.message;hunter.appendChild(m); }
        finally { button.disabled = false; }
      });
      hunter.appendChild(button);      if (latest) { const p=document.createElement("p"); p.id="client-hunter-run-summary"; p.textContent="Last cycle: "+latest.mode+" · "+latest.actions.length+" prospects processed · "+latest.external_messages_sent+" emails sent"; hunter.appendChild(p); }
    } catch (e) {hunter.textContent="Client Hunter status unavailable: "+e.message;}
  }  try {
    const response = await fetch("/api/workspace-state", {credentials:"same-origin",cache:"no-store"});
    if (!response.ok) throw new Error("Operator access required");
    const state = await response.json();
    const data = state.data || {};
    const leads = data.leads || [], quotes = data.quotes || [], invoices = data.invoices || [];
    const actualPaid = invoices.filter(x => x.status === "paid" && x.payment_verified === true);
    const rows = leads.map(lead => {
      const q = quotes.find(x => x.lead_id === lead.id);
      const invoice = invoices.find(x => x.lead_id === lead.id);
      const research = lead.research_evidence_url ? '<a href="'+esc(lead.research_evidence_url)+'" target="_blank" rel="noopener noreferrer">Evidence</a>' : "Not researched";
      const roi = lead.roi_verified === true ? esc(lead.estimated_monthly_roi_usd)+" USD/mo (verified)" : "Not verified";
      return '<tr><td><strong>'+esc(lead.company || "Unknown")+'</strong></td><td>'+research+'</td><td>'+roi+'</td><td>'+esc(lead.email_draft_status || "Not drafted")+'</td><td>'+esc(lead.outreach_approval || "Not approved")+'</td><td>'+esc(lead.reply_status || "Not tracked")+'</td><td>'+esc(q ? q.status : "No proposal")+'</td><td>'+esc(invoice && invoice.payment_verified === true ? invoice.status : "Unverified")+'</td><td>'+esc(lead.stage || "Unknown")+'</td></tr>';
    }).join("");
    root.innerHTML = '<div class="meta"><span class="chip">Leads: '+leads.length+'</span><span class="chip">Approved outreach: '+leads.filter(x=>x.outreach_approval==="approved").length+'</span><span class="chip">Verified payments: '+actualPaid.length+'</span></div><div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse;text-align:left"><thead><tr><th>Company</th><th>Research</th><th>ROI</th><th>Email draft</th><th>Approval</th><th>Reply</th><th>Proposal</th><th>Payment</th><th>Customer status</th></tr></thead><tbody>'+ (rows || '<tr><td colspan="9">No researched companies yet.</td></tr>') +'</tbody></table></div><p class="muted">Missing evidence is shown as unverified. No email sends or payment actions are performed here.</p>';
  } catch(e) { root.textContent = "Sales pipeline unavailable: "+e.message; }
})();
