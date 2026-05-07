function formatDuration(ms) {
  if (ms === undefined || ms === null || Number.isNaN(Number(ms))) return "—";
  const value = Number(ms);
  if (value >= 1000) return `${(value / 1000).toFixed(2)}s`;
  return `${Math.round(value)}ms`;
}

function formatCount(value) {
  if (value === undefined || value === null) return "—";
  return String(value);
}

function metricRow(label, value) {
  return `
    <div class="metric-row">
      <span class="metric-label">${escapeHtml(label)}</span>
      <span class="metric-value">${escapeHtml(value)}</span>
    </div>
  `;
}

function modelCallRows(modelCalls = []) {
  if (!modelCalls.length) return "";

  return `
    <div class="metric-subsection">
      ${modelCalls.map((call) => `
        <div class="metric-call">
          <span>Turn ${escapeHtml(formatCount(call.turn))}</span>
          <span>TTFT ${escapeHtml(formatDuration(call.ttft_ms))}</span>
          <span>Total ${escapeHtml(formatDuration(call.model_total_ms ?? call.model_elapsed_ms))}</span>
        </div>
      `).join("")}
    </div>
  `;
}

function renderRuntimeMetrics(metrics = {}) {
  const root = document.getElementById("runtime-metrics");
  if (!root) return;

  const request = metrics.current_request || metrics.last_request || {};
  const modelCalls = request.model_calls || [];
  const firstCall = modelCalls[0] || {};
  const requestDuration = request.request_total_ms ?? request.request_elapsed_ms;
  const baseline = metrics.baseline || {};
  const baselineStatus = baseline.status === "error"
    ? baseline.error
    : `TTFT ${formatDuration(baseline.baseline_ttft_ms)} · Total ${formatDuration(baseline.baseline_total_ms)}`;

  root.innerHTML = `
    <div class="metrics-card">
      ${metricRow("Request", formatDuration(requestDuration))}
      ${metricRow("TTFT", formatDuration(firstCall.ttft_ms))}
      ${metricRow("Model calls", formatCount(modelCalls.length || request.auto_turns))}
      ${metricRow("Tool calls", formatCount(request.tool_call_count))}
      ${metricRow("Prompt", `${formatCount(request.estimated_prompt_chars)} chars`)}
      ${metricRow("Context refs", `${formatCount(request.context_reference_count)} · saved ${formatCount(request.context_reference_saved_chars)} chars`)}
      ${metricRow("System", `${formatCount(request.estimated_system_prompt_chars)} chars`)}
      ${modelCallRows(modelCalls)}
    </div>
    <div class="metrics-card">
      <div class="metric-header">
        <span>Baseline</span>
        <button id="measure-baseline-button" class="runtime-small-button" type="button">Measure</button>
      </div>
      <div class="metric-muted">${escapeHtml(baseline.status ? baselineStatus : "Not measured")}</div>
    </div>
  `;
}

async function measureBaselineMetrics() {
  const button = document.getElementById("measure-baseline-button");
  if (button) {
    button.disabled = true;
    button.textContent = "Measuring";
  }

  try {
    const response = await fetch("/api/metrics/baseline", {
      method: "POST",
      headers: { Accept: "application/json" },
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data.error || `Baseline failed: ${response.status}`);
    }
    await refreshState();
  } catch (error) {
    console.error(error);
    showAppError(error);
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = "Measure";
    }
  }
}
