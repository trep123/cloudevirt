import test from "node:test";
import assert from "node:assert/strict";
import { buildSync } from "esbuild";
const result = buildSync({entryPoints:["src/features/users/permissionSelection.ts"], bundle:true,write:false,format:"esm"});
const { selectPermissions } = await import("data:text/javascript;base64," + Buffer.from(result.outputFiles[0].text).toString("base64"));
const permission = (code, dependencies = [], assignable = true) => ({code,name:code,module:code.split(".")[0],dependencies,assignable});
const catalog = [permission("instances.view_instance"),permission("nodes.view_node"),permission("images.view_image"),permission("networks.view_network"),
  permission("instances.add_instance", ["instances.view_instance","nodes.view_node","images.view_image","networks.view_network"]),
  permission("instances.manage_snapshot_instance", ["instances.view_instance"]),permission("accounts.manage_user", [], false)];
test("create VM selection includes cross-module dependencies and never grants admin permissions", () => {
  assert.deepEqual(selectPermissions([], ["instances.add_instance","accounts.manage_user","missing"], true, catalog),
    ["images.view_image","instances.add_instance","instances.view_instance","networks.view_network","nodes.view_node"]);
});
test("removing a required view removes dependent actions but preserves unrelated actions", () => {
  const selected = selectPermissions([], ["instances.add_instance","instances.manage_snapshot_instance"], true, catalog);
  const remaining = selectPermissions(selected, ["images.view_image"], false, catalog);
  assert.ok(!remaining.includes("instances.add_instance"));
  assert.ok(remaining.includes("instances.manage_snapshot_instance"));
  assert.deepEqual(selectPermissions(remaining,["instances.view_instance"],false,catalog),["networks.view_network","nodes.view_node"]);
});
test("copying built-in permissions filters privileged capabilities and keeps valid business dependencies", () => {
  assert.deepEqual(selectPermissions([], catalog.map(p => p.code),true,catalog), catalog.filter(p => p.assignable).map(p => p.code).sort());
});
