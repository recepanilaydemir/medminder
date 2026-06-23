/**
 * =============================================================================
 * MedMinder — Main Application Controller
 * =============================================================================
 *
 * Orchestrates the single-page application:
 *  • Setup flow (API key configuration)
 *  • View routing (Chat, Dashboard, Medications, History)
 *  • Chat messaging with typing indicator
 *  • Dashboard & medication data loading
 *  • Event binding for all interactive elements
 *
 * Dependencies: api.js (window.api), components.js (global render functions)
 *
 * ⚠️ MEDICAL DISCLAIMER: This application is for informational purposes only.
 * It is not a substitute for professional medical advice, diagnosis, or treatment.
 * Always consult your physician or pharmacist.
 */

'use strict';

// =============================================================================
// Application State
// =============================================================================

const state = {
  /** @type {'chat'|'dashboard'|'medications'|'history'} Current active view */
  currentView: 'chat',

  /** @type {Array<{text: string, isUser: boolean, timestamp: string}>} Chat message history */
  messages: [],

  /** @type {Array<Object>} Cached medication list */
  medications: [],

  /** @type {string|null} Current session ID for chat continuity */
  sessionId: null,

  /** @type {boolean} Whether the agent is currently responding */
  isTyping: false,

  /** @type {'symptoms'|'doses'} Active history sub-tab */
  historyTab: 'symptoms',
};

// =============================================================================
// Constants
// =============================================================================

/** Welcome message displayed when the chat view first loads */
const WELCOME_MESSAGE = `Hello! 👋 I'm MedMinder, your AI medication assistant.

I can help you with:
• 💊 Medication information & interactions
• ⏰ Dose scheduling & reminders
• 📝 Symptom logging & severity assessment
• 📊 Adherence tracking

How can I help you today?

⚠️ Remember: I provide general information only. Always consult your healthcare provider for medical decisions.`;

// =============================================================================
// Initialisation
// =============================================================================

/**
 * Application entry point — runs when the DOM is fully loaded.
 *
 * Checks for a stored API key:
 *  - If found → show main app, load initial data
 *  - If not   → show setup screen
 */
function init() {
  // Generate or restore a session ID for chat continuity
  state.sessionId = loadOrCreateSessionId();

  if (window.api.hasApiKey()) {
    showMainApp();
  } else {
    showSetupScreen();
  }

  // Bind all event listeners
  bindEvents();
}

// =============================================================================
// Setup Flow
// =============================================================================

/** Show the setup screen and hide the main app. */
function showSetupScreen() {
  document.getElementById('setup-screen').style.display = '';
  document.getElementById('main-app').style.display = 'none';
}

/** Show the main app, hide setup, and load initial data. */
function showMainApp() {
  document.getElementById('setup-screen').style.display = 'none';
  document.getElementById('main-app').style.display = '';

  // Show welcome message if chat is empty
  if (state.messages.length === 0) {
    addMessage(WELCOME_MESSAGE, false);
  }

  // Pre-load data for the current view
  onViewActivated(state.currentView);

  // Start the medication reminder notification engine
  if (typeof initNotifications === 'function') {
    initNotifications();
  }
}

/**
 * Handle API key submission from the setup form.
 * Validates the key by calling the backend config endpoint.
 *
 * @param {Event} e - Form submit event.
 */
async function setupApiKey(e) {
  e.preventDefault();

  const input = document.getElementById('setup-api-key');
  const btn = document.getElementById('setup-connect-btn');
  const key = input.value.trim();

  if (!key) {
    showToast('Please enter a valid API key.', 'warning');
    return;
  }

  // Disable the button to prevent double-submission
  btn.disabled = true;
  btn.textContent = '⏳ Connecting…';

  try {
    // Store the key and attempt to configure the backend
    window.api.setApiKey(key);
    await window.api.setConfig(key);

    showToast('Connected successfully!', 'success');
    showMainApp();
  } catch (error) {
    // If config fails, still let them proceed — the backend may not be running yet
    // but the key is stored for when it starts
    console.warn('Config endpoint not reachable; proceeding with stored key:', error.message);
    showToast('Key saved. Backend may not be running yet.', 'warning');
    showMainApp();
  } finally {
    btn.disabled = false;
    btn.textContent = '🔗 Connect & Start';
  }
}

// =============================================================================
// View Routing
// =============================================================================

/**
 * Switch the visible view and update sidebar navigation state.
 *
 * @param {string} viewName - One of: chat, dashboard, medications, history
 */
