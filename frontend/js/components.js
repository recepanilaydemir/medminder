/**
 * =============================================================================
 * MedMinder — Reusable UI Components
 * =============================================================================
 *
 * Pure rendering functions that return HTML strings via template literals.
 * No direct DOM manipulation — the caller decides where to inject the markup.
 *
 * Design philosophy:
 *  • Each function is self-contained and produces accessible HTML.
 *  • Severity levels map to medical triage colours.
 *  • All user-facing text should include disclaimers where appropriate.
 *
 * ⚠️ MEDICAL DISCLAIMER: This software is for informational purposes only.
 * It is not a substitute for professional medical advice.
 */

'use strict';

// =============================================================================
// 1. Chat Messages
// =============================================================================

/**
 * Render a single chat message bubble.
 *
 * Agent messages are wrapped with an avatar; user messages float to the right.
 *
 * @param {string}  text   - The message body (plain text; HTML is escaped).
 * @param {boolean} isUser - True for user messages, false for agent messages.
 * @returns {string} HTML string.
 */
function renderChatMessage(text, isUser = false, trace = null, messageId = null) {
  // Basic HTML escaping to prevent XSS in user-supplied content
  const escaped = escapeHTML(text);

  // Convert newlines to <br> for readable multi-line messages
  const formatted = escaped.replace(/\n/g, '<br>');

  if (isUser) {
    return `
      <div class="message message-user">
        ${formatted}
      </div>`;
  }

  // Build the optional trace panel HTML for agent messages
  const traceHtml = (trace && trace.length > 0)
    ? renderTracePanel(trace, messageId || ('msg-' + Date.now()))
    : '';

  // Agent messages include a small bot avatar
  return `
    <div class="message-agent-wrapper">
      <div class="agent-avatar" aria-hidden="true">🤖</div>
      <div class="message message-agent">
        ${formatted}
        ${traceHtml}
      </div>
    </div>`;
}

/**
 * Render the agent trace/log panel for an agent message.
 * Shows which sub-agent handled the request, what tools were called,
 * and what MCP servers responded.
 *
 * @param {Array<Object>} trace - Array of trace events from the server.
 * @param {string} messageId - Unique ID to link toggle with panel.
 * @returns {string} HTML string.
 */
function renderTracePanel(trace, messageId) {
  if (!trace || trace.length === 0) {
    return '';
  }

  // Build the trace steps HTML
  const stepsHtml = trace.map((event, i) => {
    const type = event.type || 'text';
    const author = escapeHTML(event.author || 'unknown');
    let icon, label, detail;

    switch (type) {
      case 'tool_call':
        icon = '🔧';
        label = `Tool Call: ${escapeHTML(event.tool_name || 'unknown')}`;
        detail = event.tool_args
          ? Object.entries(event.tool_args)
              .map(([k, v]) => `${escapeHTML(k)}: ${escapeHTML(String(v))}`)
              .join(', ')
          : '';
        break;
      case 'tool_response':
        icon = '✅';
        label = `Tool Result: ${escapeHTML(event.tool_name || 'unknown')}`;
        detail = event.result_preview ? escapeHTML(event.result_preview).substring(0, 200) : 'OK';
        break;
      case 'text':
        icon = '💬';
        label = `Response from ${author}`;
        detail = event.text_preview ? escapeHTML(event.text_preview) : '';
        break;
      default:
        icon = '📎';
        label = `Event: ${type}`;
        detail = '';
    }

    // Determine if this is a routing event (author differs from previous)
    const isRouting = i > 0 && event.author !== trace[i - 1].author && type === 'text';
    const stepType = isRouting ? 'routing' : type;
    const stepIcon = isRouting ? '🔀' : icon;
    const stepLabel = isRouting ? `Routed to ${author}` : label;

    // MCP server source badge (only for tool calls and responses)
    const mcpSource = event.mcp_server
      ? `<div class="trace-mcp-source">📡 via ${escapeHTML(event.mcp_server)}</div>`
      : '';

    return `
      <div class="trace-step trace-step--${stepType}">
        <div class="trace-step-header">
          <span>${stepIcon}</span>
          <span class="trace-badge trace-badge--${stepType}">${stepType.replace('_', ' ')}</span>
          <span>${stepLabel}</span>
        </div>
        ${mcpSource}
        ${detail ? `<div class="trace-step-detail">${detail}</div>` : ''}
      </div>
    `;
  }).join('');

  // Count tool calls for the toggle summary
  const toolCalls = trace.filter(e => e.type === 'tool_call').length;
  const agents = [...new Set(trace.map(e => e.author).filter(a => a && a !== 'unknown'))];
  const summary = [];
  if (agents.length > 0) summary.push(`${agents.length} agent${agents.length > 1 ? 's' : ''}`);
  if (toolCalls > 0) summary.push(`${toolCalls} tool${toolCalls > 1 ? 's' : ''}`);
  const summaryText = summary.length > 0 ? summary.join(' · ') : 'No tools used';

  return `
    <button class="message-trace-toggle" data-trace-toggle="${messageId}" aria-expanded="false" aria-controls="trace-${messageId}">
      <span class="trace-icon">ℹ️</span>
      <span>${summaryText} · ${trace.length} steps</span>
    </button>
    <div class="message-trace" id="trace-${messageId}">
      <div style="margin-bottom:8px;color:var(--text-muted);font-weight:600;">🔍 Agent Reasoning Trace</div>
      ${stepsHtml}
    </div>
  `;
}

