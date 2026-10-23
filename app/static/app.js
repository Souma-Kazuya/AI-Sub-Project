// Interactive Frontend Client for QA & Boundary-Value Test Synthesizer

document.addEventListener("DOMContentLoaded", () => {
  const codeEditor = document.getElementById("codeEditor");
  const exampleSelect = document.getElementById("exampleSelect");

  const btnScan = document.getElementById("btnScan");
  const btnSolve = document.getElementById("btnSolve");
  const btnSynthesize = document.getElementById("btnSynthesize");
  const btnAudit = document.getElementById("btnAudit");
  const btnPipeline = document.getElementById("btnPipeline");

  const btnCopyTest = document.getElementById("btnCopyTest");
  const btnDownloadTest = document.getElementById("btnDownloadTest");

  const tabButtons = document.querySelectorAll(".tab-btn");
  const tabPanes = document.querySelectorAll(".tab-pane");

  let currentSynthesizedScript = "";

  // 1. Tab Navigation
  tabButtons.forEach(btn => {
    btn.addEventListener("click", () => {
      const targetTab = btn.getAttribute("data-tab");
      tabButtons.forEach(b => b.classList.remove("active"));
      tabPanes.forEach(p => p.classList.remove("active"));
      btn.classList.add("active");
      const targetPane = document.getElementById(targetTab);
      if (targetPane) targetPane.classList.add("active");
    });
  });

  function switchTab(tabId) {
    const btn = document.querySelector(`.tab-btn[data-tab="${tabId}"]`);
    if (btn) btn.click();
  }

  // 2. Load Examples
  fetch("/api/examples")
    .then(res => res.json())
    .then(examples => {
      examples.forEach(ex => {
        const opt = document.createElement("option");
        opt.value = ex.id;
        opt.textContent = `${ex.title} - ${ex.description}`;
        opt.dataset.code = ex.code;
        exampleSelect.appendChild(opt);
      });

      // Default load first example (loan_approval)
      if (examples.length > 0) {
        exampleSelect.selectedIndex = 1;
        codeEditor.value = examples[0].code;
      }
    })
    .catch(err => console.error("Failed to fetch examples:", err));

  exampleSelect.addEventListener("change", () => {
    const selected = exampleSelect.options[exampleSelect.selectedIndex];
    if (selected && selected.dataset.code) {
      codeEditor.value = selected.dataset.code;
    }
  });

  // 3. API Actions
  btnScan.addEventListener("click", () => runScan(true));
  btnSolve.addEventListener("click", () => runSolve(true));
  btnSynthesize.addEventListener("click", () => runSynthesize(true));
  btnAudit.addEventListener("click", () => runAudit(true));
  btnPipeline.addEventListener("click", runFullPipeline);

  // Phase 1: Scan AST
  async function runScan(switchView = false) {
    const code = codeEditor.value.trim();
    if (!code) return alert("Please enter Python source code.");

    try {
      const res = await fetch("/api/scan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Scan failed");

      renderAST(data);
      if (switchView) switchTab("tab-ast");
      return data;
    } catch (err) {
      alert("Error scanning AST: " + err.message);
    }
  }

  // Phase 2: Solve BVA
  async function runSolve(switchView = false) {
    const code = codeEditor.value.trim();
    if (!code) return alert("Please enter Python source code.");

    try {
      const res = await fetch("/api/solve", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Solve failed");

      renderBVA(data.plans);
      if (switchView) switchTab("tab-bva");
      return data;
    } catch (err) {
      alert("Error solving BVA: " + err.message);
    }
  }

  // Phase 3 & 4: Synthesize
  async function runSynthesize(switchView = false) {
    const code = codeEditor.value.trim();
    if (!code) return alert("Please enter Python source code.");

    try {
      const res = await fetch("/api/synthesize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Synthesize failed");

      currentSynthesizedScript = data.test_script;
      document.getElementById("testCodeDisplay").textContent = data.test_script;
      renderDecisionTable(data.decision_rules);

      if (switchView) switchTab("tab-decision");
      return data;
    } catch (err) {
      alert("Error synthesizing tests: " + err.message);
    }
  }

  // Phase 5: Audit Run
  async function runAudit(switchView = false) {
    const code = codeEditor.value.trim();
    if (!code) return alert("Please enter Python source code.");

    try {
      const res = await fetch("/api/audit", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Audit failed");

      renderAuditOverview(data);
      if (switchView) switchTab("tab-overview");
      return data;
    } catch (err) {
      alert("Error running audit: " + err.message);
    }
  }

  // End-to-End Pipeline
  async function runFullPipeline() {
    await runScan(false);
    await runSolve(false);
    await runSynthesize(false);
    await runAudit(true);
  }

  // Renderers
  function renderAST(data) {
    const container = document.getElementById("astContainer");
    let html = `
      <div class="bva-card">
        <div class="bva-card-header">
          <span class="bva-param-name">Function: def ${data.function_name}()</span>
          <span class="bva-param-type">Lines ${data.line_start} - ${data.line_end}</span>
        </div>
        <p style="font-size: 13px; color: var(--text-secondary); margin-bottom: 12px;">${data.docstring || 'No docstring specification.'}</p>
        
        <h4 style="font-size: 13px; margin-bottom: 8px; color: #a5b4fc;">Parameters (${data.parameters.length}):</h4>
        <div class="bva-chips-row" style="margin-bottom: 14px;">
          ${data.parameters.map(p => `
            <span class="bva-chip valid"><strong>${p.name}</strong>: ${p.type} ${p.has_default ? `(default=${p.default_value})` : ''}</span>
          `).join('')}
        </div>

        <h4 style="font-size: 13px; margin-bottom: 8px; color: #a5b4fc;">Extracted AST Branch Constraints (${data.constraints.length}):</h4>
        <div style="display: flex; flex-direction: column; gap: 6px;">
          ${data.constraints.map(c => `
            <div style="font-family: var(--font-mono); font-size: 12px; padding: 6px 10px; background: rgba(0,0,0,0.3); border-radius: 4px; border-left: 3px solid ${c.is_guard ? '#f43f5e' : '#6366f1'};">
              • <code>${c.raw_expr}</code> ${c.is_guard ? '<span style="color:#f43f5e; font-size: 11px;">(Guard Clause)</span>' : ''} (Line ${c.line_number})
            </div>
          `).join('')}
        </div>
      </div>
    `;
    container.innerHTML = html;
  }

  function renderBVA(plans) {
    const container = document.getElementById("bvaContainer");
    let html = "";
    for (const [pName, plan] of Object.entries(plans)) {
      html += `
        <div class="bva-card">
          <div class="bva-card-header">
            <span class="bva-param-name">${pName}</span>
            <span class="bva-param-type">${plan.inferred_type} | Bounds: [${plan.min_bound}, ${plan.max_bound}]</span>
          </div>
          <div class="bva-chips-row">
            ${plan.boundary_values.map(b => `
              <span class="bva-chip ${b.is_valid ? 'valid' : 'invalid'}" title="${b.description}">
                <strong>${b.category}</strong>: ${b.value === null ? 'None' : b.value}
              </span>
            `).join('')}
          </div>
        </div>
      `;
    }
    container.innerHTML = html;
  }

  function renderDecisionTable(rules) {
    const wrapper = document.getElementById("decisionTableWrapper");
    if (!rules || rules.length === 0) {
      wrapper.innerHTML = "<p class='empty-state'>No rules generated.</p>";
      return;
    }

    let html = `
      <table class="decision-table">
        <thead>
          <tr>
            <th>Rule ID</th>
            <th>Category</th>
            <th>Target Boundary</th>
            <th>Input Combination</th>
            <th>Expected Outcome</th>
            <th>Business Rationale</th>
          </tr>
        </thead>
        <tbody>
    `;

    rules.forEach(r => {
      const isPass = r.expected_outcome === "pass";
      html += `
        <tr>
          <td><strong>${r.rule_id}</strong></td>
          <td><span style="font-family:var(--font-mono); font-size:11px;">${r.category}</span></td>
          <td><code>${r.target_boundary}</code></td>
          <td><code>${JSON.stringify(r.inputs)}</code></td>
          <td>
            <span class="bva-chip ${isPass ? 'valid' : 'invalid'}" style="padding:2px 8px; font-size:11px;">
              ${isPass ? 'Pass' : 'Reject / Err'}
            </span>
          </td>
          <td style="font-size:11px; color:var(--text-secondary);">${r.business_rationale}</td>
        </tr>
      `;
    });

    html += `</tbody></table>`;
    wrapper.innerHTML = html;
  }

  function renderAuditOverview(data) {
    const banner = document.getElementById("auditBanner");
    const bannerTitle = document.getElementById("bannerTitle");
    const bannerDesc = document.getElementById("bannerDesc");

    document.getElementById("statTotal").textContent = data.total_tests;
    document.getElementById("statPassed").textContent = data.passed_tests;
    document.getElementById("statFailed").textContent = data.failed_tests;
    document.getElementById("statDuration").textContent = `${data.duration_sec}s`;

    const defectsSection = document.getElementById("defectsSection");
    const defectsList = document.getElementById("defectsList");

    if (data.is_approved) {
      banner.className = "audit-banner banner-success";
      banner.querySelector(".banner-icon").textContent = "✅";
      bannerTitle.textContent = "PR AUDIT APPROVED — 100% Boundary Pass";
      bannerDesc.textContent = `All ${data.total_tests} boundary limits and equivalence classes satisfied without regressions.`;
      defectsSection.style.display = "none";
    } else {
      banner.className = "audit-banner banner-danger";
      banner.querySelector(".banner-icon").textContent = "❌";
      bannerTitle.textContent = "PR BLOCKED — Boundary Defects Detected";
      bannerDesc.textContent = `Identified ${data.failed_tests} boundary violation(s) or off-by-one errors during isolated sandbox execution.`;

      defectsSection.style.display = "block";
      defectsList.innerHTML = (data.failure_details || []).map((f, i) => `
        <div class="defect-card">
          <div class="defect-title">Defect #${i+1}: [${f.rule_id}] Boundary Violation in ${f.boundary}</div>
          <div class="defect-body">
            <div><strong>Offending Input:</strong> <code>${JSON.stringify(f.inputs)}</code></div>
            <div><strong>AI Diagnostic:</strong> ${f.root_cause}</div>
            <div class="defect-patch">💡 Recommended Fix: ${f.remediation}</div>
          </div>
        </div>
      `).join('');
    }
  }

  // Copy / Download test script
  btnCopyTest.addEventListener("click", () => {
    if (!currentSynthesizedScript) return alert("No synthesized test code available yet.");
    navigator.clipboard.writeText(currentSynthesizedScript).then(() => {
      btnCopyTest.textContent = "✔ Copied!";
      setTimeout(() => btnCopyTest.textContent = "📋 Copy Code", 2000);
    });
  });

  btnDownloadTest.addEventListener("click", () => {
    if (!currentSynthesizedScript) return alert("No synthesized test code available yet.");
    const blob = new Blob([currentSynthesizedScript], { type: "text/x-python" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "test_synthesized_bva.py";
    a.click();
    URL.revokeObjectURL(url);
  });
});