function switchView(viewName) {
  if (viewName === state.currentView) return;

  state.currentView = viewName;

  // Toggle view sections
  document.querySelectorAll('.view').forEach(section => {
    section.classList.toggle('active', section.id === `view-${viewName}`);
  });

  // Update sidebar active state
  document.querySelectorAll('.nav-item[data-view]').forEach(item => {
    const isActive = item.dataset.view === viewName;
    item.classList.toggle('active', isActive);
    if (isActive) {
      item.setAttribute('aria-current', 'page');
    } else {
      item.removeAttribute('aria-current');
    }
  });

  // Load data for the newly activated view
  onViewActivated(viewName);
}

/**
 * Called whenever a view becomes active — loads its data.
 *
 * @param {string} viewName
 */
function onViewActivated(viewName) {
  switch (viewName) {
    case 'dashboard':
      loadDashboard();
      break;
    case 'medications':
      loadMedications();
      break;
    case 'history':
      loadHistory();
      break;
    // Chat: no additional loading needed (messages are in state)
  }
}

// =============================================================================
// Chat
// =============================================================================

/**
 * Add a message to state and render it in the chat UI.
 *
 * @param {string}  text   - Message content.
 * @param {boolean} isUser - True for user messages.
 * @param {Array|null} trace - Optional agent trace events for transparency.
 */
function addMessage(text, isUser, trace = null) {
  state.messages.push({
    text,
    isUser,
    timestamp: new Date().toISOString(),
  });

  const container = document.getElementById('chat-messages');
  const messageId = 'msg-' + Date.now() + '-' + Math.random().toString(36).substr(2, 5);
  container.insertAdjacentHTML('beforeend', renderChatMessage(text, isUser, trace, messageId));
  scrollChatToBottom();
}

/**
 * Send the user's chat message to the API and display the response.
 */
async function sendMessage() {
  const input = document.getElementById('chat-input');
  const text = input.value.trim();

  if (!text || state.isTyping) return;

  // Clear input and add user message
  input.value = '';
  autoResizeTextarea(input);
  addMessage(text, true);

  // Show typing indicator
  state.isTyping = true;
  const container = document.getElementById('chat-messages');
  container.insertAdjacentHTML('beforeend', renderTypingIndicator());
  scrollChatToBottom();

  try {
    const response = await window.api.chat(text, state.sessionId);

    // Remove typing indicator
    removeTypingIndicator();

    // Display agent response
    const agentText = response.response || response.message || 'I received your message but had no response.';
    addMessage(agentText, false, response.trace || null);

    // Update session ID if the server provides one
    if (response.session_id) {
      state.sessionId = response.session_id;
    }
  } catch (error) {
    removeTypingIndicator();
    addMessage(`Sorry, I encountered an error: ${error.message}`, false);
    showToast(error.message, 'error');
  } finally {
    state.isTyping = false;
  }
}

/** Remove the typing indicator from the chat DOM. */
function removeTypingIndicator() {
  const indicator = document.getElementById('typing-indicator');
  if (indicator) indicator.remove();
}

/** Smoothly scroll the chat container to the bottom. */
function scrollChatToBottom() {
  const container = document.getElementById('chat-messages');
  // Use requestAnimationFrame for smoother scroll after DOM update
  requestAnimationFrame(() => {
    container.scrollTop = container.scrollHeight;
  });
}

/** Start a fresh chat conversation. */
function newChat() {
  state.messages = [];
  state.sessionId = generateSessionId();
  document.getElementById('chat-messages').innerHTML = '';
  addMessage(WELCOME_MESSAGE, false);
  showToast('New conversation started.', 'info');
}

// =============================================================================
// Dashboard
// =============================================================================

/**
 * Load today's schedule and adherence stats into the dashboard view.
 */