// =============================================================================
// 2. Typing Indicator
// =============================================================================

/**
 * Render the animated "agent is typing…" indicator.
 * Three dots bounce in sequence via CSS @keyframes typing.
 *
 * @returns {string} HTML string.
 */
function renderTypingIndicator() {
  return `
    <div class="message-agent-wrapper" id="typing-indicator">
      <div class="agent-avatar" aria-hidden="true">🤖</div>
      <div class="message message-agent typing-indicator" aria-label="MedMinder is typing">
        <span class="dot"></span>
        <span class="dot"></span>
        <span class="dot"></span>
      </div>
    </div>`;
}

// =============================================================================
// 3. Medication Card
// =============================================================================

/**
 * Render a medication card with name, dosage, frequency, scheduled times,
 * and an active/inactive badge.
 *
 * @param {Object}   medication
 * @param {string}   medication.id
 * @param {string}   medication.name       - e.g. "Lisinopril"
 * @param {string}   medication.dosage     - e.g. "10 mg"
 * @param {string}   medication.frequency  - e.g. "Once daily"
 * @param {string[]} medication.times      - e.g. ["08:00", "20:00"]
 * @param {boolean}  medication.active     - Whether the medication is currently active.
 * @returns {string} HTML string.
 */
function renderMedicationCard(medication) {
  const { id, name, dosage, frequency, times = [], active = true } = medication;

  const statusBadge = active
    ? '<span class="badge badge-active">Active</span>'
    : '<span class="badge badge-inactive">Inactive</span>';

  const timeChips = times
    .map(t => `<span class="medication-time-chip">${escapeHTML(t)}</span>`)
    .join('');

  return `
    <div class="card card-medication" data-medication-id="${escapeHTML(id || '')}">
      <div class="card-header">
        <span class="medication-name">${escapeHTML(name)}</span>
        ${statusBadge}
      </div>
      <div class="medication-detail">${escapeHTML(dosage)} · ${escapeHTML(frequency)}</div>
      ${times.length ? `<div class="medication-times">${timeChips}</div>` : ''}
    </div>`;
}

// =============================================================================
// 4. Schedule Timeline Item
// =============================================================================

