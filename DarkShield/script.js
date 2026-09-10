const stateKey = "streamplusSubscription";
const defaultState = { status: "active", offerAccepted: false, cancellationReason: "" };
let subscription = { ...defaultState, ...(JSON.parse(localStorage.getItem(stateKey) || "null") || {}) };

function logBehavior(action, elementText) {
  console.log({ timestamp: new Date().toISOString(), action, elementText, currentURL: window.location.href });
}

function saveState() { localStorage.setItem(stateKey, JSON.stringify(subscription)); }
function navigate(route) { window.location.hash = route; }

function render(route = window.location.hash.slice(1) || "home") {
  const page = document.querySelector(`[data-page="${route}"]`) || document.querySelector('[data-page="home"]');
  document.querySelectorAll(".page").forEach(section => section.classList.toggle("hidden", section !== page));
  document.querySelectorAll("[data-route]").forEach(link => link.classList.toggle("active", link.dataset.route === page.dataset.page));
  updateAccount();
}

function updateAccount() {
  const active = subscription.status === "active";
  document.getElementById("subscription-status").textContent = active ? "Premium Plan – Active" : "Premium – Cancelled";
  document.getElementById("subscription-detail").textContent = active ? "Free trial active" : "Your plan is no longer renewing";
  document.getElementById("renewal-price").textContent = active ? "₹999" : "—";
}

function startTrial(button) {
  subscription = { ...defaultState, status: "active" };
  saveState(); logBehavior("start_trial", button.textContent.trim()); navigate("account");
}

function handleAction(action, button) {
  const text = button.textContent.trim();
  if (action === "start-trial") startTrial(button);
  if (action === "manage-subscription") { logBehavior("manage_subscription", text); navigate("account"); }
  if (action === "start-cancellation") { logBehavior("start_cancellation", text); navigate("cancel"); }
  if (action === "show-offer") { logBehavior("retention_offer_requested", text); navigate("offer"); }
  if (action === "continue-cancellation") { logBehavior("continue_cancellation", text); navigate("offer"); }
  if (action === "accept-offer") { subscription.offerAccepted = true; saveState(); logBehavior("accept_offer", text); navigate("account"); }
  if (action === "decline-offer") { logBehavior("decline_offer", text); navigate("survey"); }
  if (action === "keep-subscription") { logBehavior("keep_subscription", text); navigate("account"); }
  if (action === "finish-cancellation") { subscription.status = "cancelled"; saveState(); logBehavior("confirm_cancellation", text); navigate("success"); }
}

document.addEventListener("click", event => {
  const routeLink = event.target.closest("[data-route]");
  if (routeLink) { event.preventDefault(); logBehavior("navigate", routeLink.textContent.trim()); navigate(routeLink.dataset.route); return; }
  const button = event.target.closest("button[data-action]");
  if (button) { logBehavior("click_button", button.textContent.trim()); handleAction(button.dataset.action, button); }
});

document.getElementById("reason").addEventListener("change", event => logBehavior("change_cancellation_reason", event.target.value));
document.getElementById("cancellation-survey").addEventListener("submit", event => {
  event.preventDefault();
  if (!event.currentTarget.reportValidity()) return;
  subscription.cancellationReason = document.getElementById("reason").value; saveState();
  logBehavior("submit_cancellation_survey", subscription.cancellationReason); navigate("confirm");
});

window.addEventListener("hashchange", () => render());
render();
