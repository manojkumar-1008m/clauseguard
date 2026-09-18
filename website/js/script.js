// Single configurable download path constant
const EXTENSION_DOWNLOAD_URL = "./downloads/ClauseGuard-Extension.zip";

// Demo credentials with persistent custom update support
const DEFAULT_USER = "demo@clauseguard.com";
const DEFAULT_PASS = "ClauseGuard@123";
const AUTH_KEY = "cg_authenticated";
const STORAGE_USER_KEY = "cg_user_email";
const STORAGE_PASS_KEY = "cg_user_password";
const STORAGE_PREFS_KEY = "cg_protection_prefs";

function getActiveUser() {
  return localStorage.getItem(STORAGE_USER_KEY) || DEFAULT_USER;
}

function getActivePass() {
  return localStorage.getItem(STORAGE_PASS_KEY) || DEFAULT_PASS;
}

function setActiveUser(email) {
  localStorage.setItem(STORAGE_USER_KEY, email);
}

function setActivePass(pass) {
  localStorage.setItem(STORAGE_PASS_KEY, pass);
}

function resetCredentialsAndPrefs() {
  localStorage.removeItem(STORAGE_USER_KEY);
  localStorage.removeItem(STORAGE_PASS_KEY);
  localStorage.removeItem(STORAGE_PREFS_KEY);
}

// --- Authentication State Management ---
function isAuthenticated() {
  return sessionStorage.getItem(AUTH_KEY) === "true";
}

function setAuthenticated(val) {
  if (val) {
    sessionStorage.setItem(AUTH_KEY, "true");
  } else {
    sessionStorage.removeItem(AUTH_KEY);
  }
}

const loginGate = document.getElementById("login-gate");
const landingContent = document.getElementById("landing-content");
const loginForm = document.getElementById("login-form");
const loginError = document.getElementById("login-error");
const logoutBtn = document.getElementById("logout-btn");
const settingsBtn = document.getElementById("settings-btn");
const navUserLabel = document.getElementById("nav-user-label");

function updateAuthState() {
  const authed = isAuthenticated();
  const currentEmail = getActiveUser();

  if (authed) {
    if (loginGate) loginGate.style.display = "none";
    if (landingContent) landingContent.style.display = "block";
    if (navUserLabel) {
      const shortName = currentEmail.split("@")[0] || "Account";
      navUserLabel.textContent = shortName;
    }
    updateSettingsUI();
    initObserver();
  } else {
    if (loginGate) loginGate.style.display = "flex";
    if (landingContent) landingContent.style.display = "none";
    if (loginError) loginError.style.display = "none";
    closeSettingsModal();
  }
}

if (loginForm) {
  loginForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const emailInput = document.getElementById("login-email");
    const passInput = document.getElementById("login-password");
    const email = emailInput ? emailInput.value.trim() : "";
    const pass = passInput ? passInput.value : "";

    const activeUser = getActiveUser();
    const activePass = getActivePass();

    if (email.toLowerCase() === activeUser.toLowerCase() && pass === activePass) {
      setAuthenticated(true);
      if (loginError) loginError.style.display = "none";
      if (passInput) passInput.value = "";
      updateAuthState();
    } else {
      if (loginError) {
        loginError.textContent = "Invalid email or password. Please try again.";
        loginError.style.display = "block";
      }
    }
  });
}

if (logoutBtn) {
  logoutBtn.addEventListener("click", () => {
    setAuthenticated(false);
    updateAuthState();
  });
}

// --- Settings Modal & Feature Controls ---
const settingsModalBackdrop = document.getElementById("settings-modal-backdrop");
const settingsCloseBtn = document.getElementById("settings-close-btn");
const settingsUserBadge = document.getElementById("settings-user-badge");
const settingsUsernameInput = document.getElementById("settings-username-input");
const formUpdateUsername = document.getElementById("form-update-username");
const formUpdatePassword = document.getElementById("form-update-password");
const settingsProfileFeedback = document.getElementById("settings-profile-feedback");
const settingsFeaturesFeedback = document.getElementById("settings-features-feedback");
const btnSaveFeatures = document.getElementById("btn-save-features");
const btnResetDefaults = document.getElementById("btn-reset-defaults");