async function loadDashboard() {
  const statsContainer = document.getElementById('adherence-stats');
  const timelineContainer = document.getElementById('today-timeline');

  // Show loading skeletons
  statsContainer.innerHTML = renderSkeletonCards(3);
  timelineContainer.innerHTML = renderSkeletonCards(2);

  try {
    // Fetch schedule — API returns {schedule: [...], count, date}
    const response = await window.api.getTodaySchedule();
    const scheduleData = response.schedule || response || [];

    if (scheduleData.length > 0) {
      // Map API format to what renderScheduleItem expects.
      // API returns: {medication_name, dosage, scheduled_times, doses_logged_today, all_taken}
      // Component expects: {time, medication, dosage, status}
      const timelineItems = [];
      scheduleData.forEach(med => {
        (med.scheduled_times || []).forEach(t => {
          timelineItems.push({
            time: t,
            medication: med.medication_name || med.name || 'Unknown',
            dosage: med.dosage || '',
            status: med.all_taken ? 'taken' : (med.doses_logged_today > 0 ? 'upcoming' : 'upcoming'),
          });
        });
      });

      // Sort by time
      timelineItems.sort((a, b) => a.time.localeCompare(b.time));

      timelineContainer.innerHTML = timelineItems
        .map(item => renderScheduleItem(item))
        .join('');

      // Calculate adherence from schedule data
      const totalDoses = scheduleData.reduce((s, m) => s + (m.total_doses_today || 0), 0);
      const loggedDoses = scheduleData.reduce((s, m) => s + (m.doses_logged_today || 0), 0);
      const pct = totalDoses > 0 ? Math.round((loggedDoses / totalDoses) * 100) : 0;

      statsContainer.innerHTML =
        renderAdherenceStat('Today', `${loggedDoses}/${totalDoses}`, pct) +
        renderAdherenceStat('Medications', `${scheduleData.length}`, 100) +
        renderAdherenceStat('This Month', '—', 0);
    } else {
      timelineContainer.innerHTML = renderEmptyState('📅', 'No doses scheduled for today. Add medications to get started.');
      statsContainer.innerHTML = renderEmptyState('📈', 'Adherence data will appear once you start tracking.');
    }
  } catch (error) {
    console.error('Failed to load dashboard:', error);
    timelineContainer.innerHTML = renderEmptyState('⚠️', 'Could not load schedule. Is the backend running?');
    statsContainer.innerHTML = '';
    showToast('Failed to load dashboard data.', 'error');
  }
}

// =============================================================================
// Medications
// =============================================================================

/**
 * Fetch and render the medication list.
 */
async function loadMedications() {
  const container = document.getElementById('medications-list');
  container.innerHTML = renderSkeletonCards(3);

  try {
    // API returns {medications: [...], count, user_id}
    const response = await window.api.getMedications();
    state.medications = response.medications || response || [];

    if (state.medications.length > 0) {
      container.innerHTML = state.medications
        .map(med => renderMedicationCard(med))
        .join('');
    } else {
      container.innerHTML = renderEmptyState(
        '💊',
        'No medications added yet. Chat with MedMinder to add your first medication!'
      );
    }
  } catch (error) {
    console.error('Failed to load medications:', error);
    container.innerHTML = renderEmptyState('⚠️', 'Could not load medications. Is the backend running?');
    showToast('Failed to load medications.', 'error');
  }
}

// =============================================================================
// History
// =============================================================================

/**
 * Load symptom or dose history based on the active tab.
 */
async function loadHistory() {
  const container = document.getElementById('history-list');
  container.innerHTML = renderSkeletonCards(3);

  try {
    // The /api/history endpoint may not exist yet —
    // fall back to showing a friendly empty state.
    let history = [];
    try {
      const response = await window.api.getHistory(state.historyTab);
      history = response.history || response.symptoms || response.doses || response || [];
    } catch {
      // Endpoint doesn't exist yet — show empty state instead of error
      history = [];
    }

    if (Array.isArray(history) && history.length > 0) {
      if (state.historyTab === 'symptoms') {
        container.innerHTML = history
          .map(s => renderSymptomEntry(s))
          .join('');
      } else {
        container.innerHTML = history
          .map(d => renderDoseEntry(d))
          .join('');
      }
    } else {
      const icon = state.historyTab === 'symptoms' ? '📝' : '💊';
      const msg = state.historyTab === 'symptoms'
        ? 'No symptoms logged yet. Use the chat to report symptoms.'
        : 'No doses recorded yet. Start tracking to see your history.';
      container.innerHTML = renderEmptyState(icon, msg);
    }
  } catch (error) {
    console.error('Failed to load history:', error);
    container.innerHTML = renderEmptyState('⚠️', 'Could not load history. Is the backend running?');
    showToast('Failed to load history.', 'error');
  }
}

/**
 * Switch the active history sub-tab (symptoms vs doses).
 *
 * @param {string} tab - 'symptoms' or 'doses'
 */
function switchHistoryTab(tab) {
  state.historyTab = tab;

  // Update tab button styles
  document.getElementById('tab-symptoms').className =
    `btn ${tab === 'symptoms' ? 'btn-primary' : 'btn-ghost'} btn-sm`;
  document.getElementById('tab-doses').className =
    `btn ${tab === 'doses' ? 'btn-primary' : 'btn-ghost'} btn-sm`;

  loadHistory();
}

// =============================================================================
// Event Binding
// =============================================================================

/**
 * Bind all DOM event listeners.
 * Called once during init().
 */