/**
 * Render a single entry in the daily medication timeline.
 *
 * @param {Object} item
 * @param {string} item.time       - e.g. "08:00 AM"
 * @param {string} item.medication - Medication name.
 * @param {string} item.dosage     - e.g. "10 mg"
 * @param {string} item.status     - 'taken' | 'upcoming' | 'missed'
 * @returns {string} HTML string.
 */
function renderScheduleItem(item) {
  const { time, medication, dosage = '', status = 'upcoming' } = item;

  // Map status to icon
  const statusIcons = {
    taken:    '✅',
    upcoming: '⏳',
    missed:   '❌',
  };
  const icon = statusIcons[status] || '⏳';

  return `
    <div class="timeline-item ${escapeHTML(status)}">
      <span class="timeline-time">${escapeHTML(time)}</span>
      <div class="timeline-card">
        <div class="flex items-center justify-between">
          <div>
            <div class="font-semibold">${escapeHTML(medication)}</div>
            ${dosage ? `<div class="text-sm text-muted">${escapeHTML(dosage)}</div>` : ''}
          </div>
          <span class="timeline-status-icon" aria-label="${status}">${icon}</span>
        </div>
      </div>
    </div>`;
}

// =============================================================================
// 5. Adherence Stat Card
// =============================================================================

/**
 * Render an adherence stat card with a circular progress ring.
 *
 * The ring uses CSS conic-gradient driven by the --progress custom property.
 *
 * @param {string} label      - e.g. "Weekly Adherence"
 * @param {string} value      - Display value, e.g. "42/45"
 * @param {number} percentage - 0–100 for the circular progress.
 * @returns {string} HTML string.
 */
function renderAdherenceStat(label, value, percentage) {
  const clampedPct = Math.max(0, Math.min(100, percentage));

  return `
    <div class="stat-card">
      <div class="circular-progress" style="--progress: ${clampedPct}">
        <span class="progress-text">${clampedPct}%</span>
      </div>
      <div class="stat-value">${escapeHTML(String(value))}</div>
      <div class="stat-label">${escapeHTML(label)}</div>
    </div>`;
}

// =============================================================================
// 6. Severity Badge
// =============================================================================

/**
 * Render a coloured severity badge.
 *
 * Severity levels follow a medical triage-inspired scale:
 *   safe → minor → moderate → major → critical
 *
 * @param {string} severity - One of: safe, minor, moderate, major, critical.
 * @returns {string} HTML string for the badge.
 */
function renderSeverityBadge(severity) {
  const normalised = (severity || 'safe').toLowerCase().trim();

  // Label mapping (capitalised for display)
  const labels = {
    safe:     'Safe',
    minor:    'Minor',
    moderate: 'Moderate',
    major:    'Major',
    critical: 'Critical',
  };

  const label = labels[normalised] || 'Unknown';
  const cssClass = `badge-${normalised}`;

  return `<span class="badge ${cssClass}">${label}</span>`;
}

// =============================================================================
// 7. Symptom Entry
// =============================================================================

/**
 * Render a symptom log entry with severity badge, description, and date.
 *
 * @param {Object} symptom
 * @param {string} symptom.description
 * @param {string} symptom.severity  - safe | minor | moderate | major | critical
 * @param {string} symptom.date      - ISO date or human-readable string.
 * @returns {string} HTML string.
 */
function renderSymptomEntry(symptom) {
  const { description, severity = 'safe', date = '' } = symptom;

  return `
    <div class="symptom-entry card-symptom">
      <div class="symptom-date">${escapeHTML(formatDate(date))}</div>
      <div class="symptom-description">
        ${escapeHTML(description)}
      </div>
      ${renderSeverityBadge(severity)}
    </div>`;
}

// =============================================================================
// 8. Toast Notifications
// =============================================================================

/**
 * Show a toast notification that slides in from the top-right
 * and auto-dismisses after ~3 seconds.
 *
 * @param {string} message - Notification text.
 * @param {'success'|'error'|'warning'|'info'} [type='info'] - Toast style.
 */
