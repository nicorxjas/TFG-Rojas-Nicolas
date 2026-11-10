import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import ts from "typescript";

// Exercise the actual handlers and effects without a browser, auth, or network.
function componentHarness(path, dependencies = {}) {
  const state = [];
  const cleanups = [];
  let cursor = 0;
  let mounting = true;
  const effects = [];
  const hooks = {
    useState(initial) {
      const index = cursor++;
      if (!(index in state)) state[index] = typeof initial === "function" ? initial() : initial;
      return [state[index], (next) => { state[index] = typeof next === "function" ? next(state[index]) : next; }];
    },
    useRef(initial) {
      const index = cursor++;
      if (!(index in state)) state[index] = { current: initial };
      return state[index];
    },
    useEffect(effect) { if (mounting) effects.push(effect); },
    useMemo(factory) { return factory(); },
    useCallback(callback) { return callback; },
  };
  const tags = new Proxy({ __esModule: true }, { get: (target, key) => target[key] ?? String(key) });
  const jsx = (type, props, key) => ({ type, props, key });
  const modules = {
    react: { __esModule: true, default: hooks, ...hooks },
    "react/jsx-runtime": { jsx, jsxs: jsx, Fragment: "fragment" },
    "next/dynamic": { __esModule: true, default: () => "DashboardCanvas" },
    "lucide-react": tags,
    "motion/react": { motion: tags },
    "./ChatInput": { __esModule: true, default: "ChatInput" },
    "../chat/ChatSidebar": { ChatSidebar: "ChatSidebar" },
    "@/lib/chat-events": { NEW_CHAT_EVENT: "nyro:new-chat" },
    "@/lib/chat-history": { buildChatHistory: (messages) => messages },
    "@/lib/supabase/client": { createClient: () => ({ auth: { getUser: async () => ({ data: { user: null } }) } }) },
    "@/lib/supabase/auth": { getSupabaseAuthHeaders: async () => ({ headers: {}, token: null }) },
    ...dependencies,
  };
  const source = readFileSync(new URL(path, import.meta.url), "utf8");
  const { outputText } = ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020,
    jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true,
  } });
  const module = { exports: {} };
  new Function("require", "module", "exports", outputText)((name) => modules[name] ?? tags, module, module.exports);
  return {
    render(name, props = {}) {
      cursor = 0;
      const result = module.exports[name](props);
      for (const effect of effects.splice(0)) cleanups.push(effect());
      mounting = false;
      return result;
    },
    dispose() { for (const cleanup of cleanups) if (typeof cleanup === "function") cleanup(); },
  };
}

function find(tree, type, predicate = () => true) {
  if (!tree || typeof tree !== "object") return undefined;
  if (tree.type === type && predicate(tree)) return tree;
  const children = tree.props?.children;
  for (const child of Array.isArray(children) ? children : [children]) {
    const match = find(child, type, predicate);
    if (match) return match;
  }
}

function fakeWindow() {
  const events = new EventTarget();
  return Object.assign(events, { clearTimeout, setTimeout, localStorage: { getItem: () => null } });
}

test("Nuevo chat dispatches reset on the current route and navigates from other pages", () => {
  const previousWindow = globalThis.window;
  try {
    for (const pathname of ["/dashboard", "/mis-tableros/example"]) {
      globalThis.window = fakeWindow();
      const destinations = [];
      let resets = 0;
      window.addEventListener("nyro:new-chat", () => { resets += 1; });
      const harness = componentHarness("../src/components/chat/Sidebar.tsx", {
        "next/navigation": { useRouter: () => ({ push: (path) => destinations.push(path) }), usePathname: () => pathname },
        "@/lib/store": { useSidebarStore: () => ({ isOpen: true, toggleSidebar() {} }) },
      });
      const tree = harness.render("default");
      find(tree, "button", (node) => node.props["aria-label"] === "Nuevo chat").props.onClick();
      assert.equal(resets, 1);
      assert.deepEqual(destinations, pathname === "/dashboard" ? [] : ["/dashboard"]);
      harness.dispose();
    }
  } finally {
    globalThis.window = previousWindow;
  }
});

test("new chat remounts the conversation without a dashboard canvas", () => {
  const previousWindow = globalThis.window;
  globalThis.window = fakeWindow();
  const harness = componentHarness("../src/components/layout/PlatformLayout.tsx");
  try {
    const oldChat = find(harness.render("PlatformLayout"), "ChatSidebar");
    window.dispatchEvent(new Event("nyro:new-chat"));
    const tree = harness.render("PlatformLayout");
    const newChat = find(tree, "ChatSidebar");
    assert.notEqual(newChat.key, oldChat.key);
    assert.equal(find(tree, "DashboardCanvas"), undefined);
    assert.equal(newChat.props.onStreamUpdate, undefined);
  } finally {
    harness.dispose();
    globalThis.window = previousWindow;
  }
});

test("new chat aborts an in-flight reader and suppresses its late content and completion", async () => {
  const previousWindow = globalThis.window;
  const previousFetch = globalThis.fetch;
  globalThis.window = fakeWindow();
  let finishRead;
  let requestSignal;
  let readerReady;
  const ready = new Promise((resolve) => { readerReady = resolve; });
  globalThis.fetch = async (_url, options) => {
    requestSignal = options.signal;
    return { ok: true, body: { getReader: () => ({ read: () => {
      readerReady();
      return new Promise((resolve) => { finishRead = resolve; });
    } }) } };
  };
  const updates = [];
  const streaming = [];
  const harness = componentHarness("../src/components/chat/ChatSidebar.tsx");
  try {
    const tree = harness.render("ChatSidebar", { onStreamUpdate: (value) => updates.push(value),
      onStreamingChange: (value) => streaming.push(value), isSidebarMode: false });
    const response = find(tree, "ChatInput").props.onSend("Pregunta sin sesión real");
    await ready;
    window.dispatchEvent(new Event("nyro:new-chat"));
    assert.equal(requestSignal.aborted, true);
    // Deliberately emulate a transport that still resolves after cancellation.
    finishRead({ done: false, value: new TextEncoder().encode('data: {"type":"chunk","content":"Respuesta anterior"}\n\n') });
    await response;
    assert.deepEqual(updates, []);
    assert.deepEqual(streaming, []);
  } finally {
    harness.dispose();
    globalThis.window = previousWindow;
    globalThis.fetch = previousFetch;
  }
});
