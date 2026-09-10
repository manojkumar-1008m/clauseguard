const fs = require("fs");
const vm = require("vm");

const analyzerSource = fs.readFileSync("extension/analyzer/analyzer.js", "utf8");
const rulesSource = fs.readFileSync("extension/analyzer/rules.js", "utf8");

const context = {
  console,
  URL,
  require: undefined,
  ANALYZER_RULES: undefined
};
vm.createContext(context);
vm.runInContext(rulesSource, context);
vm.runInContext(analyzerSource, context);

const events = [
  {
    event_id: "evt-1",
    session_id: "session-a",
    tab_id: 10,
    timestamp: new Date().toISOString(),
    action: "CLICK",
    route: "/account",
    url: "http://localhost",
    element: { tag: "button", role: "button", text: "Cancel Subscription", visible: true, disabled: false },
    text: "Cancel Subscription"
  },
  {
    event_id: "evt-2",
    session_id: "session-a",
    tab_id: 10,
    timestamp: new Date().toISOString(),
    action: "NAVIGATION",
    route: "/cancel",
    url: "http://localhost",
    element: null,
    text: ""
  },
  {
    event_id: "evt-3",
    session_id: "session-a",
    tab_id: 10,
    timestamp: new Date().toISOString(),
    action: "CLICK",
    route: "/cancel",
    url: "http://localhost",
    element: { tag: "button", role: "button", text: "No Thanks", visible: true, disabled: false },
    text: "No Thanks"
  }
];

const result = context.analyzeBehavior(events);
if (!result || !result.features || !result.intent) throw new Error("Analyzer did not accept B1 event schema");
if (result.features.generalIntent?.type !== "CANCEL") throw new Error("Structured element text was not classified as CANCEL");

const content = fs.readFileSync("extension/content.js", "utf8");
const background = fs.readFileSync("extension/background.js", "utf8");

for (const token of ["page_load_id", "elementContext", "PAGE_INIT", "history.pushState", "history.replaceState", "INPUT_CHANGE"]) {
  if (!content.includes(token)) throw new Error(`content.js missing B1 feature: ${token}`);
}
for (const token of ["session_id", "tab_id", "window_id", "SESSIONS_KEY", "TAB_SESSIONS_KEY", "tabs.onRemoved"]) {
  if (!background.includes(token)) throw new Error(`background.js missing B1 feature: ${token}`);
}
if (content.includes("element.value") || content.includes("target.value")) {
  throw new Error("Potential sensitive input value capture detected");
}

console.log("B1 foundation checks passed.");
