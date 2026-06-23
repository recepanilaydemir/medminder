/**
 * MedMinder — Medication Reminder Notification Engine
 *
 * Checks the daily schedule every 60 seconds against the current time
 * and triggers notifications when it's time to take a medication.
 *
 * Features:
 *   - Browser push notifications (Notification API)
 *   - In-app reminder banner with Take / Skip actions
 *   - Snooze support (5-minute delay)
 *   - Deduplication (won't re-notify for already-handled doses)
 *   - Graceful degradation (works without notification permission)
 *
 * @module notifications
 */

// ─── State ───────────────────────────────────────────────────────

/** Set of reminder keys already shown this session: "medId:HH:MM" */
const _notifiedDoses = new Set();

/** Interval ID for the schedule checker */
let _checkInterval = null;

/** Whether browser notifications are permitted */
let _browserNotificationsAllowed = false;

// ─── Initialization ──────────────────────────────────────────────

/**
 * Initialize the notification engine.
 * Requests browser notification permission and starts the schedule checker.
 */
function initNotifications() {
  // Request browser notification permission
  if ('Notification' in window) {
    if (Notification.permission === 'granted') {
      _browserNotificationsAllowed = true;
    } else if (Notification.permission !== 'denied') {
      Notification.requestPermission().then(perm => {
        _browserNotificationsAllowed = perm === 'granted';
      });
    }
  }

  // Start checking schedule every 60 seconds
  _checkScheduleNow();
  _checkInterval = setInterval(_checkScheduleNow, 60_000);

  // Inject the reminder banner container into the DOM
  _ensureBannerContainer();

  console.log('[Notifications] Engine initialized. Checking every 60s.');
}

/**
 * Stop the notification engine. Call when navigating away or resetting.
 */
function stopNotifications() {
  if (_checkInterval) {
    clearInterval(_checkInterval);
    _checkInterval = null;
  }
}

// ─── Schedule Checker ────────────────────────────────────────────

/**
 * Fetch today's schedule and check for due medications.
 * @private
 */
async function _checkScheduleNow() {
  try {
    const resp = await fetch('/api/schedule/today');
    if (!resp.ok) return;

    const data = await resp.json();
    const schedule = data.schedule || [];
    const now = new Date();
    const currentHH = String(now.getHours()).padStart(2, '0');
    const currentMM = String(now.getMinutes()).padStart(2, '0');
    const currentTime = `${currentHH}:${currentMM}`;

    for (const med of schedule) {
      if (med.all_taken) continue; // All doses already logged

      for (const scheduledTime of med.scheduled_times) {
        const key = `${med.medication_id}:${scheduledTime}`;

        // Already notified this session
        if (_notifiedDoses.has(key)) continue;

        // Check if it's time (within a 5-minute window)
        if (_isWithinWindow(currentTime, scheduledTime, 5)) {
          _notifiedDoses.add(key);
          _triggerReminder(med, scheduledTime);
        }
      }
    }
  } catch (err) {
    // Silently fail — schedule might not be available yet
    console.debug('[Notifications] Schedule check failed:', err.message);
  }
}

/**
 * Check if current time is within N minutes of the target time.
 * @param {string} current - "HH:MM"
 * @param {string} target  - "HH:MM"
 * @param {number} windowMinutes - tolerance in minutes
 * @returns {boolean}
 * @private
 */
function _isWithinWindow(current, target, windowMinutes) {
  const [cH, cM] = current.split(':').map(Number);
  const [tH, tM] = target.split(':').map(Number);

  const currentTotal = cH * 60 + cM;
  const targetTotal  = tH * 60 + tM;

  const diff = currentTotal - targetTotal;
  // Trigger if within 0 to +windowMinutes (i.e., at or just after the scheduled time)
  return diff >= 0 && diff <= windowMinutes;
}

// ─── Trigger Notifications ───────────────────────────────────────

/**
 * Fire both browser notification and in-app banner for a due medication.
 * @param {object} med - Schedule entry { medication_id, medication_name, dosage, ... }
 * @param {string} time - The scheduled time that triggered this (e.g., "08:00")
 * @private
 */
function _triggerReminder(med, time) {
  console.log(`[Notifications] 💊 Reminder: ${med.medication_name} ${med.dosage} at ${time}`);

  // 1. Browser push notification
  if (_browserNotificationsAllowed) {
    try {
      const notif = new Notification('💊 Time for your medication', {
        body: `${med.medication_name} ${med.dosage} — scheduled at ${time}`,
        icon: 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><text y=".9em" font-size="90">💊</text></svg>',
        tag: `medminder-${med.medication_id}-${time}`,
        requireInteraction: true,
      });

      notif.onclick = () => {
        window.focus();
        notif.close();
      };
    } catch (e) {
      console.debug('[Notifications] Browser notification failed:', e);
    }
  }

  // 2. In-app reminder banner
  _showReminderBanner(med, time);
}

