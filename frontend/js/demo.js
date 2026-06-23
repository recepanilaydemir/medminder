/**
 * =============================================================================
 * MedMinder — Interactive Demo Mode
 * =============================================================================
 *
 * A guided walkthrough that showcases MedMinder's capabilities without
 * needing a real API key or backend connection.
 *
 * Features demonstrated:
 *   1. Adding a medication (with safety validation)
 *   2. Dashboard / schedule view
 *   3. Drug interaction check
 *   4. Symptom logging
 *   5. Notification reminders
 *
 * Uses typewriter effect for messages and auto-navigation between views.
 *
 * @module demo
 */

'use strict';

// ─── Demo State ──────────────────────────────────────────────────

let _demoActive = false;
let _demoStep = 0;
let _demoCancelled = false;
let _demoOverlay = null;

// ─── Demo Script ─────────────────────────────────────────────────

/**
 * Each step in the demo script.
 * @typedef {Object} DemoStep
 * @property {'narrate'|'user'|'agent'|'navigate'|'action'|'pause'|'toast'|'reminder'} type
 * @property {string} [text] - Message text or narration
 * @property {string} [view] - View to navigate to
 * @property {Function} [fn] - Action function to run
 * @property {number} [delay] - Delay before this step (ms)
 * @property {Array} [trace] - Fake trace for agent messages
 */
