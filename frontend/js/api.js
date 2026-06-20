/**
 * =============================================================================
 * MedMinder — API Client
 * =============================================================================
 *
 * Lightweight HTTP client that communicates with the MedMinder backend.
 * Handles:
 *  - API key storage (localStorage) and injection (X-API-Key header)
 *  - Chat, medications, schedule, and configuration endpoints
 *  - Graceful error handling with user-friendly messages
 *
 * ⚠️ MEDICAL DISCLAIMER: This software is for informational purposes only.
 * It is not a substitute for professional medical advice.
 *
 * Usage:
 *   The module self-instantiates and attaches to `window.api`.
 *   >>> window.api.chat('What is ibuprofen used for?', sessionId);
 */

'use strict';

class MedMinderAPI {
  // ---- Private Constants ----
  /** @type {string} localStorage key for persisting the API key */
  static LOCAL_STORAGE_KEY = 'medminder_api_key';

  /**
   * Create a new API client.
   * @param {string} baseUrl - Backend root URL (default: '' for same-origin).
   */
  constructor(baseUrl = '') {
    /** @type {string} */
    this.baseUrl = baseUrl.replace(/\/+$/, ''); // strip trailing slashes

    /** @type {string|null} In-memory copy of the API key */
    this._apiKey = this.getApiKey();
  }

  // ===========================================================================
  // Key Management
  // ===========================================================================

  /**
   * Persist an API key to localStorage and cache it in memory.
   * @param {string} key - The Gemini API key.
   */
  setApiKey(key) {
    if (!key || typeof key !== 'string') {
      throw new Error('API key must be a non-empty string.');
    }
    localStorage.setItem(MedMinderAPI.LOCAL_STORAGE_KEY, key.trim());
    this._apiKey = key.trim();
  }

  /**
   * Retrieve the stored API key.
   * @returns {string|null} The stored key, or null if not set.
   */
  getApiKey() {
    return localStorage.getItem(MedMinderAPI.LOCAL_STORAGE_KEY) || null;
  }

  /**
   * Remove the stored API key (logout / reset).
   */
  clearApiKey() {
    localStorage.removeItem(MedMinderAPI.LOCAL_STORAGE_KEY);
    this._apiKey = null;
  }

  /**
   * Check whether an API key is currently stored.
   * @returns {boolean}
   */
  hasApiKey() {
    return !!this._apiKey;
  }

  // ===========================================================================
  // Internal Helpers
  // ===========================================================================

  /**
   * Build default headers, including authentication when available.
   * @returns {HeadersInit}
   * @private
   */
  _headers() {
    const headers = {
      'Content-Type': 'application/json',
      'Accept': 'application/json',
    };
    if (this._apiKey) {
      headers['X-API-Key'] = this._apiKey;
    }
    return headers;
  }

  /**
   * Centralised fetch wrapper with error handling.
   *
   * Design decision: we throw on non-2xx responses so callers can use
   * try/catch without inspecting status codes manually.
   *
   * @param {string}       endpoint - Relative path, e.g. '/api/chat'.
   * @param {RequestInit}  options  - Fetch options (method, body, etc.).
   * @returns {Promise<any>} Parsed JSON response body.
   * @private
   */
  async _request(endpoint, options = {}) {
    const url = `${this.baseUrl}${endpoint}`;

    try {
      const response = await fetch(url, {
        headers: this._headers(),
        ...options,
      });

      // Handle common HTTP error codes with friendly messages
      if (!response.ok) {
        let errorMessage;
        try {
          const errorBody = await response.json();
          errorMessage = errorBody.detail || errorBody.message || errorBody.error || response.statusText;
        } catch {
          errorMessage = response.statusText;
        }

        switch (response.status) {
          case 401:
            throw new Error('Invalid or missing API key. Please check your settings.');
          case 403:
            throw new Error('Access denied. Your API key may not have the required permissions.');
          case 404:
            throw new Error(`Endpoint not found: ${endpoint}. Is the backend running?`);
          case 429:
            throw new Error('Rate limit exceeded. Please wait a moment and try again.');
          case 500:
            throw new Error(`Server error: ${errorMessage}`);
          default:
            throw new Error(`Request failed (${response.status}): ${errorMessage}`);
        }
      }

      // Some endpoints may return 204 No Content
      if (response.status === 204) return null;

      return await response.json();
    } catch (error) {
      // Re-throw API errors as-is; wrap network failures
      if (error instanceof TypeError && error.message.includes('fetch')) {
        throw new Error(
          'Unable to reach the MedMinder server. Please ensure the backend is running.'
        );
      }
      throw error;
    }
  }

