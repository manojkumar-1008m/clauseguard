// background.js – ClauseGuard background service worker (Manifest V3)

// Listen for optional background requests
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg && msg.type === "PING") {
    sendResponse({ status: "ok" });
    return false;
  }
  return false;
});