const DEMO_SCRIPT = [
  // ── Introduction ──
  {
    type: 'narrate',
    text: '👋 Welcome to the MedMinder demo! I\'ll walk you through the key features. You can exit anytime by clicking the ✕ button.',
    delay: 800,
  },

  // ── Step 1: Add a medication ──
  {
    type: 'narrate',
    text: '💊 **Step 1:** Let\'s add a medication. Watch how MedMinder validates it against the FDA database for safety.',
    delay: 2000,
  },
  {
    type: 'user',
    text: 'Add Lisinopril 10mg once daily at 8:00 AM',
    delay: 1500,
  },
  {
    type: 'agent',
    text: '🔍 I\'ll add Lisinopril for you. Let me first check it against the FDA database...\n\n✅ **FDA Verification Complete**\n• Drug: Lisinopril (ACE inhibitor)\n• Standard dosage range: 5-40mg daily\n• Your dose (10mg): ✅ Within safe range\n\n💊 **Medication Added Successfully:**\n• **Lisinopril** — 10mg\n• Frequency: Once daily\n• Scheduled: 08:00 AM\n\n⚠️ *Disclaimer: Always follow your prescriber\'s instructions. This is for informational purposes only.*',
    delay: 2500,
    trace: [
      { type: 'text', author: 'Orchestrator', text_preview: 'Routing to ScheduleAgent for medication management' },
      { type: 'tool_call', author: 'ScheduleAgent', tool_name: 'add_medication', tool_args: { name: 'Lisinopril', dosage: '10mg', frequency: 'once daily', times: ['08:00'] }, mcp_server: 'MedMinder MCP Server' },
      { type: 'tool_call', author: 'ScheduleAgent', tool_name: 'lookup_drug_info', tool_args: { drug_name: 'Lisinopril' }, mcp_server: 'MedMinder MCP → openFDA API' },
      { type: 'tool_response', author: 'ScheduleAgent', tool_name: 'lookup_drug_info', result_preview: 'Found: Lisinopril, ACE inhibitor, 5-40mg range' },
      { type: 'tool_response', author: 'ScheduleAgent', tool_name: 'add_medication', result_preview: 'Medication added: Lisinopril 10mg, times: [08:00]' },
      { type: 'text', author: 'ScheduleAgent', text_preview: 'Medication added with FDA safety check' },
    ],
  },

  // ── Step 2: Add another medication ──
  {
    type: 'user',
    text: 'Also add Metformin 500mg twice daily at 8:00 AM and 8:00 PM',
    delay: 2000,
  },
  {
    type: 'agent',
    text: '✅ **Metformin Added Successfully:**\n• **Metformin** — 500mg\n• Frequency: Twice daily\n• Scheduled: 08:00 AM, 08:00 PM\n\n📋 You now have 2 active medications. I\'ll remind you when it\'s time for each dose!',
    delay: 2000,
    trace: [
      { type: 'tool_call', author: 'ScheduleAgent', tool_name: 'add_medication', tool_args: { name: 'Metformin', dosage: '500mg', frequency: 'twice daily', times: ['08:00', '20:00'] }, mcp_server: 'MedMinder MCP Server' },
      { type: 'tool_call', author: 'ScheduleAgent', tool_name: 'lookup_drug_info', tool_args: { drug_name: 'Metformin' }, mcp_server: 'MedMinder MCP → openFDA API' },
      { type: 'tool_response', author: 'ScheduleAgent', tool_name: 'add_medication', result_preview: 'Medication added: Metformin 500mg' },
    ],
  },

  // ── Step 3: Navigate to Dashboard ──
  {
    type: 'narrate',
    text: '📊 **Step 2:** Let\'s check the Dashboard to see your schedule and adherence stats.',
    delay: 2500,
  },
  {
    type: 'navigate',
    view: 'dashboard',
    delay: 800,
  },
  {
    type: 'action',
    delay: 600,
    fn: () => {
      // Populate dashboard with demo data
      const statsContainer = document.getElementById('adherence-stats');
      const timelineContainer = document.getElementById('today-timeline');

      if (statsContainer) {
        statsContainer.innerHTML =
          renderAdherenceStat('Today', '1/3', 33) +
          renderAdherenceStat('Medications', '2', 100) +
          renderAdherenceStat('This Week', '18/21', 86);
        staggeredReveal('adherence-stats', 80);
      }

      if (timelineContainer) {
        timelineContainer.innerHTML =
          renderScheduleItem({ time: '08:00', medication: 'Lisinopril', dosage: '10mg', status: 'taken' }) +
          renderScheduleItem({ time: '08:00', medication: 'Metformin', dosage: '500mg', status: 'taken' }) +
          renderScheduleItem({ time: '20:00', medication: 'Metformin', dosage: '500mg', status: 'upcoming' });
        staggeredReveal('today-timeline', 60);
      }
    },
  },
  {
    type: 'toast',
    text: 'Dashboard loaded with your schedule',
    toastType: 'success',
    delay: 1200,
  },

  // ── Step 4: Show Medications View ──
  {
    type: 'narrate',
    text: '💊 **Step 3:** Here\'s your Medications view — all your active medications in one place.',
    delay: 3000,
  },
  {
    type: 'navigate',
    view: 'medications',
    delay: 800,
  },
  {
    type: 'action',
    delay: 600,
    fn: () => {
      const container = document.getElementById('medications-list');
      if (container) {
        container.innerHTML =
          renderMedicationCard({ id: 'demo-1', name: 'Lisinopril', dosage: '10mg', frequency: 'Once daily', times: ['08:00'], active: true }) +
          renderMedicationCard({ id: 'demo-2', name: 'Metformin', dosage: '500mg', frequency: 'Twice daily', times: ['08:00', '20:00'], active: true });
        staggeredReveal('medications-list', 100);
      }
    },
  },

  // ── Step 5: Drug Interaction Check ──
  {
    type: 'narrate',
    text: '⚠️ **Step 4:** Let\'s check for drug interactions — a critical safety feature.',
    delay: 3000,
  },
  {
    type: 'navigate',
    view: 'chat',
    delay: 800,
  },
  {
    type: 'user',
    text: 'Can you check if Lisinopril and Metformin have any interactions?',
    delay: 1500,
  },
  {
    type: 'agent',
    text: '🔍 Checking drug interactions between **Lisinopril** and **Metformin**...\n\n⚠️ **Potential Interaction Found:**\n• Severity: **Moderate**\n• Description: ACE inhibitors like Lisinopril may enhance the hypoglycemic effect of Metformin. Monitor blood glucose levels more frequently.\n• Recommendation: This is a commonly prescribed combination, but inform your doctor so they can monitor your levels.\n\n📚 *Sources: DDInter database, PubMed clinical references*\n\n⚠️ *Always consult your healthcare provider about drug interactions.*',
    delay: 3000,
    trace: [
      { type: 'text', author: 'Orchestrator', text_preview: 'Routing to InteractionAgent for drug interaction check' },
      { type: 'tool_call', author: 'InteractionAgent', tool_name: 'search_drug_interactions', tool_args: { drug1: 'Lisinopril', drug2: 'Metformin' }, mcp_server: 'BioMCP (DDInter/PubMed)' },
      { type: 'tool_response', author: 'InteractionAgent', tool_name: 'search_drug_interactions', result_preview: 'Moderate interaction: enhanced hypoglycemic effect' },
      { type: 'tool_call', author: 'InteractionAgent', tool_name: 'check_interaction', tool_args: { drugs: ['Lisinopril', 'Metformin'] }, mcp_server: 'drug-interaction-mcp' },
      { type: 'tool_response', author: 'InteractionAgent', tool_name: 'check_interaction', result_preview: 'Confirmed: moderate interaction' },
    ],
  },

  // ── Step 6: Symptom Logging ──
  {
    type: 'narrate',
    text: '📝 **Step 5:** MedMinder can also track your symptoms and correlate them with your medications.',
    delay: 3000,
  },
  {
    type: 'user',
    text: 'I\'ve been experiencing mild dizziness after taking Lisinopril this morning',
    delay: 1500,
  },
  {
    type: 'agent',
    text: '📝 **Symptom Logged:**\n• Symptom: Dizziness\n• Severity: Mild (2/5)\n• Related medication: Lisinopril\n• Time: This morning\n\n💡 **Note:** Dizziness is a known side effect of Lisinopril (ACE inhibitor), especially during the first few weeks or after dose changes. This is typically mild and improves over time.\n\n🔔 If the dizziness is severe, persistent, or accompanied by fainting, please contact your healthcare provider immediately.\n\n⚠️ *This is informational only. Consult your doctor about any concerning side effects.*',
    delay: 2800,
    trace: [
      { type: 'text', author: 'Orchestrator', text_preview: 'Routing to HealthAgent for symptom tracking' },
      { type: 'tool_call', author: 'HealthAgent', tool_name: 'log_symptom', tool_args: { name: 'Dizziness', severity: 2, notes: 'After taking Lisinopril', medication_id: 'demo-1' }, mcp_server: 'MedMinder MCP Server' },
      { type: 'tool_response', author: 'HealthAgent', tool_name: 'log_symptom', result_preview: 'Symptom logged: Dizziness, severity 2/5' },
    ],
  },

  // ── Step 7: Show Reminder Notification ──
  {
    type: 'narrate',
    text: '🔔 **Step 6:** MedMinder sends you timely reminders. Here\'s what a notification looks like:',
    delay: 3000,
  },
  {
    type: 'action',
    delay: 1000,
    fn: () => {
      // Show a demo reminder banner
      if (typeof _showReminderBanner === 'function') {
        _showReminderBanner(
          { medication_id: 'demo-2', medication_name: 'Metformin', dosage: '500mg', scheduled_times: ['20:00'] },
          '20:00'
        );
      }
    },
  },
  {
    type: 'toast',
    text: '💊 Reminder: Metformin 500mg is due!',
    toastType: 'info',
    delay: 1500,
  },

  // ── Conclusion ──
  {
    type: 'narrate',
    text: '🎉 **That\'s the tour!** MedMinder combines AI-powered medication management with real safety checks via MCP (Model Context Protocol).\n\nKey features you saw:\n• 🔒 FDA drug validation on every add\n• ⚠️ Drug interaction checking (BioMCP + DDInter)\n• 📊 Real-time adherence dashboard\n• 🔔 Smart medication reminders\n• 📝 Symptom tracking & correlation\n• 📡 Full MCP tracing transparency\n\nTo use MedMinder with your own data, close this demo and enter your Gemini API key. Thanks for watching! 🙌',
    delay: 4000,
  },
];