  // ===========================================================================
  // API Endpoints
  // ===========================================================================

  /**
   * Send a chat message to the AI agent.
   *
   * @param {string} message   - The user's message text.
   * @param {string} sessionId - A unique session identifier for conversation continuity.
   * @returns {Promise<{response: string, session_id: string}>}
   */
  async chat(message, sessionId) {
    if (!message || !message.trim()) {
      throw new Error('Message cannot be empty.');
    }

    return this._request('/api/chat', {
      method: 'POST',
      body: JSON.stringify({
        message: message.trim(),
        session_id: sessionId,
      }),
    });
  }

  /**
   * Check the current backend configuration status.
   * Useful for verifying the API key is valid on startup.
   *
   * @returns {Promise<{configured: boolean, model: string}>}
   */
  async checkConfig() {
    return this._request('/api/config', { method: 'GET' });
  }

  /**
   * Send or update the backend configuration (primarily the Gemini API key).
   *
   * @param {string} apiKey - The Gemini API key to configure on the server.
   * @returns {Promise<{status: string}>}
   */
  async setConfig(apiKey) {
    return this._request('/api/config', {
      method: 'POST',
      body: JSON.stringify({ api_key: apiKey }),
    });
  }

  /**
   * Retrieve the user's medication list.
   *
   * @returns {Promise<Array<{id: string, name: string, dosage: string, frequency: string, times: string[], active: boolean}>>}
   */
  async getMedications() {
    return this._request('/api/medications', { method: 'GET' });
  }

  /**
   * Add a new medication.
   *
   * @param {Object} medication - Medication details.
   * @param {string} medication.name
   * @param {string} medication.dosage
   * @param {string} medication.frequency
   * @param {string[]} medication.times
   * @returns {Promise<{id: string, status: string}>}
   */
  async addMedication(medication) {
    return this._request('/api/medications', {
      method: 'POST',
      body: JSON.stringify(medication),
    });
  }

  /**
   * Fetch today's medication schedule.
   *
   * @returns {Promise<Array<{time: string, medication: string, status: string}>>}
   */
  async getTodaySchedule() {
    return this._request('/api/schedule/today', { method: 'GET' });
  }

  /**
   * Retrieve symptom and dose history.
   *
   * @param {string} [type='all'] - Filter by 'symptoms', 'doses', or 'all'.
   * @returns {Promise<Array>}
   */
  async getHistory(type = 'all') {
    return this._request(`/api/history?type=${encodeURIComponent(type)}`, {
      method: 'GET',
    });
  }

  /**
   * Log a symptom entry.
   *
   * @param {Object} symptom
   * @param {string} symptom.description
   * @param {string} symptom.severity - One of: safe, minor, moderate, major, critical.
   * @returns {Promise<{id: string, status: string}>}
   */
  async logSymptom(symptom) {
    return this._request('/api/symptoms', {
      method: 'POST',
      body: JSON.stringify(symptom),
    });
  }

  /**
   * Log a dose taken.
   *
   * @param {Object} dose
   * @param {string} dose.medication_id
   * @param {string} dose.taken_at - ISO 8601 timestamp.
   * @returns {Promise<{status: string}>}
   */
  async logDose(dose) {
    return this._request('/api/doses', {
      method: 'POST',
      body: JSON.stringify(dose),
    });
  }
}

// =============================================================================
// Module Export — instantiate and attach to global scope
// =============================================================================
window.api = new MedMinderAPI();
