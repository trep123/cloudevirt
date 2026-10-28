import fs from "node:fs";
import path from "node:path";
import net from "node:net";
import crypto from "node:crypto";
import { spawn, spawnSync } from "node:child_process";
import { chromium } from "playwright-core";

const credentials=process.env.CREDENTIALS_DIRECTORY;
const spec=JSON.parse(fs.readFileSync(path.join(credentials,"spec"),"utf8"));
const state=process.env.STATE_DIRECTORY;
const origin=new URL(spec.origin).origin;
const children=[];let context,finishing=false,resolveStop;
const stopped=new Promise(resolve=>{resolveStop=resolve;});
function status(value,error=""){
 const temporary=path.join(state,"status.next");
 fs.writeFileSync(temporary,JSON.stringify({state:value,error,generation:spec.generation,updated_at:new Date().toISOString()}),{mode:0o600});
 fs.renameSync(temporary,path.join(state,"status.json"));
}
function stop(){finishing=true;resolveStop();}
process.on("SIGTERM",stop);process.on("SIGINT",stop);
function child(command,args,env){
 const process=spawn(command,args,{env,stdio:["ignore","ignore","ignore"]});children.push(process);
 process.on("error",()=>{if(!finishing){status("ERROR","DISPLAY_PROCESS_FAILED");stop();}});
 process.on("exit",()=>{if(!finishing){status("ERROR","DISPLAY_PROCESS_EXITED");stop();}});
 return process;
}
async function until(check){
 const deadline=Date.now()+15000;
 while(Date.now()<deadline&&!finishing){if(await check())return;await new Promise(resolve=>setTimeout(resolve,100));}
 throw new Error("WORKBENCH_START_TIMEOUT");
}
async function main(){
 status("STARTING");
 const home=state,display=":"+spec.display,authority=path.join(state,"Xauthority");
 fs.mkdirSync(path.join(home,".pki/nssdb"),{recursive:true,mode:0o700});
 const certdb="sql:"+path.join(home,".pki/nssdb");
 if(!fs.existsSync(path.join(home,".pki/nssdb/cert9.db"))){
  if(spawnSync("/usr/bin/certutil",["-N","--empty-password","-d",certdb],{stdio:"ignore"}).status!==0)throw new Error("CERT_DB_FAILED");
 }
 if(fs.existsSync(path.join(credentials,"ca"))){
  if(spawnSync("/usr/bin/certutil",["-A","-d",certdb,"-n","cloudvirt-platform","-t","C,,","-i",path.join(credentials,"ca")],{stdio:"ignore"}).status!==0)throw new Error("CERT_IMPORT_FAILED");
 }
 fs.writeFileSync(authority,"",{mode:0o600});
 const cookie=crypto.randomBytes(16).toString("hex");
 if(spawnSync("/usr/bin/xauth",["-f",authority],{input:"add "+display+" MIT-MAGIC-COOKIE-1 "+cookie+"\n",stdio:["pipe","ignore","ignore"]}).status!==0)throw new Error("XAUTH_FAILED");
 const env={...process.env,HOME:home,DISPLAY:display,XAUTHORITY:authority};
 child("/usr/bin/Xvfb",[display,"-screen","0","1440x900x24","-nolisten","tcp","-auth",authority,"-noreset"],env);
 await until(()=>fs.existsSync("/tmp/.X11-unix/X"+spec.display));
 const passwordFile=path.join(state,"vnc-password");
 fs.writeFileSync(passwordFile,spec.vnc_password+"\n",{mode:0o600});
 child("/usr/bin/x11vnc",["-display",display,"-auth",authority,"-localhost","-rfbport",String(spec.port),"-passwdfile",passwordFile,"-forever","-shared","-noxdamage","-quiet"],env);
 await until(()=>new Promise(resolve=>{
  const socket=net.connect({host:"127.0.0.1",port:spec.port});
  socket.once("connect",()=>{socket.destroy();resolve(true);});socket.once("error",()=>resolve(false));
 }));
 context=await chromium.launchPersistentContext(path.join(state,"browser"),{
  executablePath:spec.chrome,headless:false,chromiumSandbox:true,viewport:null,
  acceptDownloads:false,env,args:["--kiosk","--window-size=1440,900","--window-position=0,0","--disable-dev-shm-usage","--no-default-browser-check"],
 });
 const page=context.pages()[0]||await context.newPage();
 await context.routeWebSocket("**/*",socket=>{
  if(new URL(socket.url()).host===new URL(origin).host)socket.connectToServer();
  else socket.close();
 });
 await context.route("**/*",route=>{
  const url=new URL(route.request().url());
  if(url.origin===origin || url.protocol==="data:" || (url.protocol==="blob:" && url.origin===origin))return route.continue();
  return route.abort("blockedbyclient");
 });
 context.on("page",popup=>{if(popup!==page)void popup.close();});
 page.on("filechooser",chooser=>void chooser.setFiles([]));
 await page.goto(origin+"/workbench-entry#"+spec.workspace+"."+spec.bootstrap_token,{waitUntil:"domcontentloaded",timeout:30000});
 await page.waitForURL(url=>url.origin===origin && !["/workbench-entry","/login"].includes(url.pathname),{timeout:30000});
 const identity=await page.evaluate(async()=>{const response=await fetch("/api/v1/auth/me");if(!response.ok)return null;return response.json();});
 if(identity?.id!==spec.owner || identity?.workbench_id!==spec.workspace)throw new Error("WORKBENCH_IDENTITY_MISMATCH");
 status("READY");
 const expiry=setTimeout(stop,Math.max(1,spec.expires_at*1000-Date.now()));
 context.on("close",stop);
 await stopped;clearTimeout(expiry);
}
try{await main();}catch{status("ERROR","BROWSER_SESSION_FAILED");process.exitCode=1;}
finally{
 finishing=true;
 try{await context?.close();}catch{}
 children.reverse().forEach(process=>{try{process.kill("SIGTERM");}catch{}});
 if(!process.exitCode)status("STOPPED");
}