function openSettingsModal() {
  if (!settingsModalBackdrop) return;
  updateSettingsUI();
  settingsModalBackdrop.style.display = "flex";
  document.body.style.overflow = "hidden";
}

function closeSettingsModal() {
  if (!settingsModalBackdrop) return;
  settingsModalBackdrop.style.display = "none";
  document.body.style.overflow = "";
  clearSettingsFeedback();
}

function clearSettingsFeedback() {
  if (settingsProfileFeedback) {
    settingsProfileFeedback.className = "settings-feedback";
    settingsProfileFeedback.textContent = "";
    settingsProfileFeedback.style.display = "none";
  }
  if (settingsFeaturesFeedback) {
    settingsFeaturesFeedback.className = "settings-feedback";
    settingsFeaturesFeedback.textContent = "";
    settingsFeaturesFeedback.style.display = "none";
  }
}

function showProfileFeedback(msg, isSuccess) {
  if (!settingsProfileFeedback) return;
  settingsProfileFeedback.textContent = msg;
  settingsProfileFeedback.className = `settings-feedback ${isSuccess ? "success" : "error"}`;
  settingsProfileFeedback.style.display = "block";
}

function showFeaturesFeedback(msg, isSuccess) {
  if (!settingsFeaturesFeedback) return;
  settingsFeaturesFeedback.textContent = msg;
  settingsFeaturesFeedback.className = `settings-feedback ${isSuccess ? "success" : "error"}`;
  settingsFeaturesFeedback.style.display = "block";
}

function updateSettingsUI() {
  const currentEmail = getActiveUser();
  if (settingsUserBadge) settingsUserBadge.textContent = currentEmail;
  if (settingsUsernameInput) settingsUsernameInput.value = currentEmail;
  loadStoredPreferences();
}

// Tab Switching
document.querySelectorAll(".settings-tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".settings-tab-btn").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".settings-tab-content").forEach((c) => c.classList.remove("active"));
    btn.classList.add("active");
    const target = btn.getAttribute("data-tab");
    const content = document.getElementById(target);
    if (content) content.classList.add("active");
    clearSettingsFeedback();
  });
});

if (settingsBtn) {
  settingsBtn.addEventListener("click", openSettingsModal);
}

if (settingsCloseBtn) {
  settingsCloseBtn.addEventListener("click", closeSettingsModal);
}

if (settingsModalBackdrop) {
  settingsModalBackdrop.addEventListener("click", (event) => {
    if (event.target === settingsModalBackdrop) {
      closeSettingsModal();
    }
  });
}

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && settingsModalBackdrop && settingsModalBackdrop.style.display === "flex") {
    closeSettingsModal();
  }
});

// Update Username Form
if (formUpdateUsername) {
  formUpdateUsername.addEventListener("submit", (event) => {
    event.preventDefault();
    const newUsername = settingsUsernameInput ? settingsUsernameInput.value.trim() : "";
    if (!newUsername || newUsername.length < 3) {
      showProfileFeedback("Please enter a valid username or email (at least 3 characters).", false);
      return;
    }
    setActiveUser(newUsername);
    if (navUserLabel) {
      navUserLabel.textContent = newUsername.split("@")[0] || "Account";
    }
    if (settingsUserBadge) settingsUserBadge.textContent = newUsername;
    showProfileFeedback("Username updated successfully! Use this username for future logins.", true);
  });
}

// Update Password Form
if (formUpdatePassword) {
  formUpdatePassword.addEventListener("submit", (event) => {
    event.preventDefault();
    const currPassInput = document.getElementById("settings-curr-password");
    const newPassInput = document.getElementById("settings-new-password");
    const confirmPassInput = document.getElementById("settings-confirm-password");

    const currPass = currPassInput ? currPassInput.value : "";
    const newPass = newPassInput ? newPassInput.value : "";
    const confirmPass = confirmPassInput ? confirmPassInput.value : "";

    const activePass = getActivePass();

    if (currPass !== activePass) {
      showProfileFeedback("Current password does not match. Please verify your current password.", false);
      return;
    }

    if (newPass.length < 6) {
      showProfileFeedback("New password must be at least 6 characters long.", false);
      return;
    }

    if (newPass !== confirmPass) {
      showProfileFeedback("New passwords do not match. Please confirm your password carefully.", false);
      return;
    }

    setActivePass(newPass);
    if (currPassInput) currPassInput.value = "";
    if (newPassInput) newPassInput.value = "";
    if (confirmPassInput) confirmPassInput.value = "";
    showProfileFeedback("Password changed successfully! Remember to use your new password next time.", true);
  });
}

