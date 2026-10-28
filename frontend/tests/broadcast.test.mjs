import test from "node:test";
import assert from "node:assert/strict";
import { buildSync } from "esbuild";
async function moduleFrom(entry) {
  const output = buildSync({
    entryPoints: [entry],
    bundle: true,
    write: false,
    format: "esm",
    platform: "browser",
    jsx: "automatic",
    define: { "process.env.NODE_ENV": '"production"' },
  });
  return import(
    "data:text/javascript;base64," +
      Buffer.from(output.outputFiles[0].text).toString("base64")
  );
}
const { parseWatchGrant } = await moduleFrom(
  "src/features/console/PublicWatchPage.tsx",
);
const { api } = await moduleFrom("src/api.ts");
test("watch links require both a broadcast UUID and a scoped fragment capability", () => {
  const id = "371cc72e-ecf9-4f23-a1b8-a949a0bd273d",
    token = "a".repeat(43);
  assert.deepEqual(parseWatchGrant("#" + id + "." + token), { id, token });
  for (const value of [
    "",
    id,
    "#" + id,
    "#" + id + ".short",
    "#bad." + token,
    "#" + id + "." + token + "?redirect=evil",
  ])
    assert.equal(parseWatchGrant(value), null);
});
test("public viewing omits platform cookies, CSRF and login redirects", async () => {
  const oldFetch = globalThis.fetch,
    oldDocument = globalThis.document,
    oldWindow = globalThis.window;
  const window = new EventTarget();
  let expired = 0,
    captured;
  window.addEventListener("cloudvirt:session-expired", () => expired++);
  globalThis.window = window;
  globalThis.document = { cookie: "csrftoken=platform-csrf" };
  globalThis.fetch = async (url, init) => {
    captured = { url, init };
    return new Response(
      JSON.stringify({
        error: { code: "UNAUTHORIZED", message: "expired", request_id: "test" },
      }),
      { status: 401 },
    );
  };
  try {
    await assert.rejects(
      api.request("/console/broadcasts/test/watch", {
        anonymous: true,
        method: "POST",
        headers: { "X-Stream-Token": "read-capability" },
        body: JSON.stringify({ sdp: "v=0" }),
      }),
    );
    assert.equal(captured.init.credentials, "omit");
    assert.equal(captured.init.headers.get("X-CSRFToken"), null);
    assert.equal(
      captured.init.headers.get("X-Stream-Token"),
      "read-capability",
    );
    assert.ok(!captured.url.includes("read-capability"));
    assert.equal(expired, 0);
  } finally {
    globalThis.fetch = oldFetch;
    globalThis.document = oldDocument;
    globalThis.window = oldWindow;
  }
});