// ─── In-App Reminder Banner ──────────────────────────────────────

/**
 * Ensure the banner container exists in the DOM.
 * @private
 */
function _ensureBannerContainer() {
  if (!document.getElementById('reminder-container')) {
    const container = document.createElement('div');
    container.id = 'reminder-container';
    container.className = 'reminder-container';
    container.setAttribute('aria-live', 'assertive');
    document.body.appendChild(container);
  }
}

/**
 * Show an in-app reminder banner with Take / Skip / Snooze actions.
 * @param {object} med - Medication schedule entry
 * @param {string} time - Scheduled time
 * @private
 */
function _showReminderBanner(med, time) {
  _ensureBannerContainer();
  const container = document.getElementById('reminder-container');

  const banner = document.createElement('div');
  banner.className = 'reminder-banner reminder-banner--enter';
  banner.id = `reminder-${med.medication_id}-${time.replace(':', '')}`;
  banner.innerHTML = `
    <div class="reminder-icon">💊</div>
    <div class="reminder-content">
      <div class="reminder-title">Time for your medication</div>
      <div class="reminder-med">${_escapeHtml(med.medication_name)} — ${_escapeHtml(med.dosage)}</div>
      <div class="reminder-time">Scheduled at ${_escapeHtml(time)}</div>
    </div>
    <div class="reminder-actions">
      <button class="reminder-btn reminder-btn--take" data-action="take"
              data-med-id="${med.medication_id}" data-time="${time}">
        ✅ Take
      </button>
      <button class="reminder-btn reminder-btn--skip" data-action="skip"
              data-med-id="${med.medication_id}" data-time="${time}">
        ⏭ Skip
      </button>
      <button class="reminder-btn reminder-btn--snooze" data-action="snooze"
              data-med-id="${med.medication_id}" data-time="${time}">
        ⏰ 5min
      </button>
    </div>
  `;

  // Attach event listeners
  banner.querySelectorAll('.reminder-btn').forEach(btn => {
    btn.addEventListener('click', (e) => _handleReminderAction(e, banner, med, time));
  });

  container.appendChild(banner);

  // Auto-dismiss after 5 minutes if no action taken
  setTimeout(() => {
    if (banner.parentNode) {
      _dismissBanner(banner);
    }
  }, 5 * 60_000);
}

/**
 * Handle Take / Skip / Snooze button clicks.
 * @private
 */
async function _handleReminderAction(event, banner, med, time) {
  const action = event.currentTarget.dataset.action;

  if (action === 'snooze') {
    // Remove current banner and re-allow notification in 5 minutes
    _dismissBanner(banner);
    const key = `${med.medication_id}:${time}`;
    _notifiedDoses.delete(key);

    setTimeout(() => {
      // The regular checker will pick it up again
      console.log(`[Notifications] Snooze expired for ${med.medication_name}`);
    }, 5 * 60_000);

    if (typeof showToast === 'function') {
      showToast(`Snoozed ${med.medication_name} for 5 minutes`, 'info');
    }
    return;
  }

  // Take or Skip → log the dose
  const status = action === 'take' ? 'taken' : 'missed';

  // Disable buttons while processing
  banner.querySelectorAll('.reminder-btn').forEach(b => b.disabled = true);

  try {
    const resp = await fetch('/api/dose/log', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        medication_id: med.medication_id,
        status: status,
      }),
    });

    if (resp.ok) {
      const label = action === 'take' ? 'Taken' : 'Skipped';
      if (typeof showToast === 'function') {
        showToast(`${label}: ${med.medication_name} ${med.dosage} ✓`, 'success');
      }
    } else {
      if (typeof showToast === 'function') {
        showToast(`Failed to log dose. Please try via chat.`, 'error');
      }
    }
  } catch (err) {
    console.error('[Notifications] Failed to log dose:', err);
    if (typeof showToast === 'function') {
      showToast(`Network error. Dose not logged.`, 'error');
    }
  }

  _dismissBanner(banner);

  // Refresh dashboard if it's currently visible
  if (typeof loadDashboard === 'function' && document.getElementById('view-dashboard')?.classList.contains('active')) {
    loadDashboard();
  }
}

/**
 * Animate out and remove a reminder banner.
 * @private
 */
function _dismissBanner(banner) {
  banner.classList.remove('reminder-banner--enter');
  banner.classList.add('reminder-banner--exit');
  banner.addEventListener('animationend', () => banner.remove());
}

/**
 * Simple HTML escaper for safe rendering.
 * @private
 */
function _escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}
