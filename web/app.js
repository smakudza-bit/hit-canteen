function normalizeApiBaseUrl(value) {
  return String(value || "").trim().replace(/\/+$/, "");
}

const apiMeta = document.querySelector('meta[name="hit-api-base-url"]')?.getAttribute("content") || "";
const api = normalizeApiBaseUrl(window.HIT_API_BASE_URL || apiMeta || localStorage.getItem("hit_api_base_url") || "");

function apiUrl(path) {
  if (/^https?:\/\//i.test(path)) return path;
  return api ? `${api}${path}` : path;
}

let token = localStorage.getItem("hit_token") || "";
let currentUserRole = localStorage.getItem("hit_role") || "";
let cart = JSON.parse(localStorage.getItem("hit_cart") || "[]");
let latestTickets = [];
const AWAY_AUTO_LOGOUT_MS = 60 * 1000;
let awayLogoutTimer = null;
let awayLogoutTicker = null;
let awayLogoutRole = "";
let awaySince = 0;

const demoMeals = [
  { id: 1, name: "Sadza + Beef Stew", price: 2.5, description: "Traditional meal" },
  { id: 2, name: "Rice + Chicken", price: 3.0, description: "Rice with grilled chicken" },
  { id: 3, name: "Veggie Plate", price: 2.2, description: "Healthy vegetarian option" },
  { id: 4, name: "Mazoe Orange", price: 1.1, description: "Fruit drink" },
  { id: 5, name: "Water 500ml", price: 0.8, description: "Still water" },
];

function id(name) { return document.getElementById(name); }
function page() { return document.body.dataset.page; }

function decodeJwtPayload(tokenValue) {
  const raw = String(tokenValue || '').trim();
  if (!raw || !raw.includes('.')) return null;
  try {
    const [, payload] = raw.split('.');
    const normalized = payload.replace(/-/g, '+').replace(/_/g, '/');
    const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, '=');
    return JSON.parse(window.atob(padded));
  } catch {
    return null;
  }
}

function setCurrentUserRole(role) {
  const normalized = normalizePortalTarget(role || '');
  currentUserRole = normalized && ['student', 'staff', 'admin'].includes(normalized) ? normalized : '';
  if (currentUserRole) {
    localStorage.setItem('hit_role', currentUserRole);
  } else {
    localStorage.removeItem('hit_role');
  }
}

function getCurrentUserRole() {
  if (currentUserRole) return normalizePortalTarget(currentUserRole);
  const payload = decodeJwtPayload(token);
  const inferredRole = payload?.role ? normalizePortalTarget(payload.role) : '';
  if (inferredRole) {
    setCurrentUserRole(inferredRole);
    return inferredRole;
  }
  const storedRole = normalizePortalTarget(localStorage.getItem('hit_role') || '');
  if (storedRole) {
    setCurrentUserRole(storedRole);
    return storedRole;
  }
  return '';
}

function showStatus(targetId, message, ok = true) {
  const el = id(targetId);
  if (!el) return;
  el.innerHTML = message || "";
  el.className = ok ? "status-msg success" : "status-msg error";
}

function setButtonBusy(button, busy, busyLabel = "Working...") {
  if (!button) return;
  if (busy) {
    if (!button.dataset.originalLabel) {
      button.dataset.originalLabel = button.textContent;
    }
    button.disabled = true;
    button.classList.add("is-busy");
    button.textContent = busyLabel;
  } else {
    button.disabled = false;
    button.classList.remove("is-busy");
    if (button.dataset.originalLabel) {
      button.textContent = button.dataset.originalLabel;
    }
  }
}


function normalizeUserFacingMessage(message) {
  const text = String(message || "").trim();
  if (!text) return "Request failed";
  if (/status not set\./i.test(text) && /provider response:\s*status=error/i.test(text)) {
    return "Paynow could not start the payment. The merchant integration is being reached, but Paynow is rejecting the request before creating a payment link. Confirm the Paynow merchant account is active and that the integration ID and key are enabled for this endpoint.";
  }
  if (/^status\s+not\s+set\.?$/i.test(text) || /^status:\s*not\s+set\.?$/i.test(text)) {
    if (["staff-scanner", "student-pay-scanner"].includes(page())) {
      return "No valid QR result was returned. Please scan again.";
    }
    return "The operation did not return a final status. Please try again.";
  }
  return text;
}

function flattenErrorPayload(payload) {
  if (!payload) return "Request failed";
  if (typeof payload === "string") return normalizeUserFacingMessage(payload);
  if (payload.detail) return normalizeUserFacingMessage(payload.detail);
  if (payload.message) return normalizeUserFacingMessage(payload.message);
  const parts = [];
  Object.entries(payload).forEach(([key, value]) => {
    if (Array.isArray(value)) {
      parts.push(`${key}: ${value.join(", ")}`);
    } else if (value && typeof value === "object") {
      if (value.message) parts.push(`${key}: ${value.message}`);
      else parts.push(`${key}: ${JSON.stringify(value)}`);
    } else if (value !== undefined && value !== null) {
      parts.push(`${key}: ${value}`);
    }
  });
  return normalizeUserFacingMessage(parts.join(" | ") || "Request failed");
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

async function req(path, method = "GET", body = null, extraHeaders = {}) {
  let response;
  try {
    response = await fetch(apiUrl(path), {
      method,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...extraHeaders,
      },
      body: body ? JSON.stringify(body) : null,
    });
  } catch (fetchError) {
    throw new Error("Unable to reach the server. Restart Django and try again.");
  }
  const rawText = await response.text();
  let data = {};
  try {
    data = rawText ? JSON.parse(rawText) : {};
  } catch {
    data = rawText || {};
  }
  if (!response.ok) {
    const message = flattenErrorPayload(data);
    if (isInvalidTokenMessage(message)) {
      setToken("");
      if (page() === "student" || page() === "staff" || page() === "admin-dashboard" || String(page() || "").startsWith("admin-")) {
        redirectToLogin(normalizePortalTarget(page()));
      }
    }
    const error = new Error(message);
    error.payload = data;
    throw error;
  }
  return data;
}

function normalizePortalTarget(targetPage) {
  const value = String(targetPage || '').toLowerCase();
  if (value.startsWith('staff')) return 'staff';
  if (value.startsWith('admin')) return 'admin';
  return 'student';
}

function portalPath(targetPage) {
  const role = normalizePortalTarget(targetPage);
  if (role === 'staff') return '/staff/';
  if (role === 'admin') return '/admin/';
  return '/student/';
}

function redirectToPortalForRole(role) {
  window.location.replace(portalPath(role || 'student'));
}

function loginPath(targetPage) {
  const role = normalizePortalTarget(targetPage);
  if (role === 'staff') return '/staff-login/';
  if (role === 'admin') return '/admin-login/';
  return '/login/';
}

function awayLogoutKey(targetPage) {
  return `hit_away_since_${normalizePortalTarget(targetPage)}`;
}

function setAwayLogoutNotice(message) {
  if (!message) return;
  sessionStorage.setItem('hit_logout_notice', String(message));
}

function consumeAwayLogoutNotice() {
  const raw = sessionStorage.getItem('hit_logout_notice');
  if (raw) sessionStorage.removeItem('hit_logout_notice');
  return raw || '';
}

function ensureAwayLogoutBanner() {
  let banner = id('hit-away-logout-banner');
  if (banner) return banner;
  banner = document.createElement('div');
  banner.id = 'hit-away-logout-banner';
  banner.className = 'hit-away-logout-banner';
  document.body.appendChild(banner);
  return banner;
}

function hideAwayLogoutBanner() {
  const banner = id('hit-away-logout-banner');
  if (!banner) return;
  banner.classList.remove('is-active');
  banner.textContent = '';
}

function updateAwayLogoutBanner(remainingMs) {
  const banner = ensureAwayLogoutBanner();
  const remaining = Math.max(0, Math.ceil(remainingMs / 1000));
  const minutes = String(Math.floor(remaining / 60)).padStart(1, '0');
  const seconds = String(remaining % 60).padStart(2, '0');
  banner.textContent = `Leaving this page will log you out in ${minutes}:${seconds}.`;
  banner.classList.add('is-active');
}

function clearAwayLogoutTracking(role = awayLogoutRole || page()) {
  if (awayLogoutTimer) {
    clearTimeout(awayLogoutTimer);
    awayLogoutTimer = null;
  }
  if (awayLogoutTicker) {
    clearInterval(awayLogoutTicker);
    awayLogoutTicker = null;
  }
  awaySince = 0;
  awayLogoutRole = normalizePortalTarget(role);
  sessionStorage.removeItem(awayLogoutKey(awayLogoutRole));
  hideAwayLogoutBanner();
}

function forcePortalLogout(targetPage, reason = '') {
  const role = normalizePortalTarget(targetPage);
  markPortalLogout(role);
  clearAwayLogoutTracking(role);
  setToken('');
  if (reason) setAwayLogoutNotice(reason);
  window.location.replace('/');
}

function startAwayLogoutTracking(targetPage) {
  const role = normalizePortalTarget(targetPage);
  clearAwayLogoutTracking(role);
  awayLogoutRole = role;
  awaySince = Date.now();
  sessionStorage.setItem(awayLogoutKey(role), String(awaySince));
  updateAwayLogoutBanner(AWAY_AUTO_LOGOUT_MS);
  awayLogoutTicker = window.setInterval(() => {
    updateAwayLogoutBanner(AWAY_AUTO_LOGOUT_MS - (Date.now() - awaySince));
  }, 250);
  awayLogoutTimer = window.setTimeout(() => {
    forcePortalLogout(role, 'You were logged out after leaving the portal for 1 minute.');
  }, AWAY_AUTO_LOGOUT_MS);
}

function ensureAwayLogoutMonitor(targetPage) {
  const role = normalizePortalTarget(targetPage);
  if (document.body?.dataset.awayLogoutBound === role) {
    const stored = Number(sessionStorage.getItem(awayLogoutKey(role)) || 0);
    if (stored && Date.now() - stored >= AWAY_AUTO_LOGOUT_MS) {
      forcePortalLogout(role, 'You were logged out after leaving the portal for 1 minute.');
    }
    return;
  }
  if (document.body) {
    document.body.dataset.awayLogoutBound = role;
  }
  awayLogoutRole = role;

  const stored = Number(sessionStorage.getItem(awayLogoutKey(role)) || 0);
  if (stored && Date.now() - stored >= AWAY_AUTO_LOGOUT_MS) {
    forcePortalLogout(role, 'You were logged out after leaving the portal for 1 minute.');
    return;
  }
  if (stored) {
    awaySince = stored;
    const remaining = AWAY_AUTO_LOGOUT_MS - (Date.now() - stored);
    if (remaining > 0) {
      updateAwayLogoutBanner(remaining);
      awayLogoutTicker = window.setInterval(() => {
        updateAwayLogoutBanner(AWAY_AUTO_LOGOUT_MS - (Date.now() - awaySince));
      }, 250);
      awayLogoutTimer = window.setTimeout(() => {
        forcePortalLogout(role, 'You were logged out after leaving the portal for 1 minute.');
      }, remaining);
    }
  }

  document.addEventListener('visibilitychange', () => {
    if (!token) return;
    if (document.hidden) {
      startAwayLogoutTracking(role);
    } else {
      const hiddenSince = Number(sessionStorage.getItem(awayLogoutKey(role)) || 0);
      if (hiddenSince && Date.now() - hiddenSince >= AWAY_AUTO_LOGOUT_MS) {
        forcePortalLogout(role, 'You were logged out after leaving the portal for 1 minute.');
      } else {
        clearAwayLogoutTracking(role);
      }
    }
  });

  window.addEventListener('pagehide', () => {
    if (token) startAwayLogoutTracking(role);
  });

  window.addEventListener('pageshow', () => {
    const hiddenSince = Number(sessionStorage.getItem(awayLogoutKey(role)) || 0);
    if (hiddenSince && Date.now() - hiddenSince >= AWAY_AUTO_LOGOUT_MS) {
      forcePortalLogout(role, 'You were logged out after leaving the portal for 1 minute.');
    } else {
      clearAwayLogoutTracking(role);
    }
  });
}

function logoutMarkerKey(targetPage) {
  return `hit_logged_out_${normalizePortalTarget(targetPage)}`;
}

function markPortalLogout(targetPage) {
  sessionStorage.setItem(logoutMarkerKey(targetPage), String(Date.now()));
}

function clearPortalLogout(targetPage) {
  sessionStorage.removeItem(logoutMarkerKey(targetPage));
}

function wasRecentlyLoggedOut(targetPage) {
  const raw = sessionStorage.getItem(logoutMarkerKey(targetPage));
  if (!raw) return false;
  const stamp = Number(raw);
  return Number.isFinite(stamp) && Date.now() - stamp < 15 * 60 * 1000;
}

function redirectToLogin(targetPage) {
  window.location.replace(loginPath(targetPage));
}

function setToken(accessToken) {
  token = accessToken || '';
  if (token) {
    localStorage.setItem('hit_token', token);
    clearPortalLogout('student');
    clearPortalLogout('staff');
    clearPortalLogout('admin');
    const inferredRole = decodeJwtPayload(token)?.role || currentUserRole;
    setCurrentUserRole(inferredRole);
  } else {
    localStorage.removeItem('hit_token');
    setCurrentUserRole('');
  }
}

function guardPortalAccess(targetPage) {
  const role = normalizePortalTarget(targetPage);
  if (!token) {
    redirectToLogin(role);
    return false;
  }
  const currentRole = getCurrentUserRole();
  if (currentRole && currentRole !== role) {
    redirectToPortalForRole(currentRole);
    return false;
  }
  ensureAwayLogoutMonitor(role);
  window.addEventListener('pageshow', () => {
    if (!localStorage.getItem('hit_token')) {
      window.location.replace('/');
    }
  });
  return true;
}

function isInvalidTokenMessage(message) {
  const text = String(message || '').toLowerCase();
  return text.includes('token not valid')
    || text.includes('given token not valid')
    || text.includes('not valid for any token type')
    || (text.includes('access token') && text.includes('invalid'));
}

function handleAuthErrorForPage(error, targetPage = page()) {
  const message = error?.message || error;
  if (!isInvalidTokenMessage(message)) return false;
  setToken('');
  redirectToLogin(normalizePortalTarget(targetPage));
  return true;
}

function applyVerificationMessage(targetId) {
  const logoutNotice = consumeAwayLogoutNotice();
  if (logoutNotice) {
    showStatus(targetId, logoutNotice, false);
    return;
  }
  const params = new URLSearchParams(window.location.search);
  const state = params.get('verification');
  if (!state) return;
  if (state === 'success') {
    showStatus(targetId, 'Email verified successfully. You can now log in.');
    return;
  }
  if (state === 'already') {
    showStatus(targetId, 'This email is already verified. Please log in.');
    return;
  }
  if (state === 'invalid') {
    showStatus(targetId, 'The verification link is invalid or expired. Please request a new one.', false);
  }
}
function bindLogout() {
  const links = Array.from(document.querySelectorAll('#logout-btn, [data-logout-link]'));
  links.forEach((link) => {
    if (link.dataset.logoutBound === 'true') return;
    link.dataset.logoutBound = 'true';
    link.addEventListener('click', (event) => {
      event.preventDefault();
      const role = normalizePortalTarget(page());
      forcePortalLogout(role);
    });
  });
}
function scannerResultState(errMessage) {
  const message = String(errMessage || "").toLowerCase();
  if (message.includes("already redeemed") || message.includes("already used")) {
    return { status: "used", title: "Ticket already used", message: errMessage || "This ticket has already been redeemed." };
  }
  return { status: "invalid", title: "Invalid ticket", message: errMessage || "The scanned ticket could not be validated." };
}

function renderScannerResult(status, title, message, details = null) {
  const card = id("scanner-result-card");
  const badge = card?.querySelector(".scanner-result-badge");
  const iconNode = id("scanner-result-icon");
  const titleNode = id("scanner-result-title");
  const messageNode = id("scanner-result-message");
  const detailsNode = id("scanner-result-details");
  if (!card || !badge || !iconNode || !titleNode || !messageNode) return;
  card.className = `scanner-result-card ${status}`;
  iconNode.className = `scanner-result-icon ${status}`;
  badge.className = `scanner-result-badge ${status}`;
  badge.textContent = status === "valid" ? "Valid" : status === "used" ? "Already Used" : status === "invalid" ? "Invalid" : "Waiting";
  if (status === "valid") {
    iconNode.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M9.55 18.2 4.8 13.45l1.4-1.4 3.35 3.35 8.25-8.25 1.4 1.4Z"/></svg>';
  } else if (status === "used") {
    iconNode.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2Zm1 11h-2V7h2Zm0 4h-2v-2h2Z"/></svg>';
  } else if (status === "invalid") {
    iconNode.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M18.3 5.71 12 12l6.3 6.29-1.41 1.41L10.59 13.4 4.29 19.7 2.88 18.29 9.17 12 2.88 5.71 4.29 4.29l6.3 6.3 6.29-6.3Z"/></svg>';
  } else {
    iconNode.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2Zm1 11h-2V7h2Zm0 4h-2v-2h2Z"/></svg>';
  }
  titleNode.textContent = title;
  messageNode.textContent = message;
    if (detailsNode) {
      if (details && typeof details === "object") {
        detailsNode.hidden = false;
        detailsNode.innerHTML = Object.entries(details)
          .filter(([, value]) => value !== undefined && value !== null && String(value).trim() !== "")
          .map(([label, value]) => {
            const isPrimary = /collection\s*no\.?|order\s*number|order\s*ref/i.test(String(label));
            return `<div class="scanner-detail-row${isPrimary ? ' scanner-detail-row--primary' : ''}"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`;
          })
          .join("");
      } else {
        detailsNode.hidden = true;
        detailsNode.innerHTML = "";
      }
  }
}

