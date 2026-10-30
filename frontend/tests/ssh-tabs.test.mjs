import test from "node:test";
import assert from "node:assert/strict";
import { buildSync } from "esbuild";
const result=buildSync({entryPoints:["src/features/vms/sshTabs.ts"],bundle:true,write:false,format:"esm"});
const {addSSHTab,closeSSHTab}=await import("data:text/javascript;base64,"+Buffer.from(result.outputFiles[0].text).toString("base64"));
test("opening an existing VM reuses its tab and a new VM respects capacity",()=>{
 const tabs=[11,22];assert.equal(addSSHTab(tabs,11,8),tabs);assert.deepEqual(addSSHTab(tabs,33,8),[11,22,33]);
 assert.equal(addSSHTab(tabs,33,2),tabs);assert.equal(addSSHTab(tabs,-1,8),tabs);
});
test("closing a background tab preserves the active connection identity",()=>{
 assert.deepEqual(closeSSHTab([11,22,33],22,11),{tabs:[22,33],active:22});
});
test("closing the active tab selects a surviving neighbor and last close empties workspace",()=>{
 assert.deepEqual(closeSSHTab([11,22,33],22,22),{tabs:[11,33],active:33});
 assert.deepEqual(closeSSHTab([11,22,33],33,33),{tabs:[11,22],active:22});
 assert.deepEqual(closeSSHTab([11],11,11),{tabs:[],active:0});
});