// ─── Demo Controller ─────────────────────────────────────────────

/**
 * Start the interactive demo mode.
 * Enters the main app view and plays through the demo script.
 */
async function startDemo() {
  _demoActive = true;
  _demoStep = 0;
  _demoCancelled = false;

  // Enter the main app without an API key
  showMainApp();

  // Stop real notification engine (no backend)
  if (typeof stopNotifications === 'function') {
    stopNotifications();
  }

  // Clear any existing chat
  document.getElementById('chat-messages').innerHTML = '';
  state.messages = [];

  // Add the demo overlay with exit button
  _createDemoOverlay();

  // Disable the real send button during demo
  const sendBtn = document.getElementById('send-btn');
  if (sendBtn) sendBtn.disabled = true;
  const chatInput = document.getElementById('chat-input');
  if (chatInput) {
    chatInput.disabled = true;
    chatInput.placeholder = '🎬 Demo mode — watching the walkthrough...';
  }

  // Play through each step
  for (let i = 0; i < DEMO_SCRIPT.length; i++) {
    if (_demoCancelled) break;
    _demoStep = i;
    await _executeDemoStep(DEMO_SCRIPT[i]);
  }

  // Demo complete — show exit option
  if (!_demoCancelled) {
    _showDemoComplete();
  }
}

/**
 * Stop and clean up demo mode.
 */
function stopDemo() {
  _demoCancelled = true;
  _demoActive = false;

  // Remove demo overlay
  if (_demoOverlay) {
    _demoOverlay.remove();
    _demoOverlay = null;
  }

  // Remove any demo narration bubbles
  document.querySelectorAll('.demo-narration').forEach(el => el.remove());

  // Remove any demo reminder banners
  const reminderContainer = document.getElementById('reminder-container');
  if (reminderContainer) reminderContainer.innerHTML = '';

  // Re-enable inputs
  const sendBtn = document.getElementById('send-btn');
  if (sendBtn) sendBtn.disabled = false;
  const chatInput = document.getElementById('chat-input');
  if (chatInput) {
    chatInput.disabled = false;
    chatInput.placeholder = 'Ask MedMinder anything…';
  }

  // Go back to setup screen
  showSetupScreen();
  showToast('Demo ended. Enter your API key to use MedMinder.', 'info');
}