function playScannerTone(type = "success") {
  if (!["staff-scanner", "student-pay-scanner"].includes(page())) return;
  const AudioCtx = window.AudioContext || window.webkitAudioContext;
  if (!AudioCtx) return;
  try {
    if (!window.__hitScannerAudioCtx) {
      window.__hitScannerAudioCtx = new AudioCtx();
    }
    const ctx = window.__hitScannerAudioCtx;
    const now = ctx.currentTime;
    const steps = type === "success"
      ? [
          { freq: 1480, duration: 0.09, gain: 0.26, when: 0 },
          { freq: 1760, duration: 0.12, gain: 0.34, when: 0.1 },
          { freq: 2090, duration: 0.14, gain: 0.28, when: 0.23 },
        ]
      : [
          { freq: 320, duration: 0.16, gain: 0.26, when: 0 },
          { freq: 210, duration: 0.22, gain: 0.22, when: 0.14 },
        ];

    steps.forEach((step) => {
      const oscillator = ctx.createOscillator();
      const gainNode = ctx.createGain();
      oscillator.type = type === "success" ? "square" : "sawtooth";
      oscillator.frequency.setValueAtTime(step.freq, now + step.when);
      gainNode.gain.setValueAtTime(0.0001, now + step.when);
      gainNode.gain.exponentialRampToValueAtTime(step.gain, now + step.when + 0.01);
      gainNode.gain.exponentialRampToValueAtTime(0.0001, now + step.when + step.duration);
      oscillator.connect(gainNode);
      gainNode.connect(ctx.destination);
      oscillator.start(now + step.when);
      oscillator.stop(now + step.when + step.duration + 0.02);
    });
  } catch (_) {
    // Ignore audio failures; scan result UI still updates.
  }
}

function triggerScannerFeedback(type = "success") {
  playScannerTone(type);
  try {
    if (navigator.vibrate) {
      navigator.vibrate(type === "success" ? [120, 40, 120] : [180, 60, 180]);
    }
  } catch (_) {
    // ignore vibration failures
  }
}

async function validateTicketToken(tokenValue, statusTargetId = "scan-status") {
  const cleanToken = String(tokenValue || "").trim();
  if (!cleanToken) {
    showStatus(statusTargetId, "Paste or scan a ticket token first.", false);
    if (page() === "staff-scanner") {
      renderScannerResult("invalid", "No ticket token", "Paste or scan a ticket token before validating.");
    }
    return null;
  }
  try {
    const result = await req("/api/v1/tickets/validate-scan", "POST", { token: cleanToken });
    const collectionNumber = result.order_ref || result.order_id;
    showStatus(statusTargetId, `Ticket valid. Collection No. ${collectionNumber} served.`);
    if (page() === "staff-scanner") {
      let details = {
        'Collection No.': String(collectionNumber || ''),
        Status: 'Verified',
        Time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };
      try {
        const order = await req(`/api/v1/orders/${result.order_id}`);
        details = {
          'Collection No.': order.order_ref || String(collectionNumber || ''),
          'Student Name': order.student_name || `Student #${result.student_id || ''}`.trim(),
          Meal: order.meal || 'Meal',
          Quantity: String(order.quantity ?? 1),
          Time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          Status: 'Verified',
        };
      } catch (_) {
        // Keep minimal confirmation details if order lookup fails.
      }
      renderScannerResult("valid", "Meal Verified", `Collection No. ${collectionNumber} has been marked as served.`, details);
      triggerScannerFeedback("success");
    }
    await loadOrdersForStaff();
    await loadServedMeals();
    await loadFraudAlerts();
    await loadReconciliation();
    return result;
  } catch (err) {
    const state = scannerResultState(err.message || "Ticket validation failed.");
    showStatus(statusTargetId, state.message, false);
    if (page() === "staff-scanner") {
      renderScannerResult(state.status, 'Invalid or Already Used', state.message);
      triggerScannerFeedback("error");
    }
    await loadFraudAlerts();
    return null;
  }
}

function walletBalance() {
  return Number(localStorage.getItem("wallet_balance") || 0);
}

function persistCart() {
  localStorage.setItem("hit_cart", JSON.stringify(cart));
}

function cartTotal() {
  return cart.reduce((sum, item) => sum + item.price * item.qty, 0);
}

function mealVisualProfile(meal) {
  const text = `${meal?.name || ''} ${meal?.description || ''}`.toLowerCase();
  if (text.includes('water') || text.includes('orange') || text.includes('juice') || text.includes('drink') || text.includes('mazoe')) {
    return { label: 'Drink', emoji: '🥤', start: '#dbeafe', end: '#bfdbfe', accent: '#0F4C9C' };
  }
  if (text.includes('salad') || text.includes('veggie') || text.includes('vegetable')) {
    return { label: 'Fresh', emoji: '🥗', start: '#dcfce7', end: '#bbf7d0', accent: '#15803d' };
  }
  if (text.includes('chicken') || text.includes('beef') || text.includes('sandwich') || text.includes('burger')) {
    return { label: 'Meal', emoji: '🍔', start: '#fef3c7', end: '#fde68a', accent: '#b45309' };
  }
  return { label: 'Plate', emoji: '🍽️', start: '#e0e7ff', end: '#c7d2fe', accent: '#3730a3' };
}

function mealArtworkMarkup(meal) {
  const profile = mealVisualProfile(meal);
  return `
    <div class="hit-meal-art" style="--meal-start:${profile.start};--meal-end:${profile.end};--meal-accent:${profile.accent};">
      <span class="hit-meal-art__emoji" aria-hidden="true">${profile.emoji}</span>
      <span class="hit-meal-art__label">${escapeHtml(profile.label)}</span>
    </div>
  `;
}

function mealImageMarkup(meal) {
  if (meal && meal.image_data) {
    return `<img class="hit-meal-photo" src="${escapeHtml(meal.image_data)}" alt="${escapeHtml(meal.name || 'Meal image')}" />`;
  }
  return mealArtworkMarkup(meal);
}

function fileToDataUrl(file) {
  return new Promise((resolve, reject) => {
    if (!file) {
      resolve("");
      return;
    }
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(new Error("Unable to read the selected image."));
    reader.readAsDataURL(file);
  });
}

function mealVisualProfile(meal) {
  const text = `${meal?.name || ''} ${meal?.description || ''}`.toLowerCase();
  if (text.includes('water') || text.includes('orange') || text.includes('juice') || text.includes('drink') || text.includes('mazoe')) {
    return { label: 'Drink', emoji: '🥤', start: '#dbeafe', end: '#bfdbfe', accent: '#0F4C9C' };
  }
  if (text.includes('salad') || text.includes('veggie') || text.includes('vegetable')) {
    return { label: 'Fresh', emoji: '🥗', start: '#dcfce7', end: '#bbf7d0', accent: '#15803d' };
  }
  if (text.includes('chicken') || text.includes('beef') || text.includes('sandwich') || text.includes('burger')) {
    return { label: 'Meal', emoji: '🍔', start: '#fef3c7', end: '#fde68a', accent: '#b45309' };
  }
  return { label: 'Plate', emoji: '🍽️', start: '#e0e7ff', end: '#c7d2fe', accent: '#3730a3' };
}

function mealArtworkMarkup(meal) {
  const profile = mealVisualProfile(meal);
  return `
    <div class="hit-meal-art" style="--meal-start:${profile.start};--meal-end:${profile.end};--meal-accent:${profile.accent};">
      <span class="hit-meal-art__emoji" aria-hidden="true">${profile.emoji}</span>
      <span class="hit-meal-art__label">${escapeHtml(profile.label)}</span>
    </div>
  `;
}

function getPendingPaynowOrderTx() {
  return localStorage.getItem("hit_pending_paynow_order_tx") || "";
}

function setPendingPaynowOrderTx(txId) {
  if (txId) localStorage.setItem("hit_pending_paynow_order_tx", txId);
  else localStorage.removeItem("hit_pending_paynow_order_tx");
}

function getPendingPaynowTopupTx() {
  return localStorage.getItem("hit_pending_paynow_topup_tx") || "";
}

function setPendingPaynowTopupTx(txId) {
  if (txId) localStorage.setItem("hit_pending_paynow_topup_tx", txId);
  else localStorage.removeItem("hit_pending_paynow_topup_tx");
}

function setWalletBalance(value) {
  const safe = Number(value || 0);
  const formatted = `$${safe.toFixed(2)}`;
  localStorage.setItem("wallet_balance", String(safe));
  if (id("wallet-balance")) {
    id("wallet-balance").textContent = page() === "student" || page() === "student-add-money" ? formatted : `Balance: ${formatted}`;
  }
  if (id("wallet-balance-corner")) id("wallet-balance-corner").textContent = `Balance: ${formatted}`;
  if (id("cart-wallet-balance")) id("cart-wallet-balance").textContent = `Balance: ${formatted}`;
}

