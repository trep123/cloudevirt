import test from "node:test";

import assert from "node:assert/strict";

// esbuild's async plugin isolates the real session lifecycle from the actual RFB transport.
import { build } from "esbuild";
const desktopBuild = await build({
  entryPoints: ["src/features/console/DesktopEngine.ts"],
  bundle: true,
  write: false,
  format: "esm",
  platform: "browser",
  plugins: [
    {
      name: "fake-rfb",
      setup(builder) {
        builder.onResolve({ filter: /^@novnc\/novnc$/ }, () => ({
          path: "rfb",
          namespace: "test",
        }));
        builder.onLoad({ filter: /.*/, namespace: "test" }, () => ({
          contents: `
      export default class RFB extends EventTarget {
        constructor(target,url,options){ super(); this.url=url; this.options=options; globalThis.__rfb.push(this); }
        disconnect(){ this.closed=true; } blur(){} focus(){} sendCredentials(){}
        clipboardPasteFrom(){} sendCtrlAltDel(){}
      }`,
        }));
      },
    },
  ],
});
const { DesktopEngine } = await import(
  "data:text/javascript;base64," +
    Buffer.from(desktopBuild.outputFiles[0].text).toString("base64")
);
async function settle() {
  for (let i = 0; i < 30; i++) await Promise.resolve();
}
function environment(t) {
  const names = [
    "window",
    "document",
    "location",
    "navigator",
    "fetch",
    "__rfb",
  ];
  const previous = new Map(
    names.map((name) => [
      name,
      Object.getOwnPropertyDescriptor(globalThis, name),
    ]),
  );
  const window = new EventTarget(),
    document = new EventTarget();
  document.cookie = "csrftoken=test";
  document.hidden = false;
  Object.defineProperties(globalThis, {
    window: { value: window, configurable: true, writable: true },
    document: { value: document, configurable: true, writable: true },
    location: {
      value: { protocol: "https:", host: "console.test" },
      configurable: true,
      writable: true,
    },
    navigator: { value: { onLine: true }, configurable: true, writable: true },
    __rfb: { value: [], configurable: true, writable: true },
  });
  const requests = [];
  globalThis.fetch = async (url, init) => {
    requests.push({ url, init });
    if (init.method === "DELETE") return new Response(null, { status: 204 });
    return new Response(
      JSON.stringify({
        session_id: "desktop-session",
        path: "/console-ws/desktop-session",
        password: "test",
      }),
      { status: 201 },
    );
  };
  t.after(() => {
    for (const [name, descriptor] of previous) {
      if (descriptor) Object.defineProperty(globalThis, name, descriptor);
      else delete globalThis[name];
    }
  });
  return requests;
}

test("desktop distinguishes handshake/draw and isolates stale connection callbacks", async (t) => {
  const requests = environment(t),
    states = [],
    metrics = [];
  const context = { drawImage() {} },
    canvas = {
      getContext() {
        return context;
      },
    };
  const target = {
    querySelector() {
      return canvas;
    },
    replaceChildren() {},
  };
  const engine = new DesktopEngine(
    target,
    1,
    (state) => states.push(state),
    (value) => metrics.push(value),
    () => {},
  );
  try {
    engine.start();
    await settle();
    const old = globalThis.__rfb[0];
    assert.ok(old.url.endsWith("/console-ws/desktop-session"));
    assert.ok(!old.url.includes("sig="));
    old.dispatchEvent(new Event("connect"));
    assert.equal(states.at(-1), "connected");
    assert.equal(metrics.at(-1).firstDrawMs, null);
    context.drawImage();
    assert.equal(states.at(-1), "rendering");
    assert.ok(metrics.at(-1).firstDrawMs !== null);
    engine.start();
    await settle();
    const before = states.at(-1);
    old.dispatchEvent(new Event("disconnect"));
    assert.equal(states.at(-1), before);
    engine.stop();
    assert.equal(states.at(-1), "closed");
    assert.ok(requests.some((request) => request.init.method === "DELETE"));
  } finally {
    engine.dispose();
  }
});

test("flapping desktop is bounded even when each short connection completes its handshake", async (t) => {
  environment(t);
  t.mock.timers.enable({ apis: ["setTimeout", "setInterval"] });
  const target = {
      querySelector() {
        return null;
      },
      replaceChildren() {},
    },
    states = [];
  const engine = new DesktopEngine(
    target,
    1,
    (state) => states.push(state),
    () => {},
    () => {},
  );
  try {
    engine.start();
    await settle();
    for (let index = 0; index < 4; index++) {
      const client = globalThis.__rfb.at(-1);
      client.dispatchEvent(new Event("connect"));
      client.dispatchEvent(new Event("disconnect"));
      if (index < 3) {
        assert.equal(states.at(-1), "reconnecting");
        t.mock.timers.tick(1000 * 2 ** (index + 1));
        await settle();
      }
    }
    assert.equal(states.at(-1), "failed");
    assert.equal(globalThis.__rfb.length, 4);
  } finally {
    engine.dispose();
  }
});