function bindEvents() {
  // ---- Setup form ----
  const setupForm = document.getElementById('setup-form');
  if (setupForm) {
    setupForm.addEventListener('submit', setupApiKey);
  }

  // ---- Sidebar navigation ----
  document.querySelectorAll('.nav-item[data-view]').forEach(item => {
    item.addEventListener('click', (e) => {
      e.preventDefault();
      switchView(item.dataset.view);
    });
  });

  // ---- Chat: Send button ----
  const sendBtn = document.getElementById('send-btn');
  if (sendBtn) {
    sendBtn.addEventListener('click', sendMessage);
  }

  // ---- Chat: Keyboard shortcuts ----
  const chatInput = document.getElementById('chat-input');
  if (chatInput) {
    chatInput.addEventListener('keydown', (e) => {
      // Enter sends; Shift+Enter inserts newline
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
      }
    });

    // Auto-resize textarea as user types
    chatInput.addEventListener('input', () => autoResizeTextarea(chatInput));
  }

  // ---- Chat: New conversation button ----
  const newChatBtn = document.getElementById('btn-new-chat');
  if (newChatBtn) {
    newChatBtn.addEventListener('click', newChat);
  }

  // ---- Dashboard: Refresh ----
  const refreshBtn = document.getElementById('btn-refresh-dashboard');
  if (refreshBtn) {
    refreshBtn.addEventListener('click', loadDashboard);
  }

  // ---- Dashboard: Quick actions ----
  const logDoseBtn = document.getElementById('btn-log-dose');
  if (logDoseBtn) {
    logDoseBtn.addEventListener('click', () => {
      switchView('chat');
      const input = document.getElementById('chat-input');
      input.value = 'I just took my medication.';
      input.focus();
    });
  }

  const logSymptomBtn = document.getElementById('btn-log-symptom');
  if (logSymptomBtn) {
    logSymptomBtn.addEventListener('click', () => {
      switchView('chat');
      const input = document.getElementById('chat-input');
      input.value = 'I want to log a symptom.';
      input.focus();
    });
  }

  const checkInteractionBtn = document.getElementById('btn-check-interaction');
  if (checkInteractionBtn) {
    checkInteractionBtn.addEventListener('click', () => {
      switchView('chat');
      const input = document.getElementById('chat-input');
      input.value = 'Can you check for drug interactions?';
      input.focus();
    });
  }

  // ---- Medications: Add button ----
  const addMedBtn = document.getElementById('btn-add-medication');
  if (addMedBtn) {
    addMedBtn.addEventListener('click', () => {
      switchView('chat');
      const input = document.getElementById('chat-input');
      input.value = 'I want to add a new medication.';
      input.focus();
    });
  }

  // ---- History: Tab switching ----
  const tabSymptoms = document.getElementById('tab-symptoms');
  const tabDoses = document.getElementById('tab-doses');
  if (tabSymptoms) tabSymptoms.addEventListener('click', () => switchHistoryTab('symptoms'));
  if (tabDoses)    tabDoses.addEventListener('click', () => switchHistoryTab('doses'));

  // ---- Settings nav (reset API key) ----
  const settingsBtn = document.getElementById('nav-settings');
  if (settingsBtn) {
    settingsBtn.addEventListener('click', () => {
      if (confirm('Reset your API key? You will need to re-enter it.')) {
        window.api.clearApiKey();
        state.messages = [];
        showToast('API key cleared.', 'info');
        showSetupScreen();
      }
    });
  }
}

// =============================================================================
// Utility Functions
// =============================================================================

/**
 * Toggle visibility of an agent trace panel.
 * @param {string} messageId - The message ID to toggle.
 */
function toggleTrace(messageId) {
  const panel = document.getElementById('trace-' + messageId);
  const toggle = panel?.previousElementSibling;
  if (panel) {
    panel.classList.toggle('visible');
    const isVisible = panel.classList.contains('visible');
    if (toggle) {
      toggle.classList.toggle('active', isVisible);
      toggle.setAttribute('aria-expanded', isVisible);
    }
  }
}

/**
 * Generate a UUID v4-like session ID for chat continuity.
 * Not cryptographically secure, but sufficient for session tracking.
 *
 * @returns {string} e.g. "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
 */
function generateSessionId() {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

/**
 * Load an existing session ID from sessionStorage, or create a new one.
 *
 * Design decision: we use sessionStorage (not localStorage) so each browser
 * tab gets its own conversation thread. If the user reloads the page within
 * the same tab, the conversation continues.
 *
 * @returns {string}
 */
function loadOrCreateSessionId() {
  const KEY = 'medminder_session_id';
  let id = sessionStorage.getItem(KEY);
  if (!id) {
    id = generateSessionId();
    sessionStorage.setItem(KEY, id);
  }
  return id;
}

/**
 * Auto-resize a textarea to fit its content, up to a max height.
 *
 * @param {HTMLTextAreaElement} el
 */
function autoResizeTextarea(el) {
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 140) + 'px';
}

// =============================================================================
// Bootstrap
// =============================================================================

document.addEventListener('DOMContentLoaded', init);
