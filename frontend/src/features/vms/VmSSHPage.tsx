import { useEffect, useRef, useState } from "react";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import "@xterm/xterm/css/xterm.css";
import "./ssh.css";
import { api } from "../../api";
import { navigate } from "../../app/router";
import { PageHeader, ConfirmOperationModal } from "../../components/ConsoleUI";
import { ErrorBanner, describeError } from "../../components/ui";
import type { Instance } from "../../types";

type SSHSession = { session_id: string; path: string; address: string; port: number };
type HostKey = { fingerprint: string; algorithm: string; address: string };
export default function VmSSHPage({ id, admin }: { id: number; admin: boolean }) {
  const [vm,setVm] = useState<Instance|null>(null), [addresses,setAddresses] = useState<string[]>([]);
  const [address,setAddress] = useState(""), [user,setUser] = useState("");
  const [mode,setMode] = useState("password"), [password,setPassword] = useState(""),
    [privateKey,setPrivateKey] = useState(""), [passphrase,setPassphrase] = useState("");
  const [state,setState] = useState("idle"), [error,setError] = useState<string|null>(null),
    [hostKey,setHostKey] = useState<HostKey|null>(null), [full,setFull] = useState(false);
  const mount = useRef<HTMLDivElement>(null), terminal = useRef<Terminal|null>(null), fit = useRef<FitAddon|null>(null);
  const socket = useRef<WebSocket|null>(null), session = useRef<SSHSession|null>(null),
    renewal = useRef<number|undefined>(undefined), generation = useRef(0), busy = useRef(false), ready = useRef(false);
  const prefix = admin ? "/admin" : "/app";
  const active = !["idle","closed","error"].includes(state);
  const labels: Record<string,string> = { idle:"未连接",authorizing:"正在授权",connecting:"正在连接 SSH",hostkey:"等待确认主机指纹",ready:"已连接",closed:"连接已结束",error:"连接失败" };
  function send(message: unknown) { if (socket.current?.readyState === WebSocket.OPEN) socket.current.send(JSON.stringify(message)); }
  async function release() {
    clearInterval(renewal.current); renewal.current=undefined;
    const previous=session.current;session.current=null;
    if(previous) await api.request(`/console/sessions/${previous.session_id}`,{method:"DELETE"}).catch(()=>{});
  }
  async function disconnect() {
    generation.current++; ready.current=false;busy.current=true;
    socket.current?.close();socket.current=null;setHostKey(null);setState("closed");
    await release(); busy.current=false;
  }
  useEffect(()=>{
    const term = new Terminal({cursorBlink:true,fontSize:14,scrollback:3000,
      fontFamily:'"Cascadia Code", "SFMono-Regular", Consolas, monospace',theme:{background:"#101828",foreground:"#e2e8f0"}});
    const addon=new FitAddon();term.loadAddon(addon);term.open(mount.current!);addon.fit();
    terminal.current=term;fit.current=addon;
    const input=term.onData(data=>{ if(ready.current) send({type:"input",data}); });
    const resize=new ResizeObserver(()=>{addon.fit();if(ready.current)send({type:"resize",cols:Math.max(20,Math.min(512,term.cols)),rows:Math.max(5,Math.min(200,term.rows))});});resize.observe(mount.current!);
    return ()=>{generation.current++;ready.current=false;socket.current?.close();socket.current=null;void release();input.dispose();resize.disconnect();term.dispose();terminal.current=null;};
  },[id]);
  useEffect(()=>{
    let alive=true;
    setVm(null);setState("idle");setHostKey(null);setUser("");
    setPassword("");setPrivateKey("");setPassphrase("");busy.current=false;
    setError(null);setAddresses([]);setAddress("");
    Promise.allSettled([api.instance(id),api.request<{addresses:string[]}>(`/console/instances/${id}/ssh`)])
      .then(([instance,result])=>{if(!alive)return;
        if(instance.status === "fulfilled") setVm(instance.value);
        else setError(describeError(instance.reason));
        if(result.status === "fulfilled") {setAddresses(result.value.addresses);setAddress(result.value.addresses[0]||"");}
        else setError(describeError(result.reason));
      });
    return ()=>{alive=false;};
  },[id]);
  async function connect(event: React.FormEvent) {
    event.preventDefault(); if(busy.current || active || !address)return;
    busy.current=true;const current=++generation.current;
    setError(null);setState("authorizing");terminal.current?.reset();
    let created:SSHSession|null=null;
    try {
      await release();
      created=await api.request<SSHSession>(`/console/instances/${id}/ssh`,{method:"POST",body:JSON.stringify({address})});
      if(current!==generation.current){await api.request(`/console/sessions/${created.session_id}`,{method:"DELETE"}).catch(()=>{});return;}
      session.current=created;setState("connecting");
      const url=new URL(created.path,location.href);url.protocol=location.protocol==="https:"?"wss:":"ws:";
      const ws=new WebSocket(url);socket.current=ws;ws.binaryType="arraybuffer";
      ws.onopen=()=>{
        if(current!==generation.current){ws.close();return;}
        const term=terminal.current!;
        send({type:"auth",user,password:mode==="password"?password:"",private_key:mode==="key"?privateKey:"",passphrase:mode==="key"?passphrase:"",cols:Math.max(20,Math.min(512,term.cols)),rows:Math.max(5,Math.min(200,term.rows))});
        setPassword("");setPrivateKey("");setPassphrase("");
        let renewing=false;
        renewal.current=window.setInterval(()=>{
          if(renewing || !session.current)return;renewing=true;
          void api.request(`/console/sessions/${session.current.session_id}`,{method:"POST",body:"{}"})
            .catch(e=>{if(current===generation.current){setError(describeError(e));setState("error");ws.close();}}).finally(()=>{renewing=false;});
        },25000);
      };
      ws.onmessage=event=>{
        if(current!==generation.current)return;
        if(event.data instanceof ArrayBuffer){terminal.current?.write(new Uint8Array(event.data));return;}
        try {
          const message=JSON.parse(String(event.data));
          if(message.type==="hostkey"){setHostKey(message);setState("hostkey");}
          if(message.type==="ready"){ready.current=true;busy.current=false;setState("ready");terminal.current?.focus();}
          if(message.type==="error"){setError(message.message||"SSH 连接失败");setState("error");}
          if(message.type==="exit"){terminal.current?.writeln("\r\n[远程终端已结束]");}
        } catch { setError("SSH 协议响应无效");ws.close(); }
      };
      ws.onerror=()=>{if(current===generation.current){setError("SSH 通道连接失败，请检查节点代理和 HTTPS 反向代理");setState("error");}};
      ws.onclose=()=>{if(current===generation.current){ready.current=false;busy.current=false;setHostKey(null);setState(previous=>previous==="error"?previous:"closed");void release();}};
    } catch(e){if(current===generation.current){setError(describeError(e));setState("error");busy.current=false;await release();}}
  }
  return <section className={"ssh-page"+(active?" ssh-session-active":"")+(full?" ssh-page-full":"")}>
    <PageHeader title={`${vm?.name || "虚拟机"} · Web SSH`} description="通过加密终端配置客体系统；使用虚拟机内的账号权限" back={{label:"返回虚拟机",onClick:()=>navigate(`${prefix}/vms/${id}`)}}>
      <span className="ssh-state">{labels[state]}</span>
      <button className="action" onClick={()=>setFull(!full)}>{full?"退出页面全屏":"页面全屏"}</button>
      <button className="action" onClick={()=>void mount.current?.closest(".ssh-page")?.requestFullscreen().catch(()=>setError("浏览器未允许全屏"))}>浏览器全屏</button>
      <button className="action danger" disabled={!active} onClick={()=>void disconnect()}>断开连接</button>
    </PageHeader>
    <ErrorBanner message={error}/>
    {!active && <form className="ssh-connect card" onSubmit={connect}>
      <div className="ssh-connect-grid">
        <label>虚拟机地址<select value={address} onChange={e=>setAddress(e.target.value)} required>{!addresses.length&&<option value="">暂无已验证的 DHCP 地址</option>}{addresses.map(ip=><option key={ip} value={ip}>{ip}:22</option>)}</select></label>
        <label>SSH 用户名<input value={user} onChange={e=>setUser(e.target.value)} required maxLength={128} autoComplete="off" /></label>
        <label>认证方式<select value={mode} onChange={e=>setMode(e.target.value)}><option value="password">密码</option><option value="key">私钥</option></select></label>
        {mode==="password"?<label>SSH 密码<input type="password" value={password} onChange={e=>setPassword(e.target.value)} required autoComplete="off" maxLength={4096}/></label>:<><label className="ssh-key">SSH 私钥<textarea value={privateKey} onChange={e=>setPrivateKey(e.target.value)} required maxLength={65536} rows={5} autoComplete="off"/></label><label>私钥口令（可选）<input type="password" value={passphrase} onChange={e=>setPassphrase(e.target.value)} maxLength={4096} autoComplete="off"/></label></>}
      </div>
      <div className="ssh-connect-foot"><span>凭据仅用于本次连接，不保存；首次连接需核对主机指纹。</span><button type="submit" className="action primary" disabled={!address || !!vm?.observed_state_is_stale}>连接终端</button></div>
      {!addresses.length&&<p className="muted">请启动虚拟机、启用 SSH 服务并获取 DHCP 地址。静态 IP 暂不开放手工填写，可先通过 noVNC 配置网络。</p>}
    </form>}
    <div className="ssh-terminal-shell"><header><span>SSH · {address || "未选择地址"}</span><button className="action sm" onClick={()=>terminal.current?.clear()}>清空本地显示</button></header><div className="ssh-terminal" ref={mount}/></div>
    <p className="muted">Ctrl+C 发送终止信号；选中文字后右键复制，粘贴使用浏览器快捷键。关闭页面会断开 SSH，不自动重连；不提供文件管理或自动提权。</p>
    {hostKey&&<ConfirmOperationModal target={`${hostKey.address}:22`} operation="确认 SSH 主机指纹" busy={false} error={null} description="请通过可信渠道核对此指纹。确认后才会向 SSH 服务进行登录认证；本次信任不会写入持久配置。" onCancel={()=>void disconnect()} onConfirm={()=>{send({type:"trust",fingerprint:hostKey.fingerprint});setHostKey(null);setState("connecting");}}><pre className="ssh-fingerprint">{hostKey.algorithm}{"\n"}{hostKey.fingerprint}</pre></ConfirmOperationModal>}
  </section>;
}
