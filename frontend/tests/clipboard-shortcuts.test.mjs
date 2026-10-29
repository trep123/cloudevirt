import test from "node:test";
import assert from "node:assert/strict";
import { build } from "esbuild";
const bundle = await build({
  entryPoints: ["src/features/console/ClipboardShortcuts.ts"],
  bundle: true,
  write: false,
  format: "esm",
  platform: "browser",
});
const { ClipboardShortcuts } = await import(
  "data:text/javascript;base64," +
    Buffer.from(bundle.outputFiles[0].text).toString("base64")
);
function event(type, properties) {
  const e = new Event(type, { cancelable: true });
  for (const [k, v] of Object.entries(properties))
    Object.defineProperty(e, k, { value: v });
  return e;
}
test("native paste forwards text and terminal shortcut without clipboard polling", () => {
  const target = new EventTarget(),
    calls = [],
    messages = [];
  const bridge = new ClipboardShortcuts(target, {
    enabled: () => true,
    paste: (text) => calls.push(text),
    shortcut: (...args) => calls.push(args),
    report: (m) => messages.push(m),
  });
  try {
    const key = event("keydown", {
      key: "v",
      code: "KeyV",
      ctrlKey: true,
      shiftKey: true,
    });
    target.dispatchEvent(key);
    assert.equal(
      key.defaultPrevented,
      false,
      "native paste event must remain possible",
    );
    const paste = event("paste", {
      clipboardData: { getData: () => "hello 中文" },
    });
    target.dispatchEvent(paste);
    assert.equal(paste.defaultPrevented, true);
    assert.deepEqual(calls, ["hello 中文", ["v", true]]);
    target.dispatchEvent(
      event("paste", { clipboardData: { getData: () => "a".repeat(65537) } }),
    );
    assert.equal(calls.length, 2);
    assert.equal(messages.length, 1);
  } finally {
    bridge.dispose();
  }
});
test("copy writes only guest data received after an explicit copy request", async (t) => {
  const old = Object.getOwnPropertyDescriptor(globalThis, "navigator"),
    writes = [];
  Object.defineProperty(globalThis, "navigator", {
    value: { clipboard: { writeText: async (s) => writes.push(s) } },
    configurable: true,
  });
  t.after(() => {
    if (old) Object.defineProperty(globalThis, "navigator", old);
    else delete globalThis.navigator;
  });
  const target = new EventTarget(),
    calls = [];
  const bridge = new ClipboardShortcuts(target, {
    enabled: () => true,
    paste: () => {},
    shortcut: (...a) => calls.push(a),
    report: () => {},
  });
  try {
    bridge.receive("unsolicited");
    assert.deepEqual(writes, []);
    target.dispatchEvent(
      event("keydown", {
        key: "c",
        code: "KeyC",
        ctrlKey: true,
        shiftKey: false,
      }),
    );
    bridge.receive("selected text");
    await Promise.resolve();
    assert.deepEqual(writes, ["selected text"]);
    assert.deepEqual(calls, [["c", false]]);
    bridge.receive("later");
    assert.equal(writes.length, 1);
  } finally {
    bridge.dispose();
  }
});
test("read-only and disposed consoles do not intercept native shortcuts", () => {
  const target = new EventTarget();
  let count = 0;
  const bridge = new ClipboardShortcuts(target, {
    enabled: () => false,
    paste: () => count++,
    shortcut: () => count++,
    report: () => count++,
  });
  const paste = event("paste", { clipboardData: { getData: () => "secret" } });
  target.dispatchEvent(paste);
  assert.equal(paste.defaultPrevented, false);
  assert.equal(count, 0);
  bridge.dispose();
  target.dispatchEvent(paste);
  assert.equal(count, 0);
});