function nextIdempotencyKey(prefix) {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

function addToCart(meal) {
  const existing = cart.find((item) => item.id === meal.id);
  if (existing) existing.qty += 1;
  else cart.push({ ...meal, qty: 1 });
  persistCart();
  renderCart();
  if (page() === "student-menu") {
    window.location.href = "/student-cart/";
  }
}

function removeFromCart(index) {
  cart.splice(index, 1);
  persistCart();
  renderCart();
}

function renderCart() {
  const cartList = id("cart-list");
  const totalNode = id("cart-total");
  const chartNode = id("cart-chart");
  if (!cartList || !totalNode || !chartNode) return;
  if (!cart.length) {
    cartList.innerHTML = "<p class='hint'>Cart is empty.</p>";
    totalNode.textContent = "Total: $0.00";
    chartNode.innerHTML = '<p class="hint">No items in cart.</p>';
    return;
  }
  cartList.innerHTML = cart.map((item, index) => `
    <div class="list-item cart-row">
      <span>${item.name} x${item.qty} - $${(item.price * item.qty).toFixed(2)}</span>
      <button class="link danger" type="button" data-remove-index="${index}">Remove</button>
    </div>
  `).join("");
  cartList.querySelectorAll("[data-remove-index]").forEach((button) => {
    button.addEventListener("click", () => removeFromCart(Number(button.dataset.removeIndex)));
  });
  persistCart();
  const total = cartTotal();
  totalNode.textContent = `Total: $${total.toFixed(2)}`;
  const max = Math.max(...cart.map((item) => item.qty));
  chartNode.innerHTML = cart.map((item) => {
    const width = max ? Math.round((item.qty / max) * 100) : 0;
    return `<div class="bar-row"><span class="bar-label">${item.name}</span><div class="bar-track"><div class="bar-fill" style="width:${width}%"></div></div><span class="bar-value">${item.qty}</span></div>`;
  }).join("");
}

function renderMenu(targetId, meals) {
  const node = id(targetId);
  if (!node) return;
  node.innerHTML = meals.map((meal) => `
    <button class="list-item meal-item" type="button" data-id="${meal.id}" data-name="${meal.name}" data-price="${meal.price}">
      <span class="badge">ID ${meal.id}</span> ${meal.name} - $${Number(meal.price).toFixed(2)} <small>${meal.description || ""}</small>
    </button>
  `).join("");
  node.querySelectorAll(".meal-item").forEach((button) => {
    button.addEventListener("click", () => addToCart({ id: Number(button.dataset.id), name: button.dataset.name, price: Number(button.dataset.price) }));
  });
}
function renderStaffMeals(meals) {
  const node = id("staff-meals-list");
  if (!node) return;
  if (!meals.length) {
    node.innerHTML = '<p class="hint">No active meals are available right now.</p>';
    return;
  }
  node.innerHTML = meals.map((meal) => {
    const stock = Number(meal.stock_quantity ?? 0);
    const lowStockClass = stock <= 10 ? " low" : "";
    const lowStockLabel = stock <= 10 ? '<span class="staff-low-stock-badge">Low stock</span>' : '';
    return `
      <div class="staff-meal-card${lowStockClass}">
        <div class="staff-meal-card__media">${mealImageMarkup(meal)}</div>
        <div class="staff-meal-card__top">
          <strong>${escapeHtml(meal.name)}</strong>
          <span class="staff-meal-price">$${Number(meal.price).toFixed(2)}</span>
        </div>
        <p>${escapeHtml(meal.description || "No description added yet.")}</p>
        <div class="staff-meal-stock-row">
          <span class="staff-meal-meta">Meal ID: ${escapeHtml(meal.id)}</span>
          <span class="staff-meal-stock${lowStockClass}">Available: ${escapeHtml(stock)}</span>
        </div>
        ${lowStockLabel}
        <div class="staff-meal-actions">
          <button class="button" type="button" data-action="sell-one" data-id="${meal.id}">Subtract 1 Sold</button>
          <button class="button" type="button" data-action="add-stock" data-id="${meal.id}">Add Stock</button>
          <button class="button alt" type="button" data-action="remove-meal" data-id="${meal.id}">Remove Meal</button>
        </div>
        <div class="staff-stock-adjuster">
          <input class="staff-stock-input" type="number" min="1" value="1" data-stock-input="${meal.id}" placeholder="Qty" />
          <button class="button" type="button" data-action="subtract-custom" data-id="${meal.id}">Subtract Qty</button>
        </div>
      </div>
    `;
  }).join("");

  const updateStock = async (mealId, delta, successMessage) => {
    try {
      await req(`/api/v1/menu/${mealId}`, "PATCH", { stock_delta: delta });
      showStatus("meal-status", successMessage);
      await loadMenuAndSlots();
    } catch (err) {
      showStatus("meal-status", err.message || "Unable to update stock.", false);
    }
  };

  node.querySelectorAll('[data-action="sell-one"]').forEach((button) => button.addEventListener("click", async () => {
    await updateStock(button.dataset.id, -1, "Meal stock reduced by 1.");
  }));
  node.querySelectorAll('[data-action="add-stock"]').forEach((button) => button.addEventListener("click", async () => {
    const qty = Number(node.querySelector(`[data-stock-input="${button.dataset.id}"]`)?.value || 1);
    await updateStock(button.dataset.id, Math.max(1, qty), `Meal stock increased by ${Math.max(1, qty)}.`);
  }));
  node.querySelectorAll('[data-action="subtract-custom"]').forEach((button) => button.addEventListener("click", async () => {
    const qty = Number(node.querySelector(`[data-stock-input="${button.dataset.id}"]`)?.value || 1);
    await updateStock(button.dataset.id, -Math.max(1, qty), `Meal stock reduced by ${Math.max(1, qty)}.`);
  }));
  node.querySelectorAll('[data-action="remove-meal"]').forEach((button) => button.addEventListener("click", async () => {
    const mealCard = button.closest(".staff-meal-card");
    const mealName = mealCard?.querySelector("strong")?.textContent || "this meal";
    const confirmed = window.confirm(`Remove ${mealName} from the active menu?`);
    if (!confirmed) return;
    try {
      await req(`/api/v1/menu/${button.dataset.id}`, "DELETE");
      showStatus("meal-status", "Meal removed from active menu.");
      await loadMenuAndSlots();
    } catch (err) {
      showStatus("meal-status", err.message || "Unable to remove meal.", false);
    }
  }));
}

function renderSlots(slots) {
  const node = id("slots-list");
  if (!node) return;
  node.innerHTML = "";
}

function renderTickets() {
  const node = id('ticket-list');
  if (!node) return;
  if (!latestTickets.length) {
    node.innerHTML = '<p class="hint">Your confirmed meal tickets will appear here after payment.</p>';
    return;
  }
  node.innerHTML = latestTickets.map((ticket) => `
    <article class="ticket-card">
      <div class="ticket-card__meta">
        <strong>${ticket.order_ref || ticket.ticket_id}</strong>
        <span>${ticket.expires_at ? `Valid until ${new Date(ticket.expires_at).toLocaleString()}` : 'Ticket issued'}</span>
      </div>
      <div class="ticket-card__qr">${ticket.ticket_qr_svg || ticket.qr_svg || '<p class="hint">QR unavailable</p>'}</div>
      <div class="ticket-card__token">${ticket.ticket_token || ticket.token || ''}</div>
    </article>
  `).join('');
}

function renderTransactionHistory(data) {
  const node = id('transaction-history');
  if (!node) return;

  const items = [
    ...(data?.payments || []).map((payment) => ({
      title: payment.provider ? `${payment.provider} payment` : 'Payment',
      subtitle: formatDateTime(payment.created_at || payment.timestamp),
      amount: Number(payment.amount || 0),
      positive: ['success', 'paid', 'confirmed', 'completed'].includes(String(payment.status || '').toLowerCase()),
      sortValue: payment.created_at || payment.timestamp || '',
    })),
    ...(data?.orders || []).map((order) => ({
      title: order.meal ? `${order.meal} order` : 'Meal order',
      subtitle: formatDateTime(order.created_at || order.timestamp),
      amount: Number(order.total_amount || 0),
      positive: false,
      sortValue: order.created_at || order.timestamp || '',
    })),
    ...(data?.ledger || []).map((entry) => ({
      title: String(entry.type || '').toLowerCase() === 'credit' ? 'Wallet top up' : 'Wallet debit',
      subtitle: formatDateTime(entry.created_at || entry.timestamp),
      amount: Number(entry.amount || 0),
      positive: String(entry.type || '').toLowerCase() === 'credit',
      sortValue: entry.created_at || entry.timestamp || '',
    })),
  ]
    .sort((a, b) => new Date(b.sortValue || 0).getTime() - new Date(a.sortValue || 0).getTime())
    .slice(0, page() === 'student' ? 6 : 50);

  if (!items.length) {
    node.innerHTML = page() === 'student'
      ? '<div class="px-4 py-5 text-sm text-slate-500">No recent activity yet.</div>'
      : '<p class="hint">No recent activity yet.</p>';
    return;
  }

  if (page() === 'student') {
    node.innerHTML = items.map((item) => `
      <div class="px-4 py-4 flex items-center justify-between gap-4">
        <div class="min-w-0">
          <p class="text-sm font-semibold text-hitText truncate">${escapeHtml(item.title)}</p>
          <p class="text-xs text-hitMuted mt-1">${escapeHtml(item.subtitle)}</p>
        </div>
        <p class="text-sm font-bold whitespace-nowrap ${item.positive ? 'text-green-600' : 'text-red-600'}">${item.positive ? '+' : '-'}${formatCurrency(Math.abs(item.amount))}</p>
      </div>
    `).join('');
    return;
  }

  node.innerHTML = items.map((item) => `<div class="list-item"><strong>${escapeHtml(item.title)}</strong> | ${escapeHtml(item.subtitle)} | ${item.positive ? '+' : '-'}${formatCurrency(Math.abs(item.amount))}</div>`).join('');
}
async function loadMyTickets() {
  try {
    latestTickets = await req("/api/v1/tickets/mine");
    renderTickets();
  } catch {
    latestTickets = [];
    renderTickets();
  }
}

function renderStaffOrders(orders) {
    const list = id("staff-orders-list");
    const chart = id("staff-orders-chart");
    renderChefNextOrder(orders);
    if (list) {
      list.innerHTML = orders.length ? orders.map((order) => `<div class="list-item"><strong>${order.order_ref}</strong> | ${order.student_name || order.student_email || ""} | ${order.meal} x${order.quantity} | $${Number(order.total_amount).toFixed(2)} | ${order.status}</div>`).join("") : '<p class="hint">No orders available.</p>';
    }
  if (chart) {
    if (!orders.length) {
      chart.innerHTML = '<p class="hint">No orders available.</p>';
      return;
    }
    const counts = orders.reduce((acc, order) => {
      const label = order.status || "unknown";
      acc[label] = (acc[label] || 0) + 1;
      return acc;
    }, {});
    const entries = Object.entries(counts);
    const max = Math.max(...entries.map(([, value]) => value));
    chart.innerHTML = entries.map(([label, value]) => `<div class="bar-row"><span class="bar-label">${label}</span><div class="bar-track"><div class="bar-fill" style="width:${Math.round((value / max) * 100)}%"></div></div><span class="bar-value">${value}</span></div>`).join("");
  }
}

function renderServedMeals(orders) {
  const node = id("served-meals-list");
  if (!node) return;
  node.innerHTML = orders.length ? orders.map((order) => `<div class="list-item"><strong>${order.order_ref}</strong> | ${order.student_name} | ${order.meal} x${order.quantity} | served ${order.served_at ? new Date(order.served_at).toLocaleString() : "recently"}</div>`).join("") : '<p class="hint">No served meals yet.</p>';
}

function renderFraudAlerts(alerts) {
  const node = id("fraud-alerts-list");
  if (!node) return;
  node.innerHTML = alerts.length ? alerts.map((alert) => `<div class="list-item"><strong>${alert.alert_type}</strong> | ${alert.severity} | ${alert.created_at ? new Date(alert.created_at).toLocaleString() : "recent"}<br><small>${alert.detail || ""}</small></div>`).join("") : '<p class="hint">No fraud alerts recorded.</p>';
}


function renderCashStudentPreview(student) {
  const node = id("cash-student-preview");
  if (!node) return;
  if (!student) {
    node.innerHTML = `<p class="hint">Search for a student by ID to confirm the wallet account before depositing.</p>`;
    return;
  }
  node.innerHTML = `
    <div class="list-item">
      <strong>${escapeHtml(student.full_name)}</strong> | ${escapeHtml(student.student_id)} | ${escapeHtml(student.email)} | Wallet $${Number(student.wallet_balance || 0).toFixed(2)}
    </div>
  `;
}

function renderCashDepositHistory(items) {
  const node = id("cash-deposit-history");
  if (!node) return;
  if (!items || !items.length) {
    node.innerHTML = `<p class="hint">No recent cash deposits yet.</p>`;
    return;
  }
  node.innerHTML = items.map((item) => `
    <div class="list-item">
      <strong>${escapeHtml(item.student_name)}</strong> | ${escapeHtml(item.student_id)} | $${Number(item.amount).toFixed(2)} | ${escapeHtml(item.cashier)} | ${new Date(item.timestamp).toLocaleString()}
    </div>
  `).join("");
}

function setHint(targetId, message, ok = true) {
  const el = id(targetId);
  if (!el) return;
  el.textContent = message || "";
  el.className = ok ? "hint success" : "hint error";
}

async function checkAvailability() {
  const email = (id("register-email")?.value || "").trim();
  const universityId = (id("register-university-id")?.value || "").trim();
  if (!email && !universityId) return { emailAvailable: null, universityIdAvailable: null };
  try {
    const params = new URLSearchParams();
    if (email) params.set("email", email);
    if (universityId) params.set("university_id", universityId);
    const data = await req(`/api/v1/auth/check-availability?${params.toString()}`);
    if (data.email) setHint("register-email-status", data.email.message, data.email.available === true);
    if (data.university_id) setHint("register-university-id-status", data.university_id.message, data.university_id.available === true);
    return {
      emailAvailable: data.email ? data.email.available : null,
      universityIdAvailable: data.university_id ? data.university_id.available : null,
    };
  } catch {
    return { emailAvailable: null, universityIdAvailable: null };
  }
}

function populateWalkinMenu(meals) {
  const selectedMealInput = id("walkin-meal-id");
  const optionsNode = id("walkin-meal-options");
  if (!selectedMealInput || !optionsNode) return;
  const safeMeals = Array.isArray(meals) ? meals : [];
  if (!safeMeals.length) {
    selectedMealInput.value = "";
    optionsNode.innerHTML = '<p class="hint">No meals available right now.</p>';
    return;
  }

function renderChefNextOrder(orders) {
  const mealNode = id("chef-next-meal");
  const studentNode = id("chef-next-student");
  const qtyNode = id("chef-next-quantity");
  const refNode = id("chef-next-order-ref");
  const upNextNode = id("chef-up-next");
  const waitingNode = id("chef-next-waiting-count");
  const statusNode = id("chef-next-status");
  const noteNode = id("chef-next-note");
  if (!mealNode || !studentNode || !qtyNode || !refNode || !upNextNode || !waitingNode || !statusNode || !noteNode) return;

  const safeOrders = Array.isArray(orders) ? orders : [];
  const actionable = safeOrders
    .filter((order) => {
      const status = String(order.status || "").toLowerCase();
      return !["served", "redeemed", "cancelled", "failed", "expired"].includes(status);
    })
    .sort((a, b) => new Date(a.created_at || 0).getTime() - new Date(b.created_at || 0).getTime());

  if (!actionable.length) {
    mealNode.textContent = "No pending meal";
    studentNode.textContent = "Waiting for new orders";
    qtyNode.textContent = "0 meals";
    refNode.textContent = "-";
    upNextNode.textContent = "No next order";
    waitingNode.textContent = "0 more orders";
    statusNode.textContent = "Queue clear";
    noteNode.textContent = "New paid student orders will appear here so the chef knows what to prepare next.";
    return;
  }

  const nextOrder = actionable[0];
  const secondOrder = actionable[1] || null;
  const remaining = Math.max(0, actionable.length - 1);
  mealNode.textContent = nextOrder.meal || "Meal pending";
  studentNode.textContent = nextOrder.student_name || nextOrder.student_email || "Student";
  qtyNode.textContent = `${Number(nextOrder.quantity || 1)} meal${Number(nextOrder.quantity || 1) === 1 ? "" : "s"}`;
  refNode.textContent = nextOrder.order_ref || "-";
  upNextNode.textContent = secondOrder ? `${secondOrder.order_ref || "-"} • ${secondOrder.meal || "Meal pending"}` : "No next order";
  waitingNode.textContent = `${remaining} more order${remaining === 1 ? "" : "s"}`;
  statusNode.textContent = remaining > 0 ? "Line active" : "Ready now";
  const queuedAt = nextOrder.created_at ? new Date(nextOrder.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "just now";
  noteNode.textContent = `Queued at ${queuedAt}. Plate ${nextOrder.meal || "this meal"} for ${nextOrder.student_name || nextOrder.student_email || "the next student"} first, then move straight to the next ticket.`;
}
  selectedMealInput.value = String(safeMeals[0].id);
  optionsNode.innerHTML = safeMeals.map((meal, index) => `
    <button class="walkin-meal-chip${index === 0 ? ' active' : ''}" type="button" data-walkin-meal-id="${meal.id}">
      <strong>${escapeHtml(meal.name)}</strong>
      <span>$${Number(meal.price).toFixed(2)}</span>
    </button>
  `).join("");
  optionsNode.querySelectorAll('[data-walkin-meal-id]').forEach((button) => {
    button.addEventListener('click', () => {
      selectedMealInput.value = String(button.dataset.walkinMealId || '');
      optionsNode.querySelectorAll('.walkin-meal-chip').forEach((chip) => chip.classList.remove('active'));
      button.classList.add('active');
    });
  });
}

function addDaysIso(baseDate, daysToAdd) {
  const copy = new Date(baseDate);
  copy.setDate(copy.getDate() + daysToAdd);
  return copy.toISOString().slice(0, 10);
}

function renderForecastPie(items = []) {
  const canvas = id("forecast-pie");
  const legend = id("forecast-legend");
  if (!canvas || !legend) return;
  const ctx = canvas.getContext("2d");
  const colors = ["#12307a", "#d4a017", "#0b6cf0", "#16a085", "#e67e22", "#8b5cf6", "#ef4444", "#0891b2"];
  const data = items.filter((item) => Number(item.value || item.forecast_qty || 0) > 0).map((item) => ({
    label: item.label || item.meal_name,
    value: Number(item.value || item.forecast_qty || 0),
  }));
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  legend.innerHTML = "";
  if (!data.length) {
    legend.innerHTML = '<div class="hit-empty-state">No forecast data yet for this date.</div>';
    return;
  }
  const total = data.reduce((sum, item) => sum + item.value, 0) || 1;
  let start = -Math.PI / 2;
  data.forEach((item, index) => {
    const slice = (item.value / total) * Math.PI * 2;
    ctx.beginPath();
    ctx.moveTo(160, 160);
    ctx.arc(160, 160, 130, start, start + slice);
    ctx.closePath();
    ctx.fillStyle = colors[index % colors.length];
    ctx.fill();
    start += slice;
    legend.innerHTML += `<div class="legend-row"><span class="legend-swatch" style="background:${colors[index % colors.length]}"></span>${escapeHtml(item.label)} - ${item.value}</div>`;
  });
}

function renderForecastPrepList(targetDate, items) {
  const node = id('forecast-prepare-list');
  if (!node) return;
  const sorted = [...items].sort((a, b) => Number(b.forecast_qty || 0) - Number(a.forecast_qty || 0));
  if (!sorted.length || sorted.every((item) => Number(item.forecast_qty || 0) <= 0)) {
    node.innerHTML = `<div class="hit-empty-state">No preparation quantities predicted for ${escapeHtml(targetDate)}.</div>`;
    return;
  }
  node.innerHTML = sorted.map((item) => `
    <div class="forecast-meal-row">
      <div>
        <strong>${escapeHtml(item.meal_name)}</strong>
        <span>Prepare for ${new Date(`${targetDate}T00:00:00`).toLocaleDateString('en-US', { weekday: 'long' })}</span>
      </div>
      <strong>${Number(item.forecast_qty || 0)} meals</strong>
    </div>
  `).join('');
}

function renderForecastDayOutlook(days) {
  const node = id('forecast-day-outlook');
  if (!node) return;
  if (!days.length) {
    node.innerHTML = '<div class="hit-empty-state">No outlook available.</div>';
    return;
  }
  node.innerHTML = days.map((entry) => `
    <div class="forecast-day-row">
      <div>
        <strong>${escapeHtml(entry.weekday)}</strong>
        <span>${escapeHtml(entry.date)}</span>
      </div>
      <strong>${entry.total} meals</strong>
    </div>
  `).join('');
}

async function loadDemandForecast(targetDate) {
  const dateValue = targetDate || addDaysIso(new Date(), 1);
  try {
    const items = await req(`/api/v1/admin/reports/demand-forecast?date=${encodeURIComponent(dateValue)}`);
    renderForecastPie(items);
    renderForecastPrepList(dateValue, items);
    const totalMeals = items.reduce((sum, item) => sum + Number(item.forecast_qty || 0), 0);
    const weekday = new Date(`${dateValue}T00:00:00`).toLocaleDateString('en-US', { weekday: 'long' });
    showStatus('forecast-status', `Forecast ready for ${weekday}, ${dateValue}. Prepare about ${totalMeals} meals in total.`);
    return items;
  } catch (err) {
    renderForecastPie([]);
    renderForecastPrepList(dateValue, []);
    showStatus('forecast-status', err.message || 'Unable to load forecast right now.', false);
    return [];
  }
}

async function loadForecastOutlook(startDate) {
  const base = new Date(`${startDate}T00:00:00`);
  const outlook = [];
  for (let offset = 0; offset < 7; offset += 1) {
    const dayIso = addDaysIso(base, offset);
    try {
      const items = await req(`/api/v1/admin/reports/demand-forecast?date=${encodeURIComponent(dayIso)}`);
      outlook.push({
        date: dayIso,
        weekday: new Date(`${dayIso}T00:00:00`).toLocaleDateString('en-US', { weekday: 'long' }),
        total: items.reduce((sum, item) => sum + Number(item.forecast_qty || 0), 0),
      });
    } catch {
      outlook.push({
        date: dayIso,
        weekday: new Date(`${dayIso}T00:00:00`).toLocaleDateString('en-US', { weekday: 'long' }),
        total: 0,
      });
    }
  }
  renderForecastDayOutlook(outlook);
}

function renderReconciliation(data) {
  const node = id("reconciliation-output");
  if (!node) return;
  node.innerHTML = `
    <div class="list-item"><strong>Date</strong> ${data.report_date}</div>
    <div class="list-item"><strong>Payments Received</strong> $${Number(data.payments_received).toFixed(2)}</div>
    <div class="list-item"><strong>Paid Orders Total</strong> $${Number(data.paid_orders_total).toFixed(2)}</div>
    <div class="list-item"><strong>Meals Collected</strong> ${data.meals_collected_total}</div>
    <div class="list-item"><strong>Successful Payments</strong> ${data.successful_payments_count}</div>
    <div class="list-item"><strong>Paid Orders</strong> ${data.paid_orders_count}</div>
    <div class="list-item"><strong>Served Orders</strong> ${data.served_orders_count}</div>
    <div class="list-item"><strong>Discrepancy</strong> $${Number(data.discrepancy_amount).toFixed(2)}</div>
    <div class="list-item"><strong>Notes</strong> ${data.notes || "No discrepancies detected."}</div>
  `;
}

async function loginRequest(emailId, passwordId) {
  const email = id(emailId)?.value.trim() || "";
  const password = id(passwordId)?.value || "";
  if (!email || !password) return { error: "Email and password are required." };
  try {
    const data = await req("/api/v1/auth/login", "POST", { email, password });
    setCurrentUserRole(data.role);
    setToken(data.access_token);
    return { ok: true, data };
  } catch (err) {
    const payload = err.payload || {};
    if (payload.verification_required && payload.verification_url) {
      return { error: `Email verification required. <a href="${payload.verification_url}">Verify this HIT account</a>.` };
    }
    return { error: err.message || "Login failed." };
  }
}

async function loadWallet() {
  try {
    const data = await req("/api/v1/wallet");
    setWalletBalance(data.balance || 0);
  } catch (err) {
    if ((err.message || "").toLowerCase().includes("suspended")) {
      showStatus("wallet-status", err.message, false);
    }
    setWalletBalance(walletBalance());
  }
}

async function loadMenuAndSlots() {
  try {
    const meals = await req("/api/v1/menu");
    const safeMeals = meals.length ? meals : demoMeals;
    renderMenu("menu-list", safeMeals);
    renderStaffMeals(safeMeals);
    populateWalkinMenu(safeMeals);
  } catch {
    if (page() === "student" || page() === "student-menu") renderDashboardMenuCards(demoMeals); else renderMenu("menu-list", demoMeals);
    renderStaffMeals(demoMeals);
    populateWalkinMenu(demoMeals);
  }
}

async function loadTransactionHistory() {
  try {
    const data = await req("/api/v1/transactions/history");
    renderTransactionHistory(data);
    return data;
  } catch (err) {
    renderTransactionHistory({});
    showStatus("wallet-status", err.message || "Unable to load transaction history.", false);
    return null;
  }
}

async function checkPendingPaynowOrderReturn() {
  const params = new URLSearchParams(window.location.search);
  const hasReturnFlag = params.get("paynow") === "processing";
  const pendingTx = getPendingPaynowOrderTx();
  if (!hasReturnFlag && !pendingTx) return;

  const data = await loadTransactionHistory();
  if (!data || !pendingTx) {
    if (hasReturnFlag) {
      showStatus("order-status", "Your Paynow payment is being confirmed. Refresh in a moment and your QR ticket will appear once the payment is verified.");
    }
    return;
  }

  const payment = (data.payments || []).find((entry) => entry.tx_id === pendingTx);
  if (!payment) {
    showStatus("order-status", "Your Paynow payment is still being processed. Refresh in a moment.");
    return;
  }

  const meta = payment.meta_json || {};
  if (payment.status === "succeeded" && payment.purpose === "order_payment" && meta.fulfilled) {
    cart = [];
    persistCart();
    setPendingPaynowOrderTx("");
    renderCart();
    await loadMyTickets();
    showStatus("order-status", "Paynow payment confirmed. Opening your QR ticket now...");
    if (hasReturnFlag) window.history.replaceState({}, "", "/student-qr/");
    setTimeout(() => {
      window.location.href = "/student-qr/";
    }, 250);
    return;
  }

  if (payment.status === "succeeded" && meta.wallet_credited) {
    setPendingPaynowOrderTx("");
    await loadWallet();
    showStatus("order-status", "Paynow payment was received, but one of your selected meals changed. The amount has been credited to your wallet so you can place the order again.", false);
    if (hasReturnFlag) window.history.replaceState({}, "", "/student/");
    return;
  }

  if (payment.status === "failed") {
    setPendingPaynowOrderTx("");
    showStatus("order-status", "Paynow payment was not completed. Your cart is still here so you can try again.", false);
    if (hasReturnFlag) window.history.replaceState({}, "", "/student/");
    return;
  }

  showStatus("order-status", "Your Paynow payment is still being processed. Refresh in a moment.");
}

async function checkPendingPaynowTopupReturn() {
  const params = new URLSearchParams(window.location.search);
  const hasReturnFlag = params.get("topup") === "processing";
  const pendingTx = getPendingPaynowTopupTx();
  if (!hasReturnFlag && !pendingTx) return;

  const data = await loadTransactionHistory();
  if (!data || !pendingTx) {
    if (hasReturnFlag) {
      showStatus("wallet-status", "Your Paynow top-up is being confirmed. Refresh in a moment and the balance will update automatically.");
    }
    return;
  }

  const payment = (data.payments || []).find((entry) => entry.tx_id === pendingTx);
  if (!payment) {
    showStatus("wallet-status", "Your Paynow top-up is still being processed. Refresh in a moment.");
    return;
  }

  if (payment.status === "succeeded" && payment.purpose === "wallet_topup") {
    setPendingPaynowTopupTx("");
    await loadWallet();
    showStatus("wallet-status", `Paynow top-up successful. Wallet updated with $${Number(payment.amount || 0).toFixed(2)}.`);
    if (id("wallet-modal-status")) {
      showStatus("wallet-modal-status", "Top-up confirmed. Your wallet balance has been updated.");
    }
    if (hasReturnFlag) window.history.replaceState({}, "", "/student/");
    return;
  }

  if (payment.status === "failed") {
    setPendingPaynowTopupTx("");
    showStatus("wallet-status", payment.meta_json?.gateway_error || "Paynow top-up was not completed.", false);
    if (id("wallet-modal-status")) {
      showStatus("wallet-modal-status", payment.meta_json?.gateway_error || "Paynow top-up was not completed.", false);
    }
    if (hasReturnFlag) window.history.replaceState({}, "", "/student/");
    return;
  }

  showStatus("wallet-status", "Your Paynow top-up is still being processed. Refresh in a moment.");
}

async function loadOrdersForStaff() {
  try {
    const orders = await req("/api/v1/orders?limit=20");
    renderStaffOrders(orders);
  } catch {
    renderStaffOrders([]);
  }
}

async function loadServedMeals() {
  try {
    const orders = await req("/api/v1/admin/served-meals");
    renderServedMeals(orders);
  } catch (err) {
    renderServedMeals([]);
    showStatus("scan-status", err.message || "Unable to load served meals.", false);
  }
}

async function loadFraudAlerts() {
  try {
    const alerts = await req("/api/v1/admin/reports/fraud-alerts");
    renderFraudAlerts(alerts);
  } catch (err) {
    renderFraudAlerts([]);
    showStatus("scan-status", err.message || "Unable to load fraud alerts.", false);
  }
}

async function loadReconciliation() {
  const selectedDate = id("reconciliation-date")?.value || "";
  try {
    const query = selectedDate ? `?date=${selectedDate}` : "";
    const data = await req(`/api/v1/admin/reports/daily-reconciliation${query}`);
    renderReconciliation(data);
  } catch (err) {
    const node = id("reconciliation-output");
    if (node) node.innerHTML = `<p class="hint">${err.message || "Unable to load reconciliation."}</p>`;
  }
}

async function loadCashDepositHistory(studentId = "") {
  try {
    const query = studentId ? `?student_id=${encodeURIComponent(studentId)}` : "";
    const items = await req(`/api/v1/admin/cash-deposits${query}`);
    renderCashDepositHistory(items);
  } catch (err) {
    renderCashDepositHistory([]);
    showStatus("cash-deposit-status", err.message || "Unable to load cash deposit history.", false);
  }
}

function setWalletMethod(method) {
  const normalizedMethod = method === "bank" ? "bank" : "ecocash";
  document.querySelectorAll(".wallet-method").forEach((button) => button.classList.toggle("active", button.dataset.walletMethod === normalizedMethod));
  document.querySelectorAll(".wallet-panel").forEach((panel) => panel.classList.toggle("active", panel.id === `wallet-panel-${normalizedMethod}` || panel.id === "wallet-panel-paynow"));
  const phoneField = id("wallet-paynow-phone");
  const bankNote = id("wallet-bank-note");
  if (phoneField) {
    phoneField.hidden = normalizedMethod === "bank";
    phoneField.required = normalizedMethod !== "bank";
    if (normalizedMethod === "bank") phoneField.value = "";
  }
  if (bankNote) {
    bankNote.hidden = normalizedMethod !== "bank";
  }
  const submitButton = id("wallet-paynow-submit");
  if (submitButton) {
    submitButton.textContent = normalizedMethod === "bank" ? "Continue with Bank" : "Continue with EcoCash";
    submitButton.dataset.walletChannel = normalizedMethod === "bank" ? "bank_card" : "mobile_money";
  }
}

function getSelectedStudentTopupMethod() {
  return document.querySelector("[data-student-topup-method].selected")?.dataset.studentTopupMethod || "ecocash";
}

function setSelectedStudentTopupMethod(method) {
  const normalizedMethod = method === "bank" ? "bank" : "ecocash";
  document.querySelectorAll("[data-student-topup-method]").forEach((button) => {
    button.classList.toggle("selected", button.dataset.studentTopupMethod === normalizedMethod);
  });
}

function syncWalletTopupAmountFromPage() {
  const pageAmount = id("student-topup-amount")?.value || "";
  if (pageAmount && id("wallet-paynow-amount")) {
    id("wallet-paynow-amount").value = pageAmount;
  }
}

function openWalletModal(method = "ecocash") {
  const modal = id("wallet-topup-modal");
  if (!modal) return;
  modal.hidden = false;
  document.body.classList.add("modal-open");
  syncWalletTopupAmountFromPage();
  setWalletMethod(method);
}

function closeWalletModal() {
  const modal = id("wallet-topup-modal");
  if (!modal) return;
  modal.hidden = true;
  document.body.classList.remove("modal-open");
  showStatus("wallet-modal-status", "", true);
}

function bindWalletModal() {
  document.querySelectorAll("[data-student-topup-method]").forEach((button) => button.addEventListener("click", () => {
    const method = button.dataset.studentTopupMethod || "ecocash";
    setSelectedStudentTopupMethod(method);
  }));
  id("wallet-topup-open-btn")?.addEventListener("click", () => {
    const amount = Number(id("student-topup-amount")?.value || 0);
    if (!amount) {
      showStatus("wallet-status", "Enter the amount you want to top up first.", false);
      return;
    }
    showStatus("wallet-status", "", true);
    openWalletModal(getSelectedStudentTopupMethod());
  });
  id("wallet-topup-card-btn")?.addEventListener("click", () => openWalletModal(getSelectedStudentTopupMethod()));
  id("wallet-topup-close-btn")?.addEventListener("click", closeWalletModal);
  document.querySelectorAll("[data-close-wallet-modal='true']").forEach((node) => node.addEventListener("click", closeWalletModal));
  document.querySelectorAll(".wallet-method").forEach((button) => button.addEventListener("click", () => setWalletMethod(button.dataset.walletMethod)));
  id("wallet-paynow-retry")?.addEventListener("click", () => {
    showStatus("wallet-modal-status", "", true);
    showStatus("wallet-status", "", true);
    id("wallet-paynow-phone")?.focus();
  });

  id("wallet-paynow-submit")?.addEventListener("click", async () => {
    const amount = Number(id("wallet-paynow-amount")?.value || 0);
    const provider = id("wallet-paynow-submit")?.dataset.walletChannel || "mobile_money";
    const phoneNumber = (id("wallet-paynow-phone")?.value || "").trim();
    if (!amount) {
      showStatus("wallet-modal-status", "Enter the top-up amount first.", false);
      return;
    }
    if (provider === "mobile_money" && !phoneNumber) {
      showStatus("wallet-modal-status", "Enter the mobile money phone number.", false);
      return;
    }
    try {
      const data = await req("/api/v1/wallet/topup/initiate", "POST", { amount, provider, phone_number: phoneNumber }, { "Idempotency-Key": nextIdempotencyKey("topup") });
      setPendingPaynowTopupTx(data.payment_transaction_id || "");
      showStatus("wallet-modal-status", provider === "mobile_money" ? "Payment request sent. Confirm it on your mobile money prompt." : "Redirecting to secure bank/card confirmation...");
      showStatus("wallet-status", `Pending USD payment started: ${data.payment_transaction_id}`);
      if (data.redirect_url && /^https?:/i.test(data.redirect_url)) {
        window.location.href = data.redirect_url;
      }
      await loadTransactionHistory();
    } catch (err) {
      if (handleAuthErrorForPage(err, 'student')) return;
      showStatus("wallet-modal-status", err.message || "Unable to start Paynow top-up.", false);
    }
  });
}

async function placeOrdersFromCart() {
  const walletButton = id("wallet-cart-btn");
  if (!cart.length) {
    showStatus("order-status", "Add at least one meal to the cart.", false);
    return;
  }
  try {
    setButtonBusy(walletButton, true, "Charging account...");
    const data = await req("/api/v1/orders", "POST", {
      items: cart.map((item) => ({ meal_id: item.id, quantity: item.qty })),
    }, { "Idempotency-Key": nextIdempotencyKey("wallet-order") });
    const createdOrders = Array.isArray(data.orders) ? data.orders : [data];
    const latestOrder = createdOrders[createdOrders.length - 1] || null;
    cart = [];
    persistCart();
    renderCart();
    await loadWallet();
    await loadTransactionHistory();
    await loadMyTickets();
    showStatus("order-status", data.detail || `Account balance payment successful for ${createdOrders.length} item(s).`);
    if (latestOrder?.order_id) {
      localStorage.setItem("last_ticket_order_id", String(latestOrder.order_id));
      setTimeout(() => {
        window.location.href = "/student-qr/";
      }, 400);
    }
  } catch (err) {
    showStatus("order-status", err.message || "Unable to create the order.", false);
  } finally {
    setButtonBusy(walletButton, false);
  }
}

async function suspendAccount() {
  const confirmed = window.confirm('Suspend this account now? This will block ordering, wallet use, and ticket redemption until reviewed by staff.');
  if (!confirmed) return;
  try {
    const data = await req('/api/v1/auth/suspend-self', 'POST', {});
    showStatus('suspend-status', data.detail || 'Your account has been suspended.');
    setTimeout(() => {
      markPortalLogout('student');
      setToken('');
      redirectToLogin('student');
    }, 800);
  } catch (err) {
    showStatus('suspend-status', err.message || 'Unable to suspend account.', false);
  }
}

function initStudentLoginPage() {
  window.__hitStudentLoginBound = true;
  setToken('');
  applyVerificationMessage('login-status');
  id('student-demo-fill-btn')?.addEventListener('click', () => {
    if (id('login-email')) id('login-email').value = 'student@hit.ac.zw';
    if (id('login-password')) id('login-password').value = 'Demo@1234';
    showStatus('login-status', 'Signing in with demo student account...');
    id('student-login-form')?.requestSubmit();
  });
  id('staff-demo-fill-btn')?.addEventListener('click', () => {
    if (id('login-email')) id('login-email').value = 'staff@hit.ac.zw';
    if (id('login-password')) id('login-password').value = 'Demo@1234';
    showStatus('login-status', 'Signing in with demo staff account...');
    id('student-login-form')?.requestSubmit();
  });
  id('admin-demo-fill-btn')?.addEventListener('click', () => {
    if (id('login-email')) id('login-email').value = 'admin@hit.ac.zw';
    if (id('login-password')) id('login-password').value = 'Demo@1234';
    showStatus('login-status', 'Signing in with demo admin account...');
    id('student-login-form')?.requestSubmit();
  });
  id('student-login-form')?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const submitButton = event.target.querySelector('button[type="submit"]');
    setButtonBusy(submitButton, true, 'Logging in...');
    showStatus('login-status', 'Checking your account...');
    const result = await loginRequest('login-email', 'login-password');
    if (result.error) {
      setButtonBusy(submitButton, false);
      showStatus('login-status', result.error, false);
      return;
    }
    showStatus('login-status', 'Login successful. Opening your portal...');
    redirectToPortalForRole(result.data?.role);
  });
}