function showToast(message, type = 'info') {
  const container = document.getElementById('toast-container');
  if (!container) return;

  // Map types to leading icons
  const icons = {
    success: '✅',
    error:   '❌',
    warning: '⚠️',
    info:    'ℹ️',
  };

  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `<span aria-hidden="true">${icons[type] || ''}</span> ${escapeHTML(message)}`;
  container.appendChild(toast);

  // Auto-dismiss after 3 seconds with exit animation
  setTimeout(() => {
    toast.classList.add('toast-dismiss');
    // Remove from DOM after the slide-out animation finishes
    toast.addEventListener('animationend', () => toast.remove());
  }, 3000);
}

// =============================================================================
// 9. Empty State
// =============================================================================

/**
 * Render a friendly empty state with a large icon and explanatory text.
 *
 * @param {string} icon    - Emoji or icon character.
 * @param {string} message - Explanatory message.
 * @returns {string} HTML string.
 */
function renderEmptyState(icon, message) {
  return `
    <div class="empty-state">
      <div class="empty-state-icon" aria-hidden="true">${icon}</div>
      <p class="empty-state-text">${escapeHTML(message)}</p>
    </div>`;
}

// =============================================================================
// 10. Skeleton Loading Placeholders
// =============================================================================

/**
 * Render skeleton loading placeholders for a card list.
 *
 * @param {number} [count=3] - Number of skeleton cards to render.
 * @returns {string} HTML string.
 */
function renderSkeletonCards(count = 3) {
  let html = '';
  for (let i = 0; i < count; i++) {
    html += `
      <div class="card">
        <div class="skeleton skeleton-text" style="width:60%"></div>
        <div class="skeleton skeleton-text" style="width:40%"></div>
        <div class="skeleton skeleton-text" style="width:80%"></div>
      </div>`;
  }
  return html;
}

// =============================================================================
// 11. Dose History Entry
// =============================================================================

/**
 * Render a dose history entry.
 *
 * @param {Object} dose
 * @param {string} dose.medication - Medication name.
 * @param {string} dose.dosage     - e.g. "10 mg"
 * @param {string} dose.taken_at   - ISO timestamp.
 * @returns {string} HTML string.
 */
function renderDoseEntry(dose) {
  const { medication, dosage = '', taken_at = '' } = dose;

  return `
    <div class="symptom-entry" style="border-left: 3px solid var(--success);">
      <div class="symptom-date">${escapeHTML(formatDate(taken_at))}</div>
      <div class="symptom-description">
        <span class="font-semibold">${escapeHTML(medication)}</span>
        ${dosage ? `<span class="text-muted"> · ${escapeHTML(dosage)}</span>` : ''}
      </div>
      <span class="badge badge-safe">Taken</span>
    </div>`;
}

// =============================================================================
// Utility Helpers
// =============================================================================

/**
 * Escape HTML special characters to prevent XSS.
 * @param {string} str
 * @returns {string}
 */
function escapeHTML(str) {
  if (!str) return '';
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

/**
 * Format an ISO date string into a human-readable short date.
 * Falls back to the original string if parsing fails.
 *
 * @param {string} dateStr - ISO 8601 date string.
 * @returns {string} Formatted date, e.g. "Jun 20, 2026".
 */
function formatDate(dateStr) {
  if (!dateStr) return '—';
  try {
    const d = new Date(dateStr);
    if (isNaN(d.getTime())) return dateStr;
    return d.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  } catch {
    return dateStr;
  }
}

/**
 * Format an ISO date string into a human-readable time.
 *
 * @param {string} dateStr - ISO 8601 date string.
 * @returns {string} Formatted time, e.g. "08:30 AM".
 */
function formatTime(dateStr) {
  if (!dateStr) return '—';
  try {
    const d = new Date(dateStr);
    if (isNaN(d.getTime())) return dateStr;
    return d.toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return dateStr;
  }
}
