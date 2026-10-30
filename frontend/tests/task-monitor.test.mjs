import test from "node:test";
import assert from "node:assert/strict";
import { buildSync } from "esbuild";
const result = buildSync({entryPoints:["src/components/taskMonitor.ts"],bundle:true,write:false,format:"esm"});
const { monitorTask, taskPresentation } = await import("data:text/javascript;base64,"+Buffer.from(result.outputFiles[0].text).toString("base64"));
const tick = () => new Promise(resolve => setImmediate(resolve));
function environment(load) {
  const updates=[],errors=[],timers=new Map(); let serial=0, hidden=false;
  const monitor = monitorTask({load,update:t=>updates.push(t.status),error:e=>errors.push(e),hidden:()=>hidden,
    schedule:(fn,delay)=>{ timers.set(++serial,{fn,delay});return serial; },cancel:id=>timers.delete(id)});
  return {monitor,updates,errors,timers,setHidden:v=>{hidden=v;},fire(){ const [id,t]=timers.entries().next().value;timers.delete(id);t.fn(); }};
}
test("submitted tasks remain nonmodal; success terminates monitoring while failure is retained",async()=>{
  assert.deepEqual(taskPresentation("PENDING"),{terminal:false,failed:false,succeeded:false});
  const states=["PENDING","CREATING","SUCCEEDED"];
  const e=environment(async()=>({status:states.shift()}));
  await tick();e.fire();await tick();e.fire();await tick();
  assert.deepEqual(e.updates,["PENDING","CREATING","SUCCEEDED"]);assert.equal(e.timers.size,0);
  assert.equal(taskPresentation("FAILED").failed,true);
  const f=environment(async()=>({status:"FAILED"}));await tick();assert.deepEqual(f.updates,["FAILED"]);assert.equal(f.timers.size,0);
});
test("hidden pages pause requests, visibility resume refreshes, disposed responses are ignored",async()=>{
  let calls=0; const e=environment(async()=>{calls++;return {status:"PENDING"};});await tick();
  e.setHidden(true);e.fire();await tick();assert.equal(calls,1);
  e.setHidden(false);await e.monitor.refresh();assert.equal(calls,2);e.monitor.stop();assert.equal(e.timers.size,0);
  let resolve;const f=environment(()=>new Promise(r=>{resolve=r;}));f.monitor.stop();resolve({status:"FAILED"});await tick();assert.deepEqual(f.updates,[]);
});
test("network errors back off without replaying the operation or overlapping status requests",async()=>{
  const e=environment(async()=>{throw new Error("offline");});await tick();
  assert.equal([...e.timers.values()][0].delay,2000);e.fire();await tick();assert.equal([...e.timers.values()][0].delay,4000);e.monitor.stop();
  let resolve,calls=0;const f=environment(()=>{calls++;return new Promise(r=>{resolve=r;});});await f.monitor.refresh();assert.equal(calls,1);f.monitor.stop();resolve({status:"SUCCEEDED"});await tick();
});