function initStaffLoginPage() {
  window.__hitStaffLoginBound = true;
  setToken('');
  applyVerificationMessage('staff-login-status');
  id('staff-demo-fill-btn')?.addEventListener('click', () => {
    if (id('staff-login-email')) id('staff-login-email').value = 'staff@hit.ac.zw';
    if (id('staff-login-password')) id('staff-login-password').value = 'Demo@1234';
    showStatus('staff-login-status', 'Signing in with demo staff account...');
    id('staff-login-form')?.requestSubmit();
  });
  id('staff-login-form')?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const submitButton = event.target.querySelector('button[type="submit"]');
    setButtonBusy(submitButton, true, 'Logging in...');
    showStatus('staff-login-status', 'Checking your account...');
    const result = await loginRequest('staff-login-email', 'staff-login-password');
    if (result.error) {
      setButtonBusy(submitButton, false);
      showStatus('staff-login-status', result.error, false);
      return;
    }
    showStatus('staff-login-status', 'Login successful. Opening your portal...');
    window.location.replace(portalPath('staff'));
  });
}

function initRegisterPage() {
  id('register-email')?.addEventListener('blur', checkAvailability);
  id('register-university-id')?.addEventListener('blur', checkAvailability);
  id('register-form')?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const submitButton = event.target.querySelector('button[type="submit"]');
    setButtonBusy(submitButton, true, 'Creating...');
    showStatus('register-status', 'Creating account and checking details...');
    const availability = await checkAvailability();
    if (availability.emailAvailable === false || availability.universityIdAvailable === false) {
      setButtonBusy(submitButton, false);
      showStatus('register-status', 'Please fix the unavailable account details before creating the account.', false);
      return;
    }
    const payload = {
      full_name: id('register-name')?.value.trim() || '',
      university_id: id('register-university-id')?.value.trim() || '',
      email: id('register-email')?.value.trim() || '',
      password: id('register-password')?.value || '',
      role: id('register-role')?.value || 'student',
    };
    try {
      await req('/api/v1/auth/register', 'POST', payload);
      showStatus('register-status', 'Account created. Check your email to verify your HIT account.');
      event.target.reset();
      setTimeout(() => {
        window.location.replace(`/email-verification/?email=${encodeURIComponent(payload.email)}`);
      }, 700);
    } catch (err) {
      const payloadErrors = err.payload || {};
      if (payloadErrors.email) setHint('register-email-status', Array.isArray(payloadErrors.email) ? payloadErrors.email.join(', ') : String(payloadErrors.email), false);
      if (payloadErrors.university_id) setHint('register-university-id-status', Array.isArray(payloadErrors.university_id) ? payloadErrors.university_id.join(', ') : String(payloadErrors.university_id), false);
      showStatus('register-status', err.message || 'Registration failed.', false);
    } finally {
      setButtonBusy(submitButton, false);
    }
  });
}

function initStudentPage() {
  if (!guardPortalAccess('student')) return;
  bindLogout();
  const greetingNode = id('student-dashboard-greeting');
  const cachedName = localStorage.getItem('hit_student_name');
  if (greetingNode && cachedName) {
    greetingNode.textContent = 'Hello, ' + cachedName;
  }
  renderCart();
  loadWallet();
  loadMenuAndSlots();
  loadMyTickets();
  loadTransactionHistory();
  loadCurrentUserProfile().then((profile) => {
    const firstName = String(profile.full_name || 'Student').trim().split(/\\s+/)[0] || 'Student';
    localStorage.setItem('hit_student_name', firstName);
    if (greetingNode) {
      greetingNode.textContent = 'Hello, ' + firstName;
    }
  }).catch(() => {});
  bindWalletModal();
  id('checkout-cart-btn')?.addEventListener('click', placeOrdersFromCart);
  id('suspend-account-btn')?.addEventListener('click', suspendAccount);
  checkPendingPaynowTopupReturn();
  checkPendingPaynowOrderReturn();
}