// ─── Step Execution ──────────────────────────────────────────────

/**
 * Execute a single demo step.
 * @param {DemoStep} step
 */
async function _executeDemoStep(step) {
  // Wait for the step's delay
  if (step.delay) {
    await _demoSleep(step.delay);
  }

  if (_demoCancelled) return;

  switch (step.type) {
    case 'narrate':
      _showNarration(step.text);
      break;

    case 'user':
      // Simulate typing into the chat input
      await _simulateUserTyping(step.text);
      addMessage(step.text, true);
      break;

    case 'agent':
      // Show typing indicator, then agent response
      await _simulateAgentResponse(step.text, step.trace);
      break;

    case 'navigate':
      switchView(step.view);
      break;

    case 'action':
      if (step.fn) step.fn();
      break;

    case 'toast':
      if (typeof showToast === 'function') {
        showToast(step.text, step.toastType || 'info');
      }
      break;

    case 'reminder':
      // Handled by the action step that calls _showReminderBanner
      break;
  }
}

/**
 * Sleep helper that can be cancelled.
 * @param {number} ms
 */
function _demoSleep(ms) {
  return new Promise(resolve => {
    const check = setInterval(() => {
      if (_demoCancelled) {
        clearInterval(check);
        resolve();
      }
    }, 50);
    setTimeout(() => {
      clearInterval(check);
      resolve();
    }, ms);
  });
}

// ─── Simulation Helpers ──────────────────────────────────────────

/**
 * Simulate user typing in the chat input with a typewriter effect.
 */
async function _simulateUserTyping(text) {
  const input = document.getElementById('chat-input');
  if (!input) return;

  input.value = '';
  const charsPerTick = 2;
  for (let i = 0; i < text.length; i += charsPerTick) {
    if (_demoCancelled) break;
    input.value = text.substring(0, i + charsPerTick);
    autoResizeTextarea(input);
    await _demoSleep(30);
  }
  input.value = '';
  autoResizeTextarea(input);
}

/**
 * Simulate the agent typing indicator, then display the response.
 */
async function _simulateAgentResponse(text, trace) {
  const container = document.getElementById('chat-messages');
  if (!container) return;

  // Show typing indicator
  container.insertAdjacentHTML('beforeend', renderTypingIndicator());
  scrollChatToBottom();

  // Simulate processing time
  await _demoSleep(1500 + Math.random() * 1000);

  if (_demoCancelled) return;

  // Remove typing indicator and show response
  removeTypingIndicator();
  const messageId = 'demo-msg-' + Date.now();
  container.insertAdjacentHTML('beforeend', renderChatMessage(text, false, trace, messageId));
  scrollChatToBottom();
}

// ─── UI Elements ─────────────────────────────────────────────────

/**
 * Create the persistent demo mode overlay with step counter and exit button.
 */
function _createDemoOverlay() {
  if (_demoOverlay) _demoOverlay.remove();

  _demoOverlay = document.createElement('div');
  _demoOverlay.className = 'demo-overlay';
  _demoOverlay.id = 'demo-overlay';
  _demoOverlay.innerHTML = `
    <div class="demo-badge">
      <span class="demo-badge-dot"></span>
      <span>DEMO MODE</span>
    </div>
    <button class="demo-exit-btn" onclick="stopDemo()" title="Exit demo">
      ✕ Exit Demo
    </button>
  `;
  document.body.appendChild(_demoOverlay);
}

/**
 * Show a narration bubble above the chat.
 */
function _showNarration(text) {
  // Remove any existing narration
  document.querySelectorAll('.demo-narration').forEach(el => el.remove());

  const container = document.getElementById('chat-messages');
  if (!container) return;

  // Convert markdown bold (**text**) to <strong>
  const formatted = escapeHTML(text)
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n/g, '<br>');

  const narration = document.createElement('div');
  narration.className = 'demo-narration';
  narration.innerHTML = `
    <div class="demo-narration-content">
      ${formatted}
    </div>
  `;

  container.appendChild(narration);
  scrollChatToBottom();
}

/**
 * Show the demo completion card with exit option.
 */
function _showDemoComplete() {
  if (_demoOverlay) {
    const badge = _demoOverlay.querySelector('.demo-badge span:last-child');
    if (badge) badge.textContent = 'DEMO COMPLETE';
  }

  // Re-enable chat input with a note
  const chatInput = document.getElementById('chat-input');
  if (chatInput) {
    chatInput.placeholder = '🎬 Demo complete — click "Exit Demo" to start for real';
  }
}