// Preferences / Feature Toggles
function loadStoredPreferences() {
  try {
    const raw = localStorage.getItem(STORAGE_PREFS_KEY);
    if (!raw) return;
    const prefs = JSON.parse(raw);
    const sensitivity = document.getElementById("setting-sensitivity");
    const journey = document.getElementById("toggle-journey");
    const subscription = document.getElementById("toggle-subscription");
    const cancellation = document.getElementById("toggle-cancellation");
    const pricing = document.getElementById("toggle-pricing");

    if (sensitivity && prefs.sensitivity) sensitivity.value = prefs.sensitivity;
    if (journey && typeof prefs.journey === "boolean") journey.checked = prefs.journey;
    if (subscription && typeof prefs.subscription === "boolean") subscription.checked = prefs.subscription;
    if (cancellation && typeof prefs.cancellation === "boolean") cancellation.checked = prefs.cancellation;
    if (pricing && typeof prefs.pricing === "boolean") pricing.checked = prefs.pricing;
  } catch (_) {}
}

if (btnSaveFeatures) {
  btnSaveFeatures.addEventListener("click", () => {
    const sensitivity = document.getElementById("setting-sensitivity")?.value || "balanced";
    const journey = document.getElementById("toggle-journey")?.checked ?? true;
    const subscription = document.getElementById("toggle-subscription")?.checked ?? true;
    const cancellation = document.getElementById("toggle-cancellation")?.checked ?? true;
    const pricing = document.getElementById("toggle-pricing")?.checked ?? true;

    const prefs = { sensitivity, journey, subscription, cancellation, pricing };
    localStorage.setItem(STORAGE_PREFS_KEY, JSON.stringify(prefs));
    showFeaturesFeedback("Protection preferences saved successfully!", true);
  });
}

// Reset Defaults
if (btnResetDefaults) {
  btnResetDefaults.addEventListener("click", () => {
    if (confirm("Reset username, password, and preferences back to project defaults?")) {
      resetCredentialsAndPrefs();
      updateSettingsUI();
      if (navUserLabel) navUserLabel.textContent = DEFAULT_USER.split("@")[0];
      alert("Credentials and settings have been restored to default (demo@clauseguard.com / ClauseGuard@123).");
    }
  });
}

// --- Extension Download Management ---
function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => {
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }, 1500);
}

function triggerExtensionDownload() {
  fetch(EXTENSION_DOWNLOAD_URL)
    .then((res) => {
      if (!res.ok) throw new Error("HTTP " + res.status);
      return res.blob();
    })
    .then((blob) => {
      downloadBlob(blob, "ClauseGuard-Extension.zip");
    })
    .catch(() => {
      // Fallback: use embedded extension base64 archive
      if (window.CLAUSEGUARD_EXTENSION_BASE64) {
        const bin = atob(window.CLAUSEGUARD_EXTENSION_BASE64);
        const bytes = new Uint8Array(bin.length);
        for (let i = 0; i < bin.length; i++) {
          bytes[i] = bin.charCodeAt(i);
        }
        const blob = new Blob([bytes], { type: "application/zip" });
        downloadBlob(blob, "ClauseGuard-Extension.zip");
      } else {
        const a = document.createElement("a");
        a.href = EXTENSION_DOWNLOAD_URL;
        a.download = "ClauseGuard-Extension.zip";
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
      }
    });
}

document.querySelectorAll(".download-link").forEach((link) => {
  link.href = EXTENSION_DOWNLOAD_URL;
  link.setAttribute("download", "ClauseGuard-Extension.zip");
  link.addEventListener("click", (event) => {
    event.preventDefault();
    triggerExtensionDownload();
  });
});

// --- Scroll Reveal Animations ---
function initObserver() {
  const observer = new IntersectionObserver(
    (entries) =>
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("visible");
          observer.unobserve(entry.target);
        }
      }),
    { threshold: 0.12 }
  );
  document.querySelectorAll(".reveal").forEach((el) => observer.observe(el));
}

// Initialize on page load
updateAuthState();

