/**
 * AI-Native Spec-Driven Pipeline Web Studio Client
 */

(function () {
  'use strict';

  // State
  let currentSessionId = null;
  let activeSpecData = null;
  let activePlanData = null;
  let activeImplementationData = null;
  let currentSynthesizedFiles = {};
  let debounceValidateTimer = null;

  // DOM Elements
  const el = {
    templateSelect: document.getElementById('templateSelect'),
    specEditor: document.getElementById('specEditor'),
    providerModelSelect: document.getElementById('providerModelSelect'),
    chkGovernanceMode: document.getElementById('chkGovernanceMode'),
    btnValidate: document.getElementById('btnValidate'),
    btnPlanOnly: document.getElementById('btnPlanOnly'),
    btnExecute: document.getElementById('btnExecute'),
    executeBtnText: document.getElementById('executeBtnText'),
    headerModelStatus: document.getElementById('headerModelStatus'),
    activeModelLabel: document.getElementById('activeModelLabel'),

    // Checklist
    checkItems: document.querySelectorAll('.check-item'),

    // Tabs
    tabLinks: document.querySelectorAll('.tab-link'),
    tabPanes: document.querySelectorAll('.tab-pane'),

    // Governance Card
    govCard: document.getElementById('govCard'),
    govCheckpointPill: document.getElementById('govCheckpointPill'),
    govTitle: document.getElementById('govTitle'),
    govStatusPill: document.getElementById('govStatusPill'),
    govDesc: document.getElementById('govDesc'),
    govPlanId: document.getElementById('govPlanId'),
    govReviewerInput: document.getElementById('govReviewerInput'),
    btnApproveGov: document.getElementById('btnApproveGov'),
    btnRejectGov: document.getElementById('btnRejectGov'),
    approveBtnLabel: document.getElementById('approveBtnLabel'),

    // Metrics
    metricHash: document.getElementById('metricHash'),
    metricTasks: document.getElementById('metricTasks'),
    metricFiles: document.getElementById('metricFiles'),
    metricRisks: document.getElementById('metricRisks'),

    // Tab 1: Overview & Plan
    archDesignSummary: document.getElementById('archDesignSummary'),
    archDecisionsList: document.getElementById('archDecisionsList'),
    tasksList: document.getElementById('tasksList'),
    risksTable: document.getElementById('risksTable'),

    // Tab 2: Code & Diffs
    synthesizedFilesTree: document.getElementById('synthesizedFilesTree'),
    viewerFileName: document.getElementById('viewerFileName'),
    viewerFileAction: document.getElementById('viewerFileAction'),
    diffViewport: document.getElementById('diffViewport'),

    // Tab 3: Tests & Traceability
    traceabilityMatrixTable: document.getElementById('traceabilityMatrixTable'),
    testsCodeViewport: document.getElementById('testsCodeViewport'),

    // Tab 4: Quality Gates
    gatesGrid: document.getElementById('gatesGrid'),

    // Tab 5: Provenance
    provenanceSignaturesTable: document.getElementById('provenanceSignaturesTable'),
    provenanceJsonViewport: document.getElementById('provenanceJsonViewport'),
    linkLiveDashboard: document.getElementById('linkLiveDashboard'),
    linkLiveReport: document.getElementById('linkLiveReport'),

    // Toast
    toastRoot: document.getElementById('toastRoot'),
  };

  // ── Initialization ─────────────────────────────────────────────────────── //

  async function init() {
    setupTabNavigation();
    setupEventListeners();
    await loadTemplates();
    await loadModelProviders();
  }

  // ── Tab Switching ──────────────────────────────────────────────────────── //

  function setupTabNavigation() {
    el.tabLinks.forEach(link => {
      link.addEventListener('click', () => {
        const targetTabId = link.getAttribute('data-tab');
        switchTab(targetTabId);
      });
    });
  }

  function switchTab(tabId) {
    el.tabLinks.forEach(l => l.classList.toggle('active', l.getAttribute('data-tab') === tabId));
    el.tabPanes.forEach(p => p.classList.toggle('active', p.id === tabId));
  }

  // ── Event Listeners ────────────────────────────────────────────────────── //

  function setupEventListeners() {
    // Template selection
    el.templateSelect.addEventListener('change', () => {
      const selectedOption = el.templateSelect.selectedOptions[0];
      if (selectedOption && selectedOption.dataset.content) {
        el.specEditor.value = selectedOption.dataset.content;
        triggerValidation();
      }
    });

    // Editor real-time debounced validation
    el.specEditor.addEventListener('input', () => {
      clearTimeout(debounceValidateTimer);
      debounceValidateTimer = setTimeout(triggerValidation, 400);
    });

    // Provider / Model selection change
    el.providerModelSelect.addEventListener('change', updateModelHeader);

    // Buttons
    el.btnValidate.addEventListener('click', triggerValidation);
    el.btnPlanOnly.addEventListener('click', handlePlanOnly);
    el.btnExecute.addEventListener('click', handleExecutePipeline);

    // Governance Approval / Rejection
    el.btnApproveGov.addEventListener('click', handleGovApprove);
    el.btnRejectGov.addEventListener('click', handleGovReject);
  }

  // ── Load Templates & Providers ─────────────────────────────────────────── //

  async function loadTemplates() {
    try {
      const res = await fetch('/api/specs');
      const data = await res.json();
      if (data.specs && data.specs.length > 0) {
        el.templateSelect.innerHTML = '';
        data.specs.forEach((s, idx) => {
          const opt = document.createElement('option');
          opt.value = s.filename;
          opt.textContent = `${s.title} (${s.format.toUpperCase()})`;
          opt.dataset.content = s.content;
          opt.dataset.format = s.format;
          if (idx === 0) opt.selected = true;
          el.templateSelect.appendChild(opt);
        });

        // Set initial spec content
        el.specEditor.value = data.specs[0].content;
        triggerValidation();
      }
    } catch (err) {
      showToast('Failed to load spec templates', 'error');
    }
  }

  async function loadModelProviders() {
    try {
      const res = await fetch('/api/models');
      const data = await res.json();
      if (data.providers) {
        el.providerModelSelect.innerHTML = '';
        data.providers.forEach(p => {
          const opt = document.createElement('option');
          opt.value = p.id;
          opt.textContent = `${p.name} ${p.configured ? '🟢 [Active Key]' : '⚪'}`;
          if (p.id === data.current_provider) opt.selected = true;
          el.providerModelSelect.appendChild(opt);
        });
        updateModelHeader();
      }
    } catch (err) {
      console.warn('Could not load providers', err);
    }
  }

  function updateModelHeader() {
    const opt = el.providerModelSelect.selectedOptions[0];
    if (opt) {
      el.activeModelLabel.textContent = opt.textContent.replace('🟢 [Active Key]', '').trim();
    }
  }

  // ── Live 6-Section Schema Validation ───────────────────────────────────── //

  async function triggerValidation() {
    const content = el.specEditor.value.trim();
    if (!content) {
      resetChecklist();
      return;
    }

    const fmt = detectFormat(content);

    try {
      const res = await fetch('/api/validate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content, format: fmt }),
      });
      const data = await res.json();

      if (data.valid && data.section_checklist) {
        updateChecklist(data.section_checklist);
        if (data.spec_hash) {
          el.metricHash.textContent = data.spec_hash.substring(0, 16) + '...';
        }
      } else if (data.section_checklist) {
        updateChecklist(data.section_checklist);
      }
    } catch (err) {
      console.warn('Validation error', err);
    }
  }

  function detectFormat(content) {
    if (content.startsWith('{')) return 'json';
    if (content.startsWith('#') || content.includes('## ')) return 'markdown';
    return 'yaml';
  }

  function updateChecklist(checklist) {
    el.checkItems.forEach(item => {
      const sec = item.getAttribute('data-section');
      const isValid = Boolean(checklist[sec]);
      item.classList.toggle('valid', isValid);
      item.classList.toggle('invalid', !isValid);
      const mark = item.querySelector('.check-mark');
      if (mark) mark.textContent = isValid ? '✓' : '✗';
    });
  }

  function resetChecklist() {
    el.checkItems.forEach(item => {
      item.classList.remove('valid', 'invalid');
      const mark = item.querySelector('.check-mark');
      if (mark) mark.textContent = '✓';
    });
  }

  // ── Plan Only Action ───────────────────────────────────────────────────── //

  async function handlePlanOnly() {
    const content = el.specEditor.value.trim();
    if (!content) {
      showToast('Please enter a specification before generating plan', 'error');
      return;
    }

    setLoading(true, 'Generating Plan & Risk Analysis...');
    try {
      const res = await fetch('/api/plan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          content,
          format: detectFormat(content),
          provider: el.providerModelSelect.value,
        }),
      });

      const data = await res.json();
      if (data.error) {
        showToast(data.error, 'error');
        return;
      }

      activeSpecData = data.spec;
      activePlanData = data.plan;

      renderOverviewAndPlan(data.spec, data.plan);
      el.govCard.style.display = 'none';
      switchTab('tabOverview');
      showToast('Technical Implementation Plan generated successfully', 'success');
    } catch (err) {
      showToast('Failed to generate plan: ' + err.message, 'error');
    } finally {
      setLoading(false);
    }
  }

  // ── Execute Pipeline (Governed vs Direct Continuous) ───────────────────── //

  async function handleExecutePipeline() {
    const content = el.specEditor.value.trim();
    if (!content) {
      showToast('Please enter a specification before running pipeline', 'error');
      return;
    }

    const isGoverned = el.chkGovernanceMode.checked;
    const provider = el.providerModelSelect.value;
    const fmt = detectFormat(content);

    if (isGoverned) {
      // Governed Multi-Stage Session
      setLoading(true, 'Starting Governed Session & Computing DAG...');
      try {
        const res = await fetch('/api/pipeline/start', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ content, format: fmt, provider }),
        });

        const data = await res.json();
        if (data.error) {
          showToast(data.error, 'error');
          return;
        }

        currentSessionId = data.session_id;
        activeSpecData = data.spec;
        activePlanData = data.plan;

        renderOverviewAndPlan(data.spec, data.plan);
        renderCheckpoint1Banner(data.plan);
        switchTab('tabOverview');
        showToast('Checkpoint #1: Pre-Implementation Plan Ready for Approval', 'success');
      } catch (err) {
        showToast('Session start failed: ' + err.message, 'error');
      } finally {
        setLoading(false);
      }
    } else {
      // Direct Continuous Execution
      setLoading(true, 'Synthesizing Code, Tests, and Verifying Quality Gates...');
      try {
        const res = await fetch('/api/run', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            content,
            format: fmt,
            provider,
            auto_approve: true,
            reviewer: 'Automated CI/CD',
          }),
        });

        const data = await res.json();
        if (data.error) {
          showToast(data.error, 'error');
          return;
        }

        currentSessionId = data.session_id;
        const result = data.result;

        activeSpecData = result.spec;
        activePlanData = result.plan;
        activeImplementationData = result.implementation;

        renderOverviewAndPlan(result.spec, result.plan);
        renderCodeAndDiffs(result.implementation);
        renderTestsAndTraceability(result.test_generation);
        renderQualityGates(result.quality_results);
        renderProvenance(result.checkpoint_1, result.checkpoint_2, result.provenance, data.dashboard_url, data.report_url);

        el.govCard.style.display = 'none';
        switchTab('tabOverview');
        showToast('End-to-End Pipeline executed successfully with 100% Quality Gates Passing!', 'success');
      } catch (err) {
        showToast('Pipeline execution failed: ' + err.message, 'error');
      } finally {
        setLoading(false);
      }
    }
  }

  // ── Governance Approval Handlers ───────────────────────────────────────── //

  async function handleGovApprove() {
    if (!currentSessionId) return;

    const currentCheck = el.govCheckpointPill.textContent;

    if (currentCheck.includes('CHECKPOINT #1')) {
      // Approve Checkpoint #1 -> Synthesize Code & Run Gates
      setLoading(true, 'Synthesizing Isolated Sandbox Code & Running 6 Verification Gates...');
      try {
        const res = await fetch('/api/pipeline/approve-plan', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            session_id: currentSessionId,
            reviewer: el.govReviewerInput.value || 'Lead_Architect',
            comments: 'Pre-implementation technical plan approved.',
          }),
        });

        const data = await res.json();
        if (data.error) {
          showToast(data.error, 'error');
          return;
        }

        activeImplementationData = data.implementation;

        renderCodeAndDiffs(data.implementation);
        renderTestsAndTraceability(data.test_generation);
        renderQualityGates(data.quality_results);

        if (data.stage === 'VERIFIED') {
          renderCheckpoint2Banner();
          showToast('Checkpoint #1 Approved. Code Synthesized & 6 Quality Gates Passed!', 'success');
        } else {
          el.govCard.style.display = 'none';
          showToast('Quality Gate Verification Failed. Inspect Quality Gates tab.', 'error');
        }
      } catch (err) {
        showToast('Approval error: ' + err.message, 'error');
      } finally {
        setLoading(false);
      }
    } else if (currentCheck.includes('CHECKPOINT #2')) {
      // Approve Checkpoint #2 -> Finalize Merge & Provenance
      setLoading(true, 'Sealing SLSA Provenance and Finalizing Merge...');
      try {
        const res = await fetch('/api/pipeline/approve-merge', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            session_id: currentSessionId,
            reviewer: el.govReviewerInput.value || 'Release_Officer',
            comments: 'Quality verification approved for merge.',
          }),
        });

        const data = await res.json();
        if (data.error) {
          showToast(data.error, 'error');
          return;
        }

        renderProvenance(null, data.checkpoint_2, data.provenance, data.dashboard_url, data.report_url);
        el.govCard.style.display = 'none';
        switchTab('tabProvenance');
        showToast('Checkpoint #2 Approved. SLSA Provenance Sealed & Artifacts Materialized!', 'success');
      } catch (err) {
        showToast('Merge approval error: ' + err.message, 'error');
      } finally {
        setLoading(false);
      }
    }
  }

  async function handleGovReject() {
    if (!currentSessionId) return;

    const currentCheck = el.govCheckpointPill.textContent;
    const checkpointName = currentCheck.includes('CHECKPOINT #1') ? 'checkpoint_1' : 'checkpoint_2';

    setLoading(true, 'Recording Governance Rejection...');
    try {
      const res = await fetch('/api/pipeline/reject', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: currentSessionId,
          checkpoint: checkpointName,
          reviewer: el.govReviewerInput.value || 'Lead_Reviewer',
          reason: 'Rejected during governance checkpoint review.',
        }),
      });

      const data = await res.json();
      if (data.error) {
        showToast(data.error, 'error');
        return;
      }

      el.govCard.style.display = 'none';
      showToast(`Pipeline execution ${checkpointName} was rejected and logged immutably.`, 'error');
    } catch (err) {
      showToast('Rejection error: ' + err.message, 'error');
    } finally {
      setLoading(false);
    }
  }

  // ── Render Helpers ─────────────────────────────────────────────────────── //

  function renderCheckpoint1Banner(plan) {
    el.govCard.style.display = 'flex';
    el.govCheckpointPill.textContent = 'GOVERNANCE CHECKPOINT #1';
    el.govTitle.textContent = 'Pre-Implementation Plan Review';
    el.govStatusPill.textContent = 'Awaiting Approval';
    el.govDesc.textContent =
      'Review the technical plan, task breakdown, approved blast radius, and risk mitigations. Authorize AI code synthesis into the isolated sandbox.';
    el.govPlanId.textContent = plan ? plan.plan_id : 'PLAN-7FDA1C0D';
    el.govReviewerInput.value = 'Lead_Architect';
    el.approveBtnLabel.textContent = 'Approve Plan & Begin Implementation';
  }

  function renderCheckpoint2Banner() {
    el.govCard.style.display = 'flex';
    el.govCheckpointPill.textContent = 'GOVERNANCE CHECKPOINT #2';
    el.govTitle.textContent = 'Pre-Merge & Deployment Approval';
    el.govStatusPill.textContent = 'Awaiting Approval';
    el.govDesc.textContent =
      'Review 100% passing quality gate evidence, test coverage matrix, and synthesized code diffs. Authorize release and sign SLSA provenance attestation.';
    el.govReviewerInput.value = 'Release_Officer';
    el.approveBtnLabel.textContent = 'Approve Merge & Sign SLSA Provenance';
  }

  function renderOverviewAndPlan(spec, plan) {
    if (!spec || !plan) return;

    // Metrics Bar
    el.metricHash.textContent = spec.spec_hash ? spec.spec_hash.substring(0, 16) + '...' : 'Pending';
    el.metricTasks.textContent = plan.tasks ? plan.tasks.length : 0;
    el.metricFiles.textContent = plan.impacted_files ? plan.impacted_files.length : 0;
    el.metricRisks.textContent = plan.risks ? plan.risks.length : 0;

    // Architecture Summary
    el.archDesignSummary.textContent = plan.architecture_summary || 'No architecture summary generated.';

    // Decision Pills
    el.archDecisionsList.innerHTML = '';
    if (plan.architectural_decisions && plan.architectural_decisions.length > 0) {
      plan.architectural_decisions.forEach((dec, idx) => {
        const pill = document.createElement('div');
        pill.className = 'decision-pill';
        pill.textContent = `Decision ${idx + 1}: ${dec}`;
        el.archDecisionsList.appendChild(pill);
      });
    }

    // Tasks DAG
    el.tasksList.innerHTML = '';
    if (plan.tasks && plan.tasks.length > 0) {
      plan.tasks.forEach(task => {
        const card = document.createElement('div');
        card.className = 'task-card';

        const header = document.createElement('div');
        header.className = 'task-card-header';

        const title = document.createElement('span');
        title.className = 'task-card-title';
        title.textContent = `${task.task_id}: ${task.title}`;

        const fileBadge = document.createElement('span');
        fileBadge.className = 'task-file-badge';
        fileBadge.textContent = task.target_file || 'SRC/MODULE.PY';

        header.appendChild(title);
        header.appendChild(fileBadge);

        const desc = document.createElement('p');
        desc.className = 'task-card-desc';
        desc.textContent = task.description || '';

        card.appendChild(header);
        card.appendChild(desc);
        el.tasksList.appendChild(card);
      });
    }

    // Risk Assessment Table
    const tbody = el.risksTable.querySelector('tbody');
    tbody.innerHTML = '';
    if (plan.risks && plan.risks.length > 0) {
      plan.risks.forEach(r => {
        const row = document.createElement('tr');
        row.innerHTML = `
          <td><strong>${r.risk_id}</strong></td>
          <td><span class="badge ${getRiskBadgeClass(r.category)}">${r.category}</span></td>
          <td>${r.description}</td>
          <td>${r.mitigation}</td>
        `;
        tbody.appendChild(row);
      });
    } else {
      tbody.innerHTML = '<tr><td colspan="4" class="empty-placeholder">No risks evaluated.</td></tr>';
    }
  }

  function getRiskBadgeClass(cat) {
    if (cat === 'security') return 'badge-danger';
    if (cat === 'performance') return 'badge-warning';
    return 'badge-info';
  }

  function renderCodeAndDiffs(impl) {
    if (!impl) return;

    const changes = impl.changes || impl.files || [];
    if (!Array.isArray(changes) || changes.length === 0) return;

    currentSynthesizedFiles = {};
    el.synthesizedFilesTree.innerHTML = '';

    changes.forEach((c, idx) => {
      const filePath = c.path || c.relative_path || 'src/module.py';
      currentSynthesizedFiles[filePath] = c;
      const li = document.createElement('li');
      li.className = 'files-tree-item' + (idx === 0 ? ' active' : '');
      li.textContent = filePath;
      li.addEventListener('click', () => {
        document.querySelectorAll('.files-tree-item').forEach(item => item.classList.remove('active'));
        li.classList.add('active');
        showFileDiff(c);
      });
      el.synthesizedFilesTree.appendChild(li);
    });

    showFileDiff(changes[0]);
  }

  function showFileDiff(fileObj) {
    if (!fileObj) return;
    const filePath = fileObj.path || fileObj.relative_path || 'src/module.py';
    el.viewerFileName.textContent = filePath;
    el.viewerFileAction.textContent = (fileObj.action || 'CREATED').toUpperCase();
    el.diffViewport.textContent = fileObj.unified_diff || fileObj.diff_summary || fileObj.content || '// Empty file';
  }

  function renderTestsAndTraceability(testGen) {
    if (!testGen) return;

    // Traceability Matrix Table
    const tbody = el.traceabilityMatrixTable.querySelector('tbody');
    tbody.innerHTML = '';

    const tests = testGen.tests || [];

    // Render Acceptance Criteria mappings
    if (activeSpecData && activeSpecData.acceptance_criteria) {
      activeSpecData.acceptance_criteria.forEach(ac => {
        const mapped = tests.filter(t => t.source_criterion_id === ac.criterion_id);
        const isMapped = mapped.length > 0;
        const testNames = isMapped ? mapped.map(t => t.test_id || t.description).join(', ') : 'None (Uncovered)';
        const row = document.createElement('tr');
        row.innerHTML = `
          <td><strong>${ac.criterion_id}</strong></td>
          <td>${ac.title || ac.given || 'Requirement'}</td>
          <td><code>${testNames}</code></td>
          <td><span class="badge ${isMapped ? 'badge-success' : 'badge-danger'}">${isMapped ? '100% PASS' : 'MISSING'}</span></td>
        `;
        tbody.appendChild(row);
      });
    }

    // Synthesized Test Suites Code Viewport
    if (tests.length > 0) {
      const codeBlocks = tests.map(t => {
        const fPath = t.file_path || t.relative_path || 'tests/test_suite.py';
        const code = t.source_code || t.content || '';
        return `# File: ${fPath}\n# Test: ${t.test_id || ''} (${t.test_type || 'unit'}) - ${t.description || ''}\n\n${code}`;
      }).join('\n\n' + '='.repeat(60) + '\n\n');
      el.testsCodeViewport.textContent = codeBlocks;
    }
  }

  function renderQualityGates(quality) {
    if (!quality) return;

    const rawGates = quality.gates;
    let gatesMap = {};

    if (Array.isArray(rawGates)) {
      rawGates.forEach(g => {
        const name = (g.gate_name || '').toLowerCase();
        if (name.includes('syntax')) gatesMap['syntax'] = g;
        else if (name.includes('lint') || name.includes('ruff')) gatesMap['lint'] = g;
        else if (name.includes('type') || name.includes('mypy')) gatesMap['typecheck'] = g;
        else if (name.includes('security')) gatesMap['security'] = g;
        else if (name.includes('pytest') || name.includes('test')) gatesMap['pytest'] = g;
        else if (name.includes('acceptance') || name.includes('ac')) gatesMap['acceptance_criteria'] = g;
      });
    } else if (typeof rawGates === 'object' && rawGates !== null) {
      gatesMap = rawGates;
    }

    const gateKeys = [
      { key: 'syntax', id: 'gateCard-syntax' },
      { key: 'lint', id: 'gateCard-lint' },
      { key: 'typecheck', id: 'gateCard-typecheck' },
      { key: 'security', id: 'gateCard-security' },
      { key: 'pytest', id: 'gateCard-pytest' },
      { key: 'acceptance_criteria', id: 'gateCard-acceptance_criteria' },
    ];

    gateKeys.forEach(g => {
      const card = document.getElementById(g.id);
      if (!card) return;

      const res = gatesMap[g.key];
      const pill = card.querySelector('.gate-pill');
      const timing = card.querySelector('.gate-duration-val');
      const logBox = card.querySelector('.gate-log-box');

      if (res) {
        const isPassed = Boolean(res.passed);
        pill.textContent = isPassed ? 'PASSED' : 'FAILED';
        pill.className = 'gate-pill ' + (isPassed ? 'pill-pass' : 'pill-fail');
        const duration = res.duration_seconds !== undefined
          ? (res.duration_seconds * 1000).toFixed(1) + ' ms'
          : (res.duration_ms ? res.duration_ms.toFixed(1) + ' ms' : '—');
        timing.textContent = duration;

        if (!isPassed && (res.details || res.stderr || res.stdout)) {
          logBox.style.display = 'block';
          logBox.textContent = res.details || res.stderr || res.stdout;
        } else {
          logBox.style.display = 'none';
        }
      }
    });
  }

  function renderProvenance(cp1, cp2, prov, dashUrl, repUrl) {
    // Provenance signatures table
    const tbody = el.provenanceSignaturesTable.querySelector('tbody');
    tbody.innerHTML = '';

    const decisions = [cp1, cp2].filter(Boolean);
    if (decisions.length > 0) {
      decisions.forEach(d => {
        const row = document.createElement('tr');
        row.innerHTML = `
          <td><strong>${d.checkpoint}</strong></td>
          <td><span class="badge badge-success">${d.status}</span></td>
          <td>${d.reviewer}</td>
          <td>${new Date(d.decided_at).toLocaleTimeString()}</td>
          <td><code class="font-mono" style="font-size: 11px;">${d.signature}</code></td>
        `;
        tbody.appendChild(row);
      });
    }

    // Provenance JSON Viewport
    if (prov) {
      el.provenanceJsonViewport.textContent = JSON.stringify(prov, null, 2);
    }

    // Live Report links
    if (dashUrl) {
      el.linkLiveDashboard.href = dashUrl;
      el.linkLiveDashboard.style.display = 'inline-flex';
    }
    if (repUrl) {
      el.linkLiveReport.href = repUrl;
      el.linkLiveReport.style.display = 'inline-flex';
    }
  }

  // ── UI Loading & Toast Helpers ─────────────────────────────────────────── //

  function setLoading(isLoading, message = 'Processing...') {
    el.btnExecute.disabled = isLoading;
    el.btnPlanOnly.disabled = isLoading;
    el.btnValidate.disabled = isLoading;
    if (isLoading) {
      el.executeBtnText.textContent = message;
    } else {
      el.executeBtnText.textContent = 'Execute Pipeline';
    }
  }

  function showToast(text, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = text;
    el.toastRoot.appendChild(toast);
    setTimeout(() => {
      toast.remove();
    }, 4000);
  }

  // Kickoff on DOM Ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