function initStaffScannerPage() {
  if (!guardPortalAccess('staff')) return;
  bindLogout();
  let scanner = null;
  let scannerActive = false;
  let scanLocked = false;

  const startWithCamera = async () => {
    if (scanner && scannerActive) return;
    scanner = scanner || new Html5Qrcode('scanner-reader');
    const onScanSuccess = async (decodedText) => {
      if (scanLocked) return;
      scanLocked = true;
      if (id('scanner-manual-token')) id('scanner-manual-token').value = decodedText;
      await validateTicketToken(decodedText, 'scanner-status');
      await stopScanner();
      setTimeout(() => {
        scanLocked = false;
      }, 600);
    };

    const config = { fps: 10, qrbox: { width: 220, height: 220 } };
    try {
      await scanner.start({ facingMode: { exact: 'environment' } }, config, onScanSuccess, () => {});
      return;
    } catch (_) {
      try {
        await scanner.start({ facingMode: 'environment' }, config, onScanSuccess, () => {});
        return;
      } catch (_) {
        const cameras = await Html5Qrcode.getCameras();
        if (!cameras || !cameras.length) {
          throw new Error('No camera was found on this device.');
        }
        const rearCamera = cameras.find((camera) => /back|rear|environment/i.test(camera.label || '')) || cameras[0];
        await scanner.start(rearCamera.id, config, onScanSuccess, () => {});
      }
    }
  };

  const stopScanner = async () => {
    if (scanner && scannerActive) {
      await scanner.stop();
      await scanner.clear();
      scannerActive = false;
      scanLocked = false;
      showStatus('scanner-status', 'Camera stopped.');
    }
  };

  id('stop-scanner-btn')?.addEventListener('click', async () => {
    try {
      await stopScanner();
    } catch (err) {
      showStatus('scanner-status', err.message || 'Unable to stop camera.', false);
    }
  });

  id('scanner-manual-validate-btn')?.addEventListener('click', async () => {
    const tokenValue = id('scanner-manual-token')?.value.trim() || '';
    await validateTicketToken(tokenValue, 'scanner-status');
  });

  id('start-scanner-btn')?.addEventListener('click', async () => {
    if (!window.Html5Qrcode) {
      showStatus('scanner-status', 'QR scanner library did not load. Refresh the page and try again.', false);
      renderScannerResult('invalid', 'Scanner unavailable', 'The browser QR scanner library did not load.');
      return;
    }
    try {
      if (scanner && scannerActive) {
        showStatus('scanner-status', 'Camera is already running.');
        return;
      }
      await startWithCamera();
      scannerActive = true;
      showStatus('scanner-status', 'Camera started. Point it at a QR ticket.');
      renderScannerResult('pending', 'Scanner active', 'Point the camera at a QR ticket to validate it.');
    } catch (err) {
      showStatus('scanner-status', err.message || 'Unable to access the camera.', false);
      renderScannerResult('invalid', 'Scanner error', err.message || 'Unable to access the camera.');
    }
  });

  window.addEventListener('beforeunload', () => {
    if (scanner && scannerActive) {
      scanner.stop().catch(() => {});
    }
  });
}

function initStaffPage() {
  if (!guardPortalAccess('staff')) return;
  bindLogout();
  applyCurrentUserGreeting('staff-dashboard-greeting', 'Staff');
  loadMenuAndSlots();
  loadCashDepositHistory();
  renderCashStudentPreview(null);

  const toolSection = id('service-tools-section');
  const toolCards = Array.from(document.querySelectorAll('#service-tools-section .staff-service-card'));
  const dashboardSections = Array.from(document.querySelectorAll('.staff-mobile-content > section')).filter((section) => section.id !== 'service-tools-section');
  const dashboardTargets = Array.from(document.querySelectorAll('.staff-dashboard-target'));
  const homeSections = Array.from(document.querySelectorAll('[data-staff-home-section]'));
  const toolTriggers = Array.from(document.querySelectorAll('[data-staff-tool]'));
  const dashboardTriggers = Array.from(document.querySelectorAll('[data-staff-dashboard]'));
  const homeTrigger = document.querySelector('[data-staff-home]');
  const setActiveStaffToolTrigger = (targetId) => {
    toolTriggers.forEach((trigger) => {
      trigger.classList.toggle('active', trigger.dataset.staffTool === targetId);
    });
    dashboardTriggers.forEach((trigger) => {
      trigger.classList.toggle('active', false);
    });
    homeTrigger?.classList.toggle('active', !targetId);
  };
  const setActiveStaffDashboardTrigger = (targetId) => {
    toolTriggers.forEach((trigger) => {
      trigger.classList.toggle('active', false);
    });
    dashboardTriggers.forEach((trigger) => {
      trigger.classList.toggle('active', trigger.dataset.staffDashboard === targetId);
    });
    homeTrigger?.classList.toggle('active', false);
  };
  const collapseStaffTools = () => {
    if (!toolSection) return;
    toolSection.classList.add('is-collapsed');
    toolSection.classList.remove('is-focused');
    dashboardSections.forEach((section) => { section.hidden = false; });
    homeSections.forEach((section) => { section.hidden = false; });
    dashboardTargets.forEach((section) => { section.classList.add('is-collapsed'); });
    toolCards.forEach((card) => { card.hidden = false; });
    setActiveStaffToolTrigger('');
    if (window.location.hash) {
      history.replaceState(null, '', window.location.pathname + window.location.search);
    }
  };
  const showStaffDashboardTarget = (targetId, shouldScroll = true) => {
    collapseStaffTools();
    const targetSection = id(targetId);
    if (!targetSection) return;
    homeSections.forEach((section) => { section.hidden = true; });
    if (targetSection.classList.contains('staff-dashboard-target')) {
      targetSection.classList.remove('is-collapsed');
    }
    setActiveStaffDashboardTrigger(targetId);
    if (window.location.hash !== `#${targetId}`) {
      history.replaceState(null, '', `#${targetId}`);
    }
    if (shouldScroll) {
      targetSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  };
  const openStaffTool = (targetId, shouldScroll = true) => {
    if (!toolSection || !targetId) return;
    const targetCard = id(targetId);
    if (!targetCard) return;
    toolSection.classList.remove('is-collapsed');
    toolSection.classList.add('is-focused');
    dashboardSections.forEach((section) => { section.hidden = true; });
    toolCards.forEach((card) => {
      card.hidden = card.id !== targetId;
    });
    setActiveStaffToolTrigger(targetId);
    if (window.location.hash !== `#${targetId}`) {
      history.replaceState(null, '', `#${targetId}`);
    }
    if (shouldScroll) {
      targetCard.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  };

  toolTriggers.forEach((trigger) => {
    trigger.addEventListener('click', (event) => {
      event.preventDefault();
      openStaffTool(trigger.dataset.staffTool);
    });
  });
  homeTrigger?.addEventListener('click', (event) => {
    event.preventDefault();
    collapseStaffTools();
    window.scrollTo({ top: 0, behavior: 'smooth' });
  });
  dashboardTriggers.forEach((trigger) => {
    trigger.addEventListener('click', (event) => {
      event.preventDefault();
      showStaffDashboardTarget(trigger.dataset.staffDashboard);
    });
  });

  const initialToolId = (window.location.hash || '').replace(/^#/, '');
  if (initialToolId && toolCards.some((card) => card.id === initialToolId)) {
    openStaffTool(initialToolId, false);
  } else if (initialToolId && dashboardSections.some((section) => section.id === initialToolId)) {
    showStaffDashboardTarget(initialToolId, false);
  } else {
    collapseStaffTools();
  }

  const sections = Array.from(document.querySelectorAll('.staff-section'));
  const tiles = Array.from(document.querySelectorAll('.staff-tile'));
  const activateStaffSection = (target, shouldScroll = true) => {
    sections.forEach((section) => section.classList.toggle('active', section.id === target));
    tiles.forEach((tile) => tile.classList.toggle('active', tile.dataset.target === target));
    if (shouldScroll) {
      document.getElementById(target)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  };
  tiles.forEach((tile) => {
    tile.addEventListener('click', () => activateStaffSection(tile.dataset.target));
  });
  if (sections[0]) activateStaffSection(sections[0].id, false);

  id('load-staff-orders-btn')?.addEventListener('click', async (event) => {
    const button = event.currentTarget;
    setButtonBusy(button, true, 'Loading...');
    try { await loadOrdersForStaff(); } finally { setButtonBusy(button, false); }
  });
  id('load-served-meals-btn')?.addEventListener('click', async (event) => {
    const button = event.currentTarget;
    setButtonBusy(button, true, 'Loading...');
    try { await loadServedMeals(); } finally { setButtonBusy(button, false); }
  });
  id('load-fraud-alerts-btn')?.addEventListener('click', async (event) => {
    const button = event.currentTarget;
    setButtonBusy(button, true, 'Loading...');
    try { await loadFraudAlerts(); } finally { setButtonBusy(button, false); }
  });
  id('load-reconciliation-btn')?.addEventListener('click', async (event) => {
    const button = event.currentTarget;
    setButtonBusy(button, true, 'Loading...');
    try { await loadReconciliation(); } finally { setButtonBusy(button, false); }
  });
  id('load-forecast-btn')?.addEventListener('click', async (event) => {
    const button = event.currentTarget;
    const selectedDate = id('forecast-date')?.value || addDaysIso(new Date(), 1);
    setButtonBusy(button, true, 'Loading...');
    try { await loadDemandForecast(selectedDate); await loadForecastOutlook(selectedDate); } finally { setButtonBusy(button, false); }
  });

  id('cash-student-search-btn')?.addEventListener('click', async (event) => {
    const button = event.currentTarget;
    const studentId = (id('cash-student-id')?.value || '').trim();
    if (!studentId) {
      showStatus('cash-deposit-status', 'Enter a Student ID first.', false);
      renderCashStudentPreview(null);
      return;
    }
    setButtonBusy(button, true, 'Searching...');
    showStatus('cash-deposit-status', 'Looking up student account...');
    try {
      const student = await req(`/api/v1/admin/students/lookup?student_id=${encodeURIComponent(studentId)}`);
      renderCashStudentPreview(student);
      showStatus('cash-deposit-status', `Student found: ${student.full_name}`);
      await loadCashDepositHistory(studentId);
    } catch (err) {
      renderCashStudentPreview(null);
      renderCashDepositHistory([]);
      showStatus('cash-deposit-status', err.message || 'Unable to find student.', false);
    } finally {
      setButtonBusy(button, false);
    }
  });

  id('cash-deposit-btn')?.addEventListener('click', async (event) => {
    const button = event.currentTarget;
    const studentId = (id('cash-student-id')?.value || '').trim();
    const amount = id('cash-deposit-amount')?.value || '';
    if (!studentId || !amount) {
      showStatus('cash-deposit-status', 'Enter Student ID and deposit amount.', false);
      return;
    }
    setButtonBusy(button, true, 'Depositing...');
    showStatus('cash-deposit-status', 'Processing cash deposit...');
    try {
      const result = await req('/api/v1/admin/cash-deposits', 'POST', { student_id: studentId, amount });
      showStatus('cash-deposit-status', result.detail || 'Deposit successful. Student wallet updated.');
      renderCashStudentPreview({
        student_id: result.student_id,
        full_name: result.student_name,
        email: '',
        wallet_balance: result.wallet_balance,
      });
      if (id('cash-deposit-amount')) id('cash-deposit-amount').value = '';
      await loadCashDepositHistory(studentId);
    } catch (err) {
      showStatus('cash-deposit-status', err.message || 'Unable to process deposit.', false);
    } finally {
      setButtonBusy(button, false);
    }
  });

  id('add-meal-form')?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const submitButton = event.target.querySelector('button[type="submit"]');
    setButtonBusy(submitButton, true, 'Adding...');
    showStatus('meal-status', 'Saving meal to the live menu...');
    try {
      const imageFile = id('meal-image')?.files?.[0] || null;
      const payload = {
        name: id('meal-name')?.value || '',
        description: id('meal-description')?.value || '',
        price: id('meal-price')?.value || '',
        stock_quantity: id('meal-stock')?.value || 50,
        image_data: imageFile ? await fileToDataUrl(imageFile) : '',
        active: true,
      };
      await req('/api/v1/menu', 'POST', payload);
      showStatus('meal-status', 'Meal added successfully.');
      event.target.reset();
      if (id('meal-stock')) id('meal-stock').value = 50;
      loadMenuAndSlots();
    } catch (err) {
      showStatus('meal-status', err.message || 'Unable to add meal.', false);
    } finally {
      setButtonBusy(submitButton, false);
    }
  });

  id('scan-validate-btn')?.addEventListener('click', async (event) => {
    const button = event.currentTarget;
    const tokenValue = id('scan-token')?.value.trim() || '';
    setButtonBusy(button, true, 'Checking...');
    showStatus('scan-status', 'Validating ticket...');
    try {
      await validateTicketToken(tokenValue, 'scan-status');
    } finally {
      setButtonBusy(button, false);
    }
  });

  id('walkin-serve-btn')?.addEventListener('click', async (event) => {
    const button = event.currentTarget;
    const customer = id('walkin-name')?.value || 'Walk-in';
    const mealId = Number(id('walkin-meal-id')?.value || 0);
    const quantity = Number(id('walkin-qty')?.value || 1);
    if (!mealId) {
      showStatus('walkin-status', 'Select a meal first.', false);
      return;
    }
    setButtonBusy(button, true, 'Serving...');
    showStatus('walkin-status', 'Recording walk-in order...');
    try {
      const result = await req('/api/v1/orders/walkin', 'POST', { meal_id: mealId, quantity, customer_name: customer });
      showStatus('walkin-status', result.detail || `Walk-in order recorded for ${customer}.`);
      await loadMenuAndSlots();
    } catch (err) {
      showStatus('walkin-status', err.message || 'Unable to record walk-in order.', false);
    } finally {
      setButtonBusy(button, false);
    }
  });
}

function init() {
  if (page() === 'student-login') return initStudentLoginPage();
  if (page() === 'staff-login') return initStaffLoginPage();
  if (page() === 'register') return initRegisterPage();
  if (page() === 'student') return initStudentPage();
  if (page() === 'staff') return initStaffPage();
  if (page() === 'staff-scanner') return initStaffScannerPage();
}

window.addEventListener('DOMContentLoaded', init);

























function initHitUiEnhancements() {
  document.querySelectorAll('[data-toggle-password]').forEach((button) => {
    button.addEventListener('click', () => {
      const targetId = button.dataset.togglePassword;
      const input = document.getElementById(targetId);
      if (!input) return;
      const show = input.type === 'password';
      input.type = show ? 'text' : 'password';
      button.textContent = show ? 'Hide' : 'Show';
    });
  });

  document.querySelectorAll('.hit-method-card').forEach((card) => {
    card.addEventListener('click', () => {
      const group = card.parentElement;
      if (!group) return;
      group.querySelectorAll('.hit-method-card').forEach((item) => item.classList.remove('selected'));
      card.classList.add('selected');
    });
  });
}

window.addEventListener('DOMContentLoaded', initHitUiEnhancements);

function formatCurrency(value) {
  return `$${Number(value || 0).toFixed(2)}`;
}

function formatDateTime(value) {
  if (!value) return "-";
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

function csvCell(value) {
  return `"${String(value ?? "").replace(/"/g, '""')}"`;
}

function setDisabled(button, disabled) {
  if (!button) return;
  button.disabled = !!disabled;
  button.setAttribute('aria-disabled', disabled ? 'true' : 'false');
}

function downloadCsvFile(filename, rows) {
  const csv = `\ufeff${rows.map((row) => row.map(csvCell).join(",")).join("\n")}`;
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function openPrintWindow(title, bodyHtml) {
  const popup = window.open("", "_blank", "width=980,height=760");
  if (!popup) return false;
  popup.document.write(`<!doctype html>
    <html lang="en">
      <head>
        <meta charset="UTF-8" />
        <title>${escapeHtml(title)}</title>
        <style>
          body { font-family: Arial, sans-serif; color: #1f2937; padding: 24px; }
          h1 { color: #0F4C9C; margin-bottom: 8px; }
          h2 { color: #0F4C9C; margin: 24px 0 8px; }
          p { margin: 4px 0 12px; }
          table { width: 100%; border-collapse: collapse; margin-top: 12px; }
          th, td { border: 1px solid #E5E7EB; padding: 10px; text-align: left; }
          th { background: #F5F7FA; }
          .summary { display: grid; grid-template-columns: repeat(2, minmax(180px, 1fr)); gap: 12px; margin: 18px 0; }
          .summary-card { border: 1px solid #E5E7EB; border-radius: 12px; padding: 14px; }
          .muted { color: #6B7280; }
          @media print { body { padding: 0; } }
        </style>
      </head>
      <body>
        ${bodyHtml}
      </body>
    </html>`);
  popup.document.close();
  popup.focus();
  popup.print();
  return true;
}
async function loadCurrentUserProfile() {
  return req('/api/v1/auth/me');
}

function applyCurrentUserGreeting(elementId, fallbackLabel) {
  const node = id(elementId);
  if (!node) return;
  const roleKey = String(fallbackLabel || 'User').toLowerCase();
  const cacheKey = `hit_${roleKey}_name`;
  const cachedName = localStorage.getItem(cacheKey);
  if (cachedName) {
    node.textContent = 'Hello, ' + cachedName;
  }
  loadCurrentUserProfile().then((profile) => {
    const firstName = String(profile.full_name || fallbackLabel || 'User').trim().split(/\s+/)[0] || fallbackLabel || 'User';
    localStorage.setItem(cacheKey, firstName);
    node.textContent = 'Hello, ' + firstName;
  }).catch(() => {});
}

function mealCategory(meal) {
  const explicit = String(meal?.category || '').trim();
  if (explicit) return explicit === 'Snacks' ? 'Meals' : explicit;
  const name = String(meal?.name || '').toLowerCase();
  const description = String(meal?.description || '').toLowerCase();
  if (name.includes('water') || name.includes('orange') || name.includes('juice') || name.includes('drink')) return 'Drinks';
  return 'Meals';
}

function renderDashboardMenuCards(meals) {
  const list = id('menu-list');
  if (!list) return;
  list.innerHTML = meals.length ? meals.map((meal) => `
    <article class="hit-menu-card">
      <div class="hit-menu-card__image">${mealImageMarkup(meal)}</div>
      <span class="hit-badge ${mealCategory(meal) === 'Meals' ? 'hit-badge--gold' : ''}">${escapeHtml(mealCategory(meal))}</span>
      <h3>${escapeHtml(meal.name)}</h3>
      <p class="hit-muted">${escapeHtml(meal.description || 'Fresh canteen item')}</p>
      <div class="hit-list-row"><span class="hit-menu-card__price">${formatCurrency(meal.price)}</span><button class="hit-btn" type="button" data-add-meal-id="${meal.id}">Add to Order</button></div>
    </article>
  `).join('') : '<div class="hit-empty-state">No menu items available.</div>';
  list.querySelectorAll('[data-add-meal-id]').forEach((button) => {
    button.addEventListener('click', () => {
      const meal = meals.find((item) => Number(item.id) === Number(button.dataset.addMealId));
      if (meal) addToCart(meal);
    });
  });
}

async function hydrateStudentMenuPage() {
  if (!token) return redirectToLogin('student');
  bindLogout();
  const searchInput = id('menu-search');
  const filterTabs = id('menu-filter-tabs');
  const tabButtons = Array.from(document.querySelectorAll('.hit-tab'));
  const setActiveTab = (label) => {
    tabButtons.forEach((item) => item.classList.toggle('active', item.textContent.trim() === label));
  };
  const syncSearchUi = () => {
    const hasQuery = !!String(searchInput?.value || '').trim();
    filterTabs?.classList.toggle('is-hidden-by-search', hasQuery);
  };
  const getActiveCategory = () => {
    const active = tabButtons.find((button) => button.classList.contains('active'));
    return (active?.textContent || 'All').trim();
  };
  const applyMenuFilters = (allMeals) => {
    const query = String(searchInput?.value || '').trim().toLowerCase();
    syncSearchUi();
    const activeCategory = getActiveCategory();
    const filtered = allMeals.filter((meal) => {
      const category = mealCategory(meal);
      const matchesCategory = activeCategory === 'All' || category === activeCategory;
      const haystack = `${meal.name || ''} ${meal.description || ''} ${category}`.toLowerCase();
      const matchesSearch = !query || haystack.includes(query);
      return matchesCategory && matchesSearch;
    });
    renderDashboardMenuCards(filtered);
  };
  try {
    const fetchedMeals = await req('/api/v1/menu');
    const allMeals = fetchedMeals.length ? fetchedMeals : demoMeals;
    applyMenuFilters(allMeals);
    searchInput?.addEventListener('input', () => applyMenuFilters(allMeals));
    tabButtons.forEach((button) => {
      button.addEventListener('click', () => {
        const isAlreadyActive = button.classList.contains('active');
        const label = button.textContent.trim();
        setActiveTab(isAlreadyActive && label !== 'All' ? 'All' : label);
        applyMenuFilters(allMeals);
      });
    });
  } catch {
    applyMenuFilters(demoMeals);
    searchInput?.addEventListener('input', () => applyMenuFilters(demoMeals));
    tabButtons.forEach((button) => {
      button.addEventListener('click', () => {
        const isAlreadyActive = button.classList.contains('active');
        const label = button.textContent.trim();
        setActiveTab(isAlreadyActive && label !== 'All' ? 'All' : label);
        applyMenuFilters(demoMeals);
      });
    });
  }
}

async function hydrateStudentCartPage() {
  if (!token) return redirectToLogin('student');
  bindLogout();
  renderCart();
  await loadWallet();
  id('wallet-cart-btn')?.addEventListener('click', placeOrdersFromCart);
}

async function hydrateStudentTransactionsPage() {
  if (!token) return redirectToLogin('student');
  bindLogout();
  await loadTransactionHistory();
}

async function hydrateStudentProfilePage() {
  if (!token) return redirectToLogin('student');
  bindLogout();

  const fillProfile = async () => {
    const profile = await loadCurrentUserProfile();
    if (id('profile-name')) id('profile-name').textContent = profile.full_name;
    if (id('profile-meta')) id('profile-meta').textContent = `${profile.student_id} - ${profile.email}`;
    if (id('profile-full-name-input')) id('profile-full-name-input').value = profile.full_name || '';
    if (id('profile-email-input')) id('profile-email-input').value = profile.email || '';
    if (id('profile-status-badge')) {
      id('profile-status-badge').textContent = profile.is_suspended ? 'Suspended' : (profile.is_email_verified ? 'Verified' : 'Pending');
      id('profile-status-badge').className = `hit-badge ${profile.is_suspended ? 'hit-badge--danger' : 'hit-badge--success'}`;
    }
    return profile;
  };

  try {
    await fillProfile();
  } catch (err) {
    showStatus('profile-update-status', err.message || 'Unable to load your account details.', false);
  }

  id('profile-update-form')?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const button = id('profile-save-btn');
    try {
      setButtonBusy(button, true, 'Saving...');
      const data = await req('/api/v1/auth/me/update', 'PATCH', {
        full_name: id('profile-full-name-input')?.value || '',
        email: id('profile-email-input')?.value || '',
      });
      showStatus('profile-update-status', data.detail || 'Account updated successfully.');
      await fillProfile();
    } catch (err) {
      showStatus('profile-update-status', err.message || 'Unable to update account.', false);
    } finally {
      setButtonBusy(button, false);
    }
  });

  id('password-change-form')?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const button = id('change-password-btn');
    try {
      setButtonBusy(button, true, 'Updating...');
      const data = await req('/api/v1/auth/change-password', 'POST', {
        current_password: id('current-password-input')?.value || '',
        new_password: id('new-password-input')?.value || '',
        confirm_password: id('confirm-password-input')?.value || '',
      });
      showStatus('password-change-status', data.detail || 'Password changed successfully. Please log in again.');
      event.target.reset();
      setTimeout(() => {
        markPortalLogout('student');
        setToken('');
        window.location.replace('/');
      }, 900);
    } catch (err) {
      showStatus('password-change-status', err.message || 'Unable to change password.', false);
    } finally {
      setButtonBusy(button, false);
    }
  });
}

