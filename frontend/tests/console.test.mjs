import test from "node:test";
import assert from "node:assert/strict";
import { buildSync } from "esbuild";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

// Compile the actual modules in memory; no browser or mock backend is required.
async function moduleFrom(entry) {
  const result = buildSync({
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
      Buffer.from(result.outputFiles[0].text).toString("base64")
  );
}
const { canEnterRoute } = await moduleFrom("src/app/permission.ts");
const { validateAddress } = await moduleFrom(
  "src/features/networks/validateAddress.ts",
);
const { api, ApiError } = await moduleFrom("src/api.ts");
const { Card, StatusBadge, ErrorBanner } = await moduleFrom(
  "src/components/ui.tsx",
);

test("ordinary user cannot enter any admin URL even with resource permissions", () => {
  const user = {
    console_scope: "user",
    permissions: ["instances.view_instance"],
  };
  assert.equal(canEnterRoute(user, "/admin/vms/42"), false);
  assert.equal(canEnterRoute(user, "/app/vms/42"), true);
  assert.equal(canEnterRoute(user, "/app/vms/create"), false);
});
test("administrator still needs route capability", () => {
  assert.equal(
    canEnterRoute({ console_scope: "admin", permissions: [] }, "/admin/users"),
    false,
  );
});
test("infrastructure administration and snapshot routes preserve role boundaries", () => {
  const user = {
    console_scope: "user",
    permissions: ["instances.view_instance"],
  };
  for (const key of ["clusters", "pools", "storage-pools", "settings"]) {
    assert.equal(canEnterRoute(user, `/admin/${key}`), false);
    assert.equal(canEnterRoute(user, `/app/${key}`), false);
  }
  assert.equal(canEnterRoute(user, "/app/snapshots"), true);
  assert.equal(
    canEnterRoute({ console_scope: "user", permissions: [] }, "/app/snapshots"),
    false,
  );
});
test("network wizard rejects overlapping subnets and a DHCP pool containing gateway", () => {
  const config = {
    subnet: "192.168.10.0/24",
    gateway: "192.168.10.1",
    dhcp_enabled: true,
    dhcp_start: "192.168.10.100",
    dhcp_end: "192.168.10.200",
  };
  assert.equal(validateAddress(config, []), null);
  assert.match(validateAddress(config, ["192.168.10.0/25"]), /重叠/);
  assert.match(
    validateAddress({ ...config, dhcp_start: "192.168.10.1" }, []),
    /网关/,
  );
});
test("resource status is localized and error banner exposes readable failure", () => {
  assert.match(
    renderToStaticMarkup(createElement(StatusBadge, { status: "RUNNING" })),
    /运行中/,
  );
  assert.match(
    renderToStaticMarkup(
      createElement(ErrorBanner, { message: "无权限 [PERMISSION_DENIED]" }),
    ),
    /PERMISSION_DENIED/,
  );
});
test("card retains resource title and empty state content", () => {
  const html = renderToStaticMarkup(
    createElement(
      Card,
      { title: "虚拟机" },
      createElement("p", null, "暂无数据"),
    ),
  );
  assert.match(html, /虚拟机/);
  assert.match(html, /暂无数据/);
});
test("HTML proxy failures become an actionable ApiError", async (t) => {
  t.mock.method(
    globalThis,
    "fetch",
    async () =>
      new Response("<html>Bad gateway</html>", {
        status: 502,
        headers: { "X-Request-ID": "request-502" },
      }),
  );
  await assert.rejects(
    api.request("/instances"),
    (e) =>
      e instanceof ApiError &&
      e.code === "INVALID_RESPONSE" &&
      e.requestId === "request-502",
  );
});
test("API errors retain server code and request id", async (t) => {
  t.mock.method(
    globalThis,
    "fetch",
    async () =>
      new Response(
        JSON.stringify({
          error: {
            code: "PERMISSION_DENIED",
            message: "无权访问",
            request_id: "request-403",
            details: {},
          },
        }),
        { status: 403 },
      ),
  );
  await assert.rejects(
    api.request("/instances/42"),
    (e) =>
      e instanceof ApiError &&
      e.status === 403 &&
      e.requestId === "request-403",
  );
});
test("create requests preserve caller idempotency key and CSRF token", async (t) => {
  globalThis.document = { cookie: "csrftoken=csrf-value" };
  let sent;
  t.mock.method(globalThis, "fetch", async (_url, init) => {
    sent = init;
    return new Response(
      JSON.stringify({ instance: { id: 1 }, task: { id: "task-1" } }),
      { status: 202 },
    );
  });
  await api.createInstance(
    {
      name: "vm-owned",
      node: 1,
      image: 1,
      vcpu: 1,
      memory_mib: 512,
      disk_gib: 5,
    },
    "stable-key",
  );
  assert.equal(sent.headers.get("Idempotency-Key"), "stable-key");
  assert.equal(sent.headers.get("X-CSRFToken"), "csrf-value");
  assert.equal(sent.credentials, "same-origin");
});
