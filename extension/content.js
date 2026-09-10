// content.js – ClauseGuard Phase 9.0 Content Script
// Extracts clean, privacy-filtered visible webpage text for analysis.

const MAX_LEN = 5000;
const MAX_PAGE_TEXT_LENGTH = 20000;

/**
 * Extract visible text from the webpage safely without sensitive inputs.
 */
function extractPageText() {
  if (typeof document === "undefined" || !document.body) {
    return {
      text: "",
      title: "",
      url: "",
      truncated: false,
    };
  }

  const title = document.title || "";
  const url = (typeof window !== "undefined" && window.location && window.location.href) ? window.location.href : "";

  // Elements to ignore during extraction for privacy and security
  const IGNORE_TAGS = new Set([
    "SCRIPT", "STYLE", "NOSCRIPT", "SVG", "CANVAS", "IFRAME",
    "VIDEO", "AUDIO", "TEMPLATE", "INPUT", "TEXTAREA", "SELECT"
  ]);

  function isVisible(el) {
    if (!el || el.nodeType !== 1) return false;
    if (el.hasAttribute && el.hasAttribute("hidden")) return false;
    if (el.getAttribute && el.getAttribute("aria-hidden") === "true") return false;
    if (typeof window !== "undefined" && typeof window.getComputedStyle === "function") {
      const style = window.getComputedStyle(el);
      if (style && (style.display === "none" || style.visibility === "hidden" || style.opacity === "0")) {
        return false;
      }
    }
    return true;
  }

  const textPieces = [];

  function walk(node) {
    if (!node) return;

    if (node.nodeType === 3) {
      const val = (node.nodeValue || "").replace(/\s+/g, " ").trim();
      if (val.length > 0) {
        textPieces.push(val);
      }
      return;
    }

    if (node.nodeType === 1) {
      if (IGNORE_TAGS.has(node.tagName)) return;
      if (!isVisible(node)) return;

      const typeAttr = (node.getAttribute && node.getAttribute("type")) || "";
      if (typeAttr.toLowerCase() === "password") return;

      for (let child = node.firstChild; child; child = child.nextSibling) {
        walk(child);
      }
    }
  }

  try {
    walk(document.body);
  } catch (e) {
    const raw = document.body.innerText || "";
    textPieces.push(raw.replace(/\s+/g, " ").trim());
  }

  let fullText = textPieces.join(" ").replace(/\s+/g, " ").trim();
  let truncated = false;

  if (fullText.length > MAX_PAGE_TEXT_LENGTH) {
    fullText = fullText.slice(0, MAX_PAGE_TEXT_LENGTH);
    truncated = true;
  }

  return {
    text: fullText,
    title: title,
    url: url,
    truncated: truncated,
  };
}

// Message listener for popup/background
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg && (msg.type === "GET_TEXT" || msg.type === "GET_PAGE_DATA")) {
    const data = extractPageText();
    sendResponse(data);
  }
  return true;
});