function parseStudentPaymentPayload(decodedText) {
  const fallback = {
    meal: 'Campus Meal',
    amount: null,
  };
  try {
    const parsed = JSON.parse(decodedText);
    return {
      meal: parsed.meal || parsed.name || fallback.meal,
      amount: Number.isFinite(Number(parsed.amount)) ? Number(parsed.amount) : null,
    };
  } catch (_) {
    try {
      const url = new URL(decodedText);
      return {
        meal: url.searchParams.get('meal') || fallback.meal,
        amount: Number.isFinite(Number(url.searchParams.get('amount'))) ? Number(url.searchParams.get('amount')) : null,
      };
    } catch (_) {
      return fallback;
    }
  }
}

function renderStudentPayOverlay(meta = {}) {
  const overlay = id('student-pay-overlay');
  const metaNode = id('student-pay-overlay-meta');
  if (!overlay) return;
  overlay.hidden = false;
  if (metaNode) {
    const parts = [];
    if (meta.meal) parts.push(meta.meal);
    if (meta.amount !== null && meta.amount !== undefined && Number.isFinite(Number(meta.amount))) {
      parts.push(`Wallet charged ${formatCurrency(Number(meta.amount))}`);
    } else {
      parts.push('Wallet payment approved');
    }
    metaNode.textContent = parts.join(' â€¢ ');
  }
}

function initStudentPayScannerPage() {
  if (!guardPortalAccess('student')) return;
  bindLogout();
  let scanner = null;
  let scannerActive = false;
  let scanLocked = false;

  const walletNode = id('student-pay-wallet-balance');
  const setWalletText = () => {
    if (walletNode) walletNode.textContent = formatCurrency(walletBalance());
  };
  setWalletText();
  loadWallet().finally(setWalletText);

  const stopScanner = async () => {
    if (scanner && scannerActive) {
      await scanner.stop();
      await scanner.clear();
      scannerActive = false;
      scanLocked = false;
      showStatus('student-pay-status', 'Camera stopped.');
    }
  };

  const onScanSuccess = async (decodedText) => {
    if (scanLocked) return;
    scanLocked = true;
    const meta = parseStudentPaymentPayload(decodedText);
    renderStudentPayOverlay(meta);
    triggerScannerFeedback('success');
    showStatus('student-pay-status', 'Payment successful.');
    await stopScanner();
  };

  const startWithCamera = async () => {
    scanner = scanner || new Html5Qrcode('student-pay-reader');
    const config = { fps: 10, qrbox: { width: 240, height: 240 } };
    try {
      await scanner.start({ facingMode: { exact: 'environment' } }, config, onScanSuccess, () => {});
      return;
    } catch (_) {
      try {
        await scanner.start({ facingMode: 'environment' }, config, onScanSuccess, () => {});
        return;
      } catch (_) {
        const cameras = await Html5Qrcode.getCameras();
        if (!cameras || !cameras.length) throw new Error('No camera was found on this device.');
        const rearCamera = cameras.find((camera) => /back|rear|environment/i.test(camera.label || '')) || cameras[0];
        await scanner.start(rearCamera.id, config, onScanSuccess, () => {});
      }
    }
  };

  id('student-pay-start-btn')?.addEventListener('click', async () => {
    if (!window.Html5Qrcode) {
      showStatus('student-pay-status', 'QR scanner library did not load. Refresh and try again.', false);
      return;
    }
    try {
      if (scanner && scannerActive) {
        showStatus('student-pay-status', 'Camera is already running.');
        return;
      }
      await startWithCamera();
      scannerActive = true;
      showStatus('student-pay-status', 'Camera started. Scan the meal QR code.');
    } catch (err) {
      showStatus('student-pay-status', err.message || 'Unable to access the camera.', false);
      triggerScannerFeedback('error');
    }
  });

  id('student-pay-stop-btn')?.addEventListener('click', async () => {
    try {
      await stopScanner();
      const overlay = id('student-pay-overlay');
      if (overlay) overlay.hidden = true;
    } catch (err) {
      showStatus('student-pay-status', err.message || 'Unable to stop the camera.', false);
    }
  });

  window.addEventListener('beforeunload', () => {
    if (scanner && scannerActive) {
      scanner.stop().catch(() => {});
    }
  });
}
async function hydrateStudentAddMoneyPage() {
  if (!token) return redirectToLogin('student');
  bindLogout();
  await loadWallet();
  setSelectedStudentTopupMethod(getSelectedStudentTopupMethod());
  setWalletMethod(getSelectedStudentTopupMethod());
  bindWalletModal();
  await checkPendingPaynowTopupReturn();
}
async function hydrateStudentQrPage() {
  if (!token) return redirectToLogin('student');
  bindLogout();

  const renderCurrentTicket = async () => {
    try {
      const profile = await loadCurrentUserProfile();
      if (id('student-qr-name')) id('student-qr-name').textContent = profile.full_name || 'Student';
    } catch {}

    await loadLatestTickets();
    const qrBox = id('student-qr-box');
    if (!qrBox) return;

    if (!latestTickets.length) {
      qrBox.innerHTML = '<div class="hit-empty-state">No active QR ticket yet. Complete an order and your QR will appear here.</div>';
      if (id('student-qr-meta')) id('student-qr-meta').textContent = 'No active ticket';
      return;
    }

    const ticket = latestTickets[0];
    qrBox.innerHTML = `<div class="ticket-card__qr hit-qr-live">${ticket.ticket_qr_svg || ticket.qr_svg || '<div class="hit-empty-state">QR unavailable for this ticket.</div>'}</div>`;
    if (id('student-qr-meta')) {
      const expiresText = ticket.expires_at ? `Valid until ${new Date(ticket.expires_at).toLocaleString()}` : 'Ticket issued';
      id('student-qr-meta').textContent = `${ticket.order_ref || ticket.ticket_id} | ${expiresText}`;
    }
  };

  id('student-qr-refresh')?.addEventListener('click', renderCurrentTicket);
  await renderCurrentTicket();
}

function renderAdminTableRows(targetId, rows, columns, emptyMessage = 'No records available.') {
  const body = id(targetId);
  if (!body) return;
  if (!rows.length) {
    body.innerHTML = `<tr><td colspan="${columns.length}">${emptyMessage}</td></tr>`;
    return;
  }
  body.innerHTML = rows.map((row) => `<tr>${columns.map((column) => `<td>${row[column] ?? ''}</td>`).join('')}</tr>`).join('');
}
async function hydrateAdminStudents() {
  if (!token) return window.location.replace('/admin-login/');
  const load = async () => {
    const q = id('admin-students-search')?.value || '';
    try {
      const items = await req(`/api/v1/admin/students?q=${encodeURIComponent(q)}`);
      const rows = items.map((item) => ({
        name: escapeHtml(item.name),
        student_id: escapeHtml(item.student_id),
        email: escapeHtml(item.email),
        balance: formatCurrency(item.balance),
        status: `<span class="hit-badge ${String(item.status).toLowerCase().includes('suspend') ? 'hit-badge--danger' : 'hit-badge--success'}">${escapeHtml(item.status)}</span>`,
        actions: `
          <button
            class="${item.is_suspended ? 'hit-btn-secondary' : 'hit-btn-danger'}"
            type="button"
            data-admin-student-action="${item.is_suspended ? 'activate' : 'suspend'}"
            data-admin-student-id="${item.id}"
            data-admin-student-name="${escapeHtml(item.name)}"
          >${item.is_suspended ? 'Activate' : 'Suspend'}</button>
        `,
      }));
      renderAdminTableRows('admin-students-body', rows, ['name', 'student_id', 'email', 'balance', 'status', 'actions']);
      id('admin-students-body')?.querySelectorAll('[data-admin-student-action]').forEach((button) => {
        button.addEventListener('click', async () => {
          const action = String(button.dataset.adminStudentAction || '').trim().toLowerCase();
          const studentId = button.dataset.adminStudentId;
          const studentName = button.dataset.adminStudentName || 'this student';
          const verb = action === 'activate' ? 'activate' : 'suspend';
          if (!window.confirm(`Do you want to ${verb} ${studentName}?`)) return;
          try {
            setButtonBusy(button, true, action === 'activate' ? 'Activating...' : 'Suspending...');
            const response = await req(`/api/v1/admin/students/${studentId}/status`, 'PATCH', { action });
            showStatus('admin-students-status', response.detail || `Student account ${verb}d successfully.`);
            await load();
          } catch (err) {
            showStatus('admin-students-status', err.message || `Unable to ${verb} this student right now.`, false);
          } finally {
            setButtonBusy(button, false);
          }
        });
      });
      showStatus('admin-students-status', `${items.length} student records loaded.`);
    } catch (err) {
      showStatus('admin-students-status', err.message || 'Unable to load students.', false);
    }
  };
  id('admin-students-search')?.addEventListener('input', load);
  id('admin-add-student-btn')?.addEventListener('click', () => {
    showStatus('admin-students-status', 'Student creation form can be wired next. Search and reporting are live now.');
  });
  await load();
}

async function hydrateAdminStaff() {
  if (!token) return window.location.replace('/admin-login/');
  const load = async () => {
    const q = id('admin-staff-search')?.value || '';
    try {
      const items = await req(`/api/v1/admin/staff-members?q=${encodeURIComponent(q)}`);
      renderAdminTableRows('admin-staff-body', items.map((item) => ({
        name: escapeHtml(item.name),
        email: escapeHtml(item.email),
        role: escapeHtml(item.role),
        status: `<span class="hit-badge ${String(item.status).toLowerCase().includes('suspend') ? 'hit-badge--danger' : 'hit-badge--success'}">${escapeHtml(item.status)}</span>`,
        actions: 'View ï¿½ Edit',
      })), ['name', 'email', 'role', 'status', 'actions']);
      showStatus('admin-staff-status', `${items.length} staff records loaded.`);
    } catch (err) {
      showStatus('admin-staff-status', err.message || 'Unable to load staff members.', false);
    }
  };
  id('admin-staff-search')?.addEventListener('input', load);
  id('admin-add-staff-btn')?.addEventListener('click', () => {
    showStatus('admin-staff-status', 'Staff creation form can be wired next. Search and reporting are live now.');
  });
  await load();
}

async function hydrateAdminFood() {
  if (!token) return window.location.replace('/admin-login/');
  const grid = id('admin-food-grid');
  if (!grid) return;
  const load = async () => {
    try {
      const items = await req('/api/v1/admin/food-items');
      grid.innerHTML = items.map((item) => `
        <article class="hit-menu-card" data-admin-food-id="${item.id}" data-admin-food-name="${escapeHtml(item.name)}" data-admin-food-price="${item.price}" data-admin-food-stock="${item.stock_quantity}" data-admin-food-active="${item.availability === 'Active' ? 'true' : 'false'}">
          <div class="hit-menu-card__image">${mealImageMarkup(item)}</div>
          <span class="hit-badge ${item.category === 'Meals' ? 'hit-badge--gold' : ''}">${escapeHtml(item.category)}</span>
          <h3>${escapeHtml(item.name)}</h3>
          <p class="hit-muted">${formatCurrency(item.price)} | ${escapeHtml(item.availability)} | Stock ${item.stock_quantity}</p>
          <div class="hit-inline-actions">
            <button class="hit-btn-secondary" type="button" data-admin-food-action="edit" data-admin-food-id="${item.id}">Edit</button>
            <button class="hit-btn-danger" type="button" data-admin-food-action="delete" data-admin-food-id="${item.id}">Delete</button>
          </div>
        </article>
      `).join('');
      showStatus('admin-food-status', `${items.length} food items loaded.`);

      grid.querySelectorAll('[data-admin-food-action="edit"]').forEach((button) => {
        button.addEventListener('click', async () => {
          const mealCard = button.closest('[data-admin-food-id]');
          const mealId = button.dataset.adminFoodId;
          const currentName = mealCard?.dataset.adminFoodName || '';
          const currentPrice = mealCard?.dataset.adminFoodPrice || '';
          const currentStock = mealCard?.dataset.adminFoodStock || '0';

          const nextName = window.prompt('Edit meal name', currentName);
          if (nextName === null) return;
          const nextPrice = window.prompt('Edit price', String(currentPrice));
          if (nextPrice === null) return;
          const nextStock = window.prompt('Edit stock quantity', String(currentStock));
          if (nextStock === null) return;
          if (!window.confirm(`Save changes to ${nextName.trim() || currentName}?`)) {
            showStatus('admin-food-status', 'Edit cancelled.', false);
            return;
          }

          try {
            await req(`/api/v1/menu/${mealId}`, 'PATCH', {
              name: nextName.trim(),
              price: Number(nextPrice),
              stock_quantity: Number(nextStock),
            });
            showStatus('admin-food-status', 'Food item updated successfully.');
            await load();
          } catch (err) {
            showStatus('admin-food-status', err.message || 'Unable to update the food item.', false);
          }
        });
      });

      grid.querySelectorAll('[data-admin-food-action="delete"]').forEach((button) => {
        button.addEventListener('click', async () => {
          const mealCard = button.closest('[data-admin-food-id]');
          const mealName = mealCard?.dataset.adminFoodName || 'this meal';
          if (!window.confirm(`Delete ${mealName} from the menu?`)) return;
          try {
            await req(`/api/v1/menu/${button.dataset.adminFoodId}`, 'DELETE');
            showStatus('admin-food-status', 'Food item removed from the active menu.');
            await load();
          } catch (err) {
            showStatus('admin-food-status', err.message || 'Unable to delete the food item.', false);
          }
        });
      });
    } catch (err) {
      showStatus('admin-food-status', err.message || 'Unable to load food items.', false);
    }
  };

  id('admin-add-food-btn')?.addEventListener('click', () => {
    showStatus('admin-food-status', 'Use the staff Add Meal flow for now, or we can add an admin food creation form next.');
  });
  await load();
}

async function hydrateAdminTransactions() {
  if (!token) return window.location.replace('/admin-login/');
  let allItems = [];
  let filteredItems = [];

  const applyFilters = () => {
    const query = (id('admin-transactions-search')?.value || '').toLowerCase();
    const from = id('admin-transactions-date-from')?.value;
    const to = id('admin-transactions-date-to')?.value;
    filteredItems = allItems.filter((item) => {
      const haystack = JSON.stringify(item).toLowerCase();
      if (query && !haystack.includes(query)) return false;
      const date = new Date(item.time);
      if (from && !Number.isNaN(date.getTime()) && date < new Date(`${from}T00:00:00`)) return false;
      if (to && !Number.isNaN(date.getTime()) && date > new Date(`${to}T23:59:59`)) return false;
      return true;
    });
    renderAdminTableRows('admin-transactions-body', filteredItems.map((item) => ({
      transaction_id: escapeHtml(item.transaction_id),
      student: escapeHtml(item.student),
      item: escapeHtml(item.item),
      amount: formatCurrency(item.amount),
      method: escapeHtml(item.method),
      status: `<span class="hit-badge ${String(item.status).toLowerCase().includes('failed') ? 'hit-badge--danger' : 'hit-badge--success'}">${escapeHtml(item.status)}</span>`,
      time: formatDateTime(item.time),
    })), ['transaction_id', 'student', 'item', 'amount', 'method', 'status', 'time']);
    showStatus('admin-transactions-status', `${filteredItems.length} transaction${filteredItems.length === 1 ? '' : 's'} ready.`);
  };

  const exportFilteredTransactions = () => {
    if (!filteredItems.length) {
      showStatus('admin-transactions-status', 'There are no transactions to export.', false);
      return;
    }
    const rows = [
      ['Transaction ID', 'Student', 'Item', 'Amount', 'Method', 'Status', 'Time'],
      ...filteredItems.map((item) => [
        item.transaction_id,
        item.student,
        item.item,
        Number(item.amount || 0).toFixed(2),
        item.method,
        item.status,
        formatDateTime(item.time),
      ]),
    ];
    downloadCsvFile(`hit-transactions-${new Date().toISOString().slice(0, 10)}.csv`, rows);
    showStatus('admin-transactions-status', 'Transactions exported successfully.');
  };

  const printFilteredTransactions = () => {
    if (!filteredItems.length) {
      showStatus('admin-transactions-status', 'There are no transactions to print.', false);
      return;
    }
    const bodyHtml = `
      <h1>HIT Canteen Transactions Report</h1>
      <p class="muted">Generated on ${escapeHtml(formatDateTime(new Date().toISOString()))}</p>
      <div class="summary">
        <div class="summary-card"><strong>Total Records</strong><p>${filteredItems.length}</p></div>
        <div class="summary-card"><strong>Total Value</strong><p>${formatCurrency(filteredItems.reduce((sum, item) => sum + Number(item.amount || 0), 0))}</p></div>
      </div>
      <table>
        <thead><tr><th>Transaction ID</th><th>Student</th><th>Item</th><th>Amount</th><th>Method</th><th>Status</th><th>Time</th></tr></thead>
        <tbody>
          ${filteredItems.map((item) => `<tr><td>${escapeHtml(item.transaction_id)}</td><td>${escapeHtml(item.student)}</td><td>${escapeHtml(item.item)}</td><td>${escapeHtml(formatCurrency(item.amount))}</td><td>${escapeHtml(item.method)}</td><td>${escapeHtml(item.status)}</td><td>${escapeHtml(formatDateTime(item.time))}</td></tr>`).join('')}
        </tbody>
      </table>
    `;
    if (openPrintWindow('HIT Canteen Transactions Report', bodyHtml)) {
      showStatus('admin-transactions-status', 'Print view opened. Save as PDF from the print dialog.');
    } else {
      showStatus('admin-transactions-status', 'Allow pop-ups to print this report.', false);
    }
  };

  try {
    allItems = await req('/api/v1/admin/all-transactions');
    applyFilters();
  } catch (err) {
    showStatus('admin-transactions-status', err.message || 'Unable to load transactions right now.', false);
  }

  id('admin-transactions-search')?.addEventListener('input', applyFilters);
  id('admin-transactions-date-from')?.addEventListener('change', applyFilters);
  id('admin-transactions-date-to')?.addEventListener('change', applyFilters);
  id('admin-export-transactions-btn')?.addEventListener('click', exportFilteredTransactions);
  id('admin-print-transactions-btn')?.addEventListener('click', printFilteredTransactions);
}

function getAdminReportPeriodMeta(period) {
  const now = new Date();
  const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  if (period === 'weekly') {
    return {
      title: 'Weekly Sales Trend',
      subtitle: 'Sales totals for the last 8 weeks.',
      includes(date) {
        return date >= new Date(todayStart.getTime() - 56 * 24 * 60 * 60 * 1000);
      },
      bucketKey(date) {
        const start = new Date(date);
        start.setHours(0, 0, 0, 0);
        start.setDate(start.getDate() - start.getDay());
        return start.toISOString().slice(0, 10);
      },
      bucketLabel(date) {
        const start = new Date(date);
        start.setHours(0, 0, 0, 0);
        start.setDate(start.getDate() - start.getDay());
        return `${start.toLocaleString('en-US', { month: 'short' })} ${start.getDate()}`;
      },
    };
  }
  if (period === 'monthly') {
    return {
      title: 'Monthly Sales Trend',
      subtitle: 'Sales totals for the last 6 months.',
      includes(date) {
        return date >= new Date(now.getFullYear(), now.getMonth() - 5, 1);
      },
      bucketKey(date) {
        return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`;
      },
      bucketLabel(date) {
        return date.toLocaleString('en-US', { month: 'short', year: 'numeric' });
      },
    };
  }
  if (period === 'weekends') {
    return {
      title: 'Weekend Sales Trend',
      subtitle: 'Saturday and Sunday sales over recent weekends.',
      includes(date) {
        const day = date.getDay();
        return date >= new Date(todayStart.getTime() - 56 * 24 * 60 * 60 * 1000) && (day === 0 || day === 6);
      },
      bucketKey(date) {
        const normalized = new Date(date);
        normalized.setHours(0, 0, 0, 0);
        return normalized.toISOString().slice(0, 10);
      },
      bucketLabel(date) {
        return `${date.toLocaleString('en-US', { month: 'short' })} ${date.getDate()} ${date.toLocaleString('en-US', { weekday: 'short' })}`;
      },
    };
  }
  return {
    title: 'Daily Sales Trend',
    subtitle: 'Sales totals for the last 7 days.',
    includes(date) {
      return date >= new Date(todayStart.getTime() - 6 * 24 * 60 * 60 * 1000);
    },
    bucketKey(date) {
      const normalized = new Date(date);
      normalized.setHours(0, 0, 0, 0);
      return normalized.toISOString().slice(0, 10);
    },
    bucketLabel(date) {
      return date.toLocaleString('en-US', { weekday: 'short' });
    },
  };
}

function renderAdminSalesLineChart(entries) {
  const width = 720;
  const height = 240;
  const padding = { top: 20, right: 20, bottom: 44, left: 24 };
  const values = entries.map(([, item]) => Number(item.value || 0));
  const max = Math.max(...values, 1);
  const min = 0;
  const usableWidth = width - padding.left - padding.right;
  const usableHeight = height - padding.top - padding.bottom;
  const stepX = entries.length > 1 ? usableWidth / (entries.length - 1) : 0;
  const points = entries.map(([, item], index) => {
    const value = Number(item.value || 0);
    const x = entries.length === 1 ? width / 2 : padding.left + (index * stepX);
    const y = padding.top + usableHeight - (((value - min) / (max - min || 1)) * usableHeight);
    return { x, y, value, label: item.label };
  });
  const polyline = points.map((point) => `${point.x},${point.y}`).join(' ');
  const area = `${padding.left},${padding.top + usableHeight} ${polyline} ${points[points.length - 1].x},${padding.top + usableHeight}`;
  const yTicks = 4;
  const gridLines = Array.from({ length: yTicks + 1 }, (_, index) => {
    const y = padding.top + ((usableHeight / yTicks) * index);
    const tickValue = max - ((max / yTicks) * index);
    return `
      <line x1="${padding.left}" y1="${y}" x2="${width - padding.right}" y2="${y}" class="hit-line-chart__grid" />
      <text x="${padding.left - 6}" y="${y + 4}" text-anchor="end" class="hit-line-chart__tick">${escapeHtml(formatCurrency(tickValue))}</text>
    `;
  }).join('');
  const pointMarkers = points.map((point, index) => `
    <g>
      <circle cx="${point.x}" cy="${point.y}" r="${index === points.length - 1 ? 5 : 4}" class="hit-line-chart__dot${index === points.length - 1 ? ' hit-line-chart__dot--latest' : ''}" />
      <text x="${point.x}" y="${height - 16}" text-anchor="middle" class="hit-line-chart__label">${escapeHtml(point.label)}</text>
    </g>
  `).join('');
  return `
    <div class="hit-line-chart">
      <svg viewBox="0 0 ${width} ${height}" class="hit-line-chart__svg" role="img" aria-label="Sales trend line graph">
        ${gridLines}
        <path d="M ${polyline.replaceAll(' ', ' L ')}" class="hit-line-chart__stroke" />
        <polygon points="${area}" class="hit-line-chart__area" />
        ${pointMarkers}
      </svg>
    </div>
  `;
}

function renderAdminRevenueChart(period, transactions) {
  const chart = id('admin-reports-revenue');
  const title = id('admin-report-chart-title');
  const subtitle = id('admin-report-chart-subtitle');
  if (!chart) return;
  const meta = getAdminReportPeriodMeta(period);
  if (title) title.textContent = meta.title;
  if (subtitle) subtitle.textContent = meta.subtitle;
  const succeeded = transactions.filter((item) => {
    const status = String(item.status || '').toLowerCase();
    return status.includes('success') || status.includes('paid') || status.includes('succeeded');
  });
  const buckets = new Map();
  succeeded.forEach((item) => {
    const date = new Date(item.time);
    if (Number.isNaN(date.getTime()) || !meta.includes(date)) return;
    const key = meta.bucketKey(date);
    const existing = buckets.get(key) || { label: meta.bucketLabel(date), value: 0 };
    existing.value += Number(item.amount || 0);
    buckets.set(key, existing);
  });
  const entries = Array.from(buckets.entries()).sort(([left], [right]) => left.localeCompare(right));
  if (!entries.length) {
    chart.innerHTML = '<div class="hit-empty-state">No sales recorded for this reporting period.</div>';
    return;
  }
  chart.innerHTML = `
    ${renderAdminSalesLineChart(entries)}
    <p class="hit-muted">Total sales in focus: <strong>${formatCurrency(entries.reduce((sum, [, item]) => sum + Number(item.value || 0), 0))}</strong></p>
  `;
}

function renderAdminReportList(targetId, rows, renderRow, emptyMessage) {
  const node = id(targetId);
  if (!node) return;
  if (!rows.length) {
    node.innerHTML = `<div class="hit-empty-state">${emptyMessage}</div>`;
    return;
  }
  node.innerHTML = rows.map(renderRow).join('');
}

async function hydrateAdminReports() {
  if (!token) return window.location.replace('/admin-login/');
  const tabs = Array.from(document.querySelectorAll('[data-report-period]'));
  let currentSnapshot = null;

  const exportFullReport = () => {
    if (!currentSnapshot) {
      showStatus('admin-reports-status', 'Load a report period before exporting.', false);
      return;
    }
    const rows = [
      ['Report Period', currentSnapshot.periodLabel],
      ['Sales Total', currentSnapshot.totalSales.toFixed(2)],
      ['Successful Payments', currentSnapshot.successful.length],
      ['Failed Payments', currentSnapshot.failed.length],
      ['Top Method', currentSnapshot.methods[0] ? currentSnapshot.methods[0][0] : ''],
      [''],
      ['Sales Summary'],
      ['Item', 'Quantity'],
      ...currentSnapshot.topItems.map(([name, quantity]) => [name, quantity]),
      [''],
      ['Payment Methods'],
      ['Method', 'Amount'],
      ...currentSnapshot.methods.map(([method, amount]) => [method, Number(amount || 0).toFixed(2)]),
      [''],
      ['Successful Payments'],
      ['Transaction ID', 'Student', 'Amount', 'Method', 'Time'],
      ...currentSnapshot.successful.map((item) => [item.transaction_id, item.student, Number(item.amount || 0).toFixed(2), item.method, formatDateTime(item.time)]),
      [''],
      ['Failed Payments'],
      ['Transaction ID', 'Student', 'Amount', 'Method', 'Time'],
      ...currentSnapshot.failed.map((item) => [item.transaction_id, item.student, Number(item.amount || 0).toFixed(2), item.method, formatDateTime(item.time)]),
    ];
    downloadCsvFile(`hit-report-${currentSnapshot.period}-${new Date().toISOString().slice(0, 10)}.csv`, rows);
    showStatus('admin-reports-status', `${currentSnapshot.metaTitle} exported successfully.`);
  };

  const exportSales = () => {
    if (!currentSnapshot) {
      showStatus('admin-reports-status', 'Load a report period before exporting sales.', false);
      return;
    }
    const rows = [
      ['Report Period', currentSnapshot.periodLabel],
      ['Sales Total', currentSnapshot.totalSales.toFixed(2)],
      [''],
      ['Top Selling Items'],
      ['Item', 'Quantity'],
      ...currentSnapshot.topItems.map(([name, quantity]) => [name, quantity]),
    ];
    downloadCsvFile(`hit-sales-${currentSnapshot.period}-${new Date().toISOString().slice(0, 10)}.csv`, rows);
    showStatus('admin-reports-status', 'Sales export downloaded.');
  };

  const exportPayments = () => {
    if (!currentSnapshot) {
      showStatus('admin-reports-status', 'Load a report period before exporting payments.', false);
      return;
    }
    if (!currentSnapshot.successful.length) {
      showStatus('admin-reports-status', 'There are no successful payments in this period.', false);
      return;
    }
    const rows = [
      ['Transaction ID', 'Student', 'Amount', 'Method', 'Status', 'Time'],
      ...currentSnapshot.successful.map((item) => [item.transaction_id, item.student, Number(item.amount || 0).toFixed(2), item.method, item.status, formatDateTime(item.time)]),
    ];
    downloadCsvFile(`hit-payments-${currentSnapshot.period}-${new Date().toISOString().slice(0, 10)}.csv`, rows);
    showStatus('admin-reports-status', 'Successful payments export downloaded.');
  };

  const exportFailedPayments = () => {
    if (!currentSnapshot) {
      showStatus('admin-reports-status', 'Load a report period before exporting failed payments.', false);
      return;
    }
    if (!currentSnapshot.failed.length) {
      showStatus('admin-reports-status', 'There are no failed payments in this period.', false);
      return;
    }
    const rows = [
      ['Transaction ID', 'Student', 'Amount', 'Method', 'Status', 'Time'],
      ...currentSnapshot.failed.map((item) => [item.transaction_id, item.student, Number(item.amount || 0).toFixed(2), item.method, item.status, formatDateTime(item.time)]),
    ];
    downloadCsvFile(`hit-failed-payments-${currentSnapshot.period}-${new Date().toISOString().slice(0, 10)}.csv`, rows);
    showStatus('admin-reports-status', 'Failed payments export downloaded.');
  };

  const printReport = () => {
    if (!currentSnapshot) {
      showStatus('admin-reports-status', 'Load a report period before printing.', false);
      return;
    }
    const bodyHtml = `
      <h1>HIT Canteen ${escapeHtml(currentSnapshot.metaTitle)}</h1>
      <p class="muted">Generated on ${escapeHtml(formatDateTime(new Date().toISOString()))}</p>
      <div class="summary">
        <div class="summary-card"><strong>Sales Total</strong><p>${formatCurrency(currentSnapshot.totalSales)}</p></div>
        <div class="summary-card"><strong>Successful Payments</strong><p>${currentSnapshot.successful.length}</p></div>
        <div class="summary-card"><strong>Failed Payments</strong><p>${currentSnapshot.failed.length}</p></div>
        <div class="summary-card"><strong>Top Method</strong><p>${escapeHtml(currentSnapshot.methods[0] ? currentSnapshot.methods[0][0] : '-')}</p></div>
      </div>
      <h2>Payment Method Breakdown</h2>
      <table>
        <thead><tr><th>Method</th><th>Amount</th></tr></thead>
        <tbody>${currentSnapshot.methods.map(([method, amount]) => `<tr><td>${escapeHtml(method)}</td><td>${escapeHtml(formatCurrency(amount))}</td></tr>`).join('') || '<tr><td colspan="2">No successful payments.</td></tr>'}</tbody>
      </table>
      <h2>Top Selling Items</h2>
      <table>
        <thead><tr><th>Item</th><th>Quantity</th></tr></thead>
        <tbody>${currentSnapshot.topItems.map(([name, quantity]) => `<tr><td>${escapeHtml(name)}</td><td>${quantity}</td></tr>`).join('') || '<tr><td colspan="2">No completed orders.</td></tr>'}</tbody>
      </table>
      <h2>Failed Payments</h2>
      <table>
        <thead><tr><th>Transaction ID</th><th>Student</th><th>Amount</th><th>Time</th></tr></thead>
        <tbody>${currentSnapshot.failed.map((item) => `<tr><td>${escapeHtml(item.transaction_id)}</td><td>${escapeHtml(item.student)}</td><td>${escapeHtml(formatCurrency(item.amount))}</td><td>${escapeHtml(formatDateTime(item.time))}</td></tr>`).join('') || '<tr><td colspan="4">No failed payments.</td></tr>'}</tbody>
      </table>
    `;
    if (openPrintWindow(`HIT Canteen ${currentSnapshot.metaTitle}`, bodyHtml)) {
      showStatus('admin-reports-status', 'Print view opened. Save as PDF from the print dialog.');
    } else {
      showStatus('admin-reports-status', 'Allow pop-ups to print this report.', false);
    }
  };

  try {
    const [transactions, orders] = await Promise.all([req('/api/v1/admin/all-transactions'), req('/api/v1/orders')]);
    const renderPeriod = (period) => {
      tabs.forEach((tab) => tab.classList.toggle('active', tab.dataset.reportPeriod === period));
      const meta = getAdminReportPeriodMeta(period);
      const filteredTransactions = transactions.filter((item) => {
        const date = new Date(item.time);
        return !Number.isNaN(date.getTime()) && meta.includes(date);
      });
      const filteredOrders = orders.filter((item) => {
        const date = new Date(item.created_at);
        return !Number.isNaN(date.getTime()) && meta.includes(date);
      });
      const successful = filteredTransactions.filter((item) => {
        const status = String(item.status || '').toLowerCase();
        return status.includes('success') || status.includes('paid') || status.includes('succeeded');
      });
      const failed = filteredTransactions.filter((item) => String(item.status || '').toLowerCase().includes('failed'));
      const totalSales = successful.reduce((sum, item) => sum + Number(item.amount || 0), 0);
      const methods = Object.entries(successful.reduce((acc, item) => {
        const key = item.method || 'Unknown';
        acc[key] = (acc[key] || 0) + Number(item.amount || 0);
        return acc;
      }, {})).sort((a, b) => b[1] - a[1]);
      const topItems = Object.entries(filteredOrders.reduce((acc, item) => {
        const key = item.meal || 'Meal';
        acc[key] = (acc[key] || 0) + Number(item.quantity || 0);
        return acc;
      }, {})).sort((a, b) => b[1] - a[1]).slice(0, 5);
      currentSnapshot = {
        period,
        periodLabel: meta.title.replace(' Trend', ''),
        metaTitle: meta.title,
        totalSales,
        successful,
        failed,
        methods,
        topItems,
      };
      if (id('admin-report-total-sales')) id('admin-report-total-sales').textContent = formatCurrency(totalSales);
      if (id('admin-report-success-count')) id('admin-report-success-count').textContent = String(successful.length);
      if (id('admin-report-top-method')) id('admin-report-top-method').textContent = methods[0] ? methods[0][0] : '-';
      if (id('admin-report-failed-count')) id('admin-report-failed-count').textContent = String(failed.length);
      renderAdminRevenueChart(period, filteredTransactions);
      renderAdminReportList('admin-payment-methods', methods, ([method, amount]) => `<div class="hit-list-row"><span>${escapeHtml(method)}</span><strong>${formatCurrency(amount)}</strong></div>`, 'No successful payments in this period.');
      renderAdminReportList('admin-top-items', topItems, ([name, quantity]) => `<div class="hit-list-row"><span>${escapeHtml(name)}</span><strong>${quantity}</strong></div>`, 'No completed orders in this period.');
      renderAdminReportList('admin-failed-payments', failed.slice(0, 8), (item) => `<div class="hit-list-row"><span>${escapeHtml(item.student)} | ${escapeHtml(item.transaction_id)}</span><strong>${formatCurrency(item.amount)}</strong></div>`, 'No failed payments in this period.');
      showStatus('admin-reports-status', `${meta.title} loaded successfully.`);
    };

    tabs.forEach((tab) => tab.addEventListener('click', () => renderPeriod(tab.dataset.reportPeriod)));
    id('admin-export-report-btn')?.addEventListener('click', exportFullReport);
    id('admin-print-report-btn')?.addEventListener('click', printReport);
    id('admin-export-sales-btn')?.addEventListener('click', exportSales);
    id('admin-export-payments-btn')?.addEventListener('click', exportPayments);
    id('admin-export-failed-btn')?.addEventListener('click', exportFailedPayments);

    renderPeriod('daily');
  } catch (err) {
    showStatus('admin-reports-status', err.message || 'Unable to load report data right now.', false);
    if (id('admin-reports-revenue')) {
      id('admin-reports-revenue').innerHTML = '<div class="hit-empty-state">Unable to load report data right now.</div>';
    }
  }
}
function applyActiveNavState() {
  const path = window.location.pathname;
  document.querySelectorAll('.hit-bottom-nav a, .hit-sidebar__nav a').forEach((link) => {
    const href = link.getAttribute('href');
    if (!href) return;
    link.classList.toggle('active', href === path);
  });
}
function ensureAdminPortalPage() {
  if (!guardPortalAccess('admin')) return false;
  bindLogout();
  applyActiveNavState();
  if (page() === 'admin-dashboard') {
    applyCurrentUserGreeting('admin-dashboard-greeting', 'Admin');
  }
  return true;
}

function renderMiniBarChart(targetId, values, labels = [], highlightIndex = -1) {
  const node = id(targetId);
  if (!node) return;
  if (!values.length) {
    node.innerHTML = '<div class="hit-empty-state">No recent data available.</div>';
    return;
  }
  const max = Math.max(...values, 1);
  node.innerHTML = `
    <div class="hit-chart-bars">
      ${values.map((value, index) => {
        const height = Math.max(12, Math.round((Number(value || 0) / max) * 100));
        const label = labels[index] || '';
        return `<div class="hit-chart-bar${index === highlightIndex ? ' hit-chart-bar--gold' : ''}" style="height:${height}%" title="${escapeHtml(label)}: ${value}"></div>`;
      }).join('')}
    </div>
  `;
}

async function hydrateAdminDashboard() {
  if (!token) return window.location.replace('/admin-login/');
  try {
    const [kpis, transactions] = await Promise.all([
      req('/api/v1/admin/kpis'),
      req('/api/v1/admin/all-transactions'),
    ]);

    if (id('admin-kpi-revenue')) id('admin-kpi-revenue').textContent = formatCurrency(kpis.total_revenue || 0);
    if (id('admin-kpi-transactions')) id('admin-kpi-transactions').textContent = String(kpis.total_transactions || 0);
    if (id('admin-kpi-students')) id('admin-kpi-students').textContent = String(kpis.active_students || 0);
    if (id('admin-kpi-failed')) id('admin-kpi-failed').textContent = String(kpis.failed_payments || 0);

    const activityBody = id('admin-activity-body');
    if (activityBody) {
      const recentItems = transactions.slice(0, 12);
      activityBody.innerHTML = recentItems.length
        ? recentItems.map((item) => `
            <tr>
              <td>${escapeHtml(formatDateTime(item.time))}</td>
              <td>${escapeHtml(item.item || 'Transaction')}</td>
              <td>${escapeHtml(item.student || item.student_email || '-')}</td>
              <td>${escapeHtml(item.status || '-')}</td>
            </tr>
          `).join('')
        : '<tr><td colspan="4">No recent activity found.</td></tr>';
    }

    const now = new Date();
    const lastSevenDays = Array.from({ length: 7 }, (_, index) => {
      const day = new Date(now);
      day.setHours(0, 0, 0, 0);
      day.setDate(now.getDate() - (6 - index));
      return day;
    });
    const dayKeys = lastSevenDays.map((day) => day.toISOString().slice(0, 10));
    const revenueByDay = Object.fromEntries(dayKeys.map((key) => [key, 0]));
    const countByDay = Object.fromEntries(dayKeys.map((key) => [key, 0]));

    transactions.forEach((item) => {
      const dayKey = String(item.time || '').slice(0, 10);
      if (!Object.prototype.hasOwnProperty.call(revenueByDay, dayKey)) return;
      const amount = Number(item.amount || 0);
      const status = String(item.status || '').toLowerCase();
      if (!status.includes('failed')) {
        revenueByDay[dayKey] += amount;
      }
      countByDay[dayKey] += 1;
    });

    const revenueValues = dayKeys.map((key) => Number(revenueByDay[key].toFixed(2)));
    const transactionValues = dayKeys.map((key) => countByDay[key]);
    const labels = lastSevenDays.map((day) => day.toLocaleDateString(undefined, { weekday: 'short' }));
    renderMiniBarChart('admin-revenue-chart', revenueValues, labels, revenueValues.lastIndexOf(Math.max(...revenueValues, 0)));
    renderMiniBarChart('admin-transactions-chart', transactionValues, labels, transactionValues.lastIndexOf(Math.max(...transactionValues, 0)));
  } catch (err) {
    const activityBody = id('admin-activity-body');
    if (activityBody) {
      activityBody.innerHTML = `<tr><td colspan="4">${escapeHtml(err.message || 'Unable to load dashboard data.')}</td></tr>`;
    }
    if (id('admin-revenue-chart')) id('admin-revenue-chart').innerHTML = '<div class="hit-empty-state">Unable to load chart data.</div>';
    if (id('admin-transactions-chart')) id('admin-transactions-chart').innerHTML = '<div class="hit-empty-state">Unable to load chart data.</div>';
  }
}

function initAdminLoginPage() {
  window.__hitAdminLoginBound = true;
  setToken('');
  applyVerificationMessage('admin-login-status');
  id('admin-demo-fill-btn')?.addEventListener('click', () => {
    if (id('admin-login-email')) id('admin-login-email').value = 'admin@hit.ac.zw';
    if (id('admin-password')) id('admin-password').value = 'Demo@1234';
    showStatus('admin-login-status', 'Signing in with demo admin account...');
    id('admin-login-form')?.requestSubmit();
  });
  id('admin-login-form')?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const submitButton = event.target.querySelector('button[type="submit"]');
    setButtonBusy(submitButton, true, 'Logging in...');
    showStatus('admin-login-status', 'Checking admin account...');
    const result = await loginRequest('admin-login-email', 'admin-password');
    if (result?.error) {
      showStatus('admin-login-status', result.error, false);
      setButtonBusy(submitButton, false);
      return;
    }
    redirectToPortalForRole(result.data?.role);
  });
}

async function hydrateAdminSettings() {
  if (!token) return window.location.replace('/admin-login/');
  let currentSettings = null;
  const fillSettings = (data) => {
    currentSettings = { ...data };
    if (id('admin-setting-paynow-id')) id('admin-setting-paynow-id').value = data.paynow_integration_id || '';
    if (id('admin-setting-paynow-return-url')) id('admin-setting-paynow-return-url').value = data.paynow_return_url || '';
    if (id('admin-setting-smtp-host')) id('admin-setting-smtp-host').value = data.smtp_host || '';
    if (id('admin-setting-default-from-email')) id('admin-setting-default-from-email').value = data.default_from_email || '';
    if (id('admin-setting-qr-expiry')) id('admin-setting-qr-expiry').value = data.qr_expiry_minutes ?? 30;
    if (id('admin-setting-email-alerts')) id('admin-setting-email-alerts').checked = Boolean(data.email_alerts_enabled);
    if (id('admin-setting-fraud-alerts')) id('admin-setting-fraud-alerts').checked = Boolean(data.fraud_alerts_enabled);
    if (id('admin-setting-session-timeout')) id('admin-setting-session-timeout').value = data.session_timeout_minutes ?? 30;
  };

  const saveSettingsGroup = async (buttonId, statusId, payloadBuilder, busyLabel, confirmMessage) => {
    const button = id(buttonId);
    if (!button || button.dataset.bound === 'true') return;
    button.dataset.bound = 'true';
    button.addEventListener('click', async () => {
      try {
        setButtonBusy(button, true, busyLabel);
        const payload = payloadBuilder();
        const changed = !currentSettings || Object.entries(payload).some(([key, value]) => currentSettings[key] !== value);
        if (!changed) {
          showStatus(statusId, 'No changes to save.');
          return;
        }
        if (confirmMessage && !window.confirm(confirmMessage)) {
          showStatus(statusId, 'Save cancelled.', false);
          return;
        }
        const response = await req('/api/v1/admin/settings', 'PATCH', payload);
        currentSettings = { ...(currentSettings || {}), ...payload };
        showStatus(statusId, response.detail || 'Settings saved successfully.');
      } catch (err) {
        showStatus(statusId, err.message || 'Unable to save settings right now.', false);
      } finally {
        setButtonBusy(button, false);
      }
    });
  };

  try {
    const settingsData = await req('/api/v1/admin/settings');
    fillSettings(settingsData);
  } catch (err) {
    showStatus('admin-settings-status-payment', err.message || 'Unable to load settings right now.', false);
  }

  saveSettingsGroup('admin-settings-save-payment-btn', 'admin-settings-status-payment', () => ({
    paynow_integration_id: id('admin-setting-paynow-id')?.value.trim() || '',
    paynow_return_url: id('admin-setting-paynow-return-url')?.value.trim() || '',
  }), 'Saving...', 'Save payment integration settings?');

  saveSettingsGroup('admin-settings-save-email-btn', 'admin-settings-status-email', () => ({
    smtp_host: id('admin-setting-smtp-host')?.value.trim() || '',
    default_from_email: id('admin-setting-default-from-email')?.value.trim() || '',
  }), 'Saving...', 'Save email settings?');

  saveSettingsGroup('admin-settings-save-qr-btn', 'admin-settings-status-qr', () => ({
    qr_expiry_minutes: Number(id('admin-setting-qr-expiry')?.value || 30),
  }), 'Saving...', 'Save QR expiry settings?');

  saveSettingsGroup('admin-settings-save-notifications-btn', 'admin-settings-status-notifications', () => ({
    email_alerts_enabled: Boolean(id('admin-setting-email-alerts')?.checked),
    fraud_alerts_enabled: Boolean(id('admin-setting-fraud-alerts')?.checked),
  }), 'Saving...', 'Save notification settings?');

  saveSettingsGroup('admin-settings-save-security-btn', 'admin-settings-status-security', () => ({
    session_timeout_minutes: Number(id('admin-setting-session-timeout')?.value || 30),
  }), 'Saving...', 'Save security settings?');
}

function initExtendedRolePages() {
  if (page() === 'student-menu') return hydrateStudentMenuPage();
  if (page() === 'student-cart') return hydrateStudentCartPage();
  if (page() === 'student-transactions') return hydrateStudentTransactionsPage();
  if (page() === 'student-profile') return hydrateStudentProfilePage();
  if (page() === 'student-add-money') return hydrateStudentAddMoneyPage();
  if (page() === 'student-pay-scanner') return initStudentPayScannerPage();
  if (page() === 'student-qr') return hydrateStudentQrPage();
  if (page() === 'admin-login') return initAdminLoginPage();
  if (page() === 'admin-dashboard') { if (!ensureAdminPortalPage()) return; return hydrateAdminDashboard(); }
  if (page() === 'admin-students') { if (!ensureAdminPortalPage()) return; return hydrateAdminStudents(); }
  if (page() === 'admin-staff') { if (!ensureAdminPortalPage()) return; return hydrateAdminStaff(); }
  if (page() === 'admin-food') { if (!ensureAdminPortalPage()) return; return hydrateAdminFood(); }
  if (page() === 'admin-transactions') { if (!ensureAdminPortalPage()) return; return hydrateAdminTransactions(); }
  if (page() === 'admin-reports') { if (!ensureAdminPortalPage()) return; return hydrateAdminReports(); }
  if (page() === 'admin-settings') { if (!ensureAdminPortalPage()) return; return hydrateAdminSettings(); }
}

window.addEventListener('DOMContentLoaded', initExtendedRolePages);



























