import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../../api";
import { navigate } from "../../app/router";
import { PageHeader, Drawer, ConfirmOperationModal } from "../../components/ConsoleUI";
import { ErrorBanner, describeError, Pagination } from "../../components/ui";
import type { Instance, Paginated } from "../../types";
import { SSHConnectionPane } from "./SSHConnectionPane";
import { addSSHTab, closeSSHTab } from "./sshTabs";

type TabInfo={state:string;name?:string};
const liveStates=["authorizing","connecting","hostkey","ready"];
const names:Record<string,string>={idle:"未连接",authorizing:"授权中",connecting:"连接中",hostkey:"待确认指纹",ready:"已连接",closed:"已断开",error:"失败"};
export default function VmSSHPage({id,admin}:{id:number;admin:boolean}) {
  const [tabs,setTabs]=useState<number[]>([id]),[active,setActive]=useState(id),[info,setInfo]=useState<Record<number,TabInfo>>({});
  const [limit,setLimit]=useState(8),[picker,setPicker]=useState(false),[error,setError]=useState<string|null>(null),
    [full,setFull]=useState(false),[disconnectEpoch,setDisconnectEpoch]=useState(0);
  const [search,setSearch]=useState(""),[page,setPage]=useState(1),[total,setTotal]=useState(0),
    [items,setItems]=useState<Instance[]>([]),[loading,setLoading]=useState(false);
  const [pending,setPending]=useState<{kind:"close"|"all"|"leave";id?:number}|null>(null);
  const workspace=useRef<HTMLElement>(null),tablist=useRef<HTMLDivElement>(null);
  const prefix=admin?"/admin":"/app";
  const connected=Object.values(info).filter(value=>liveStates.includes(value.state)).length;
  const report=useCallback((vmId:number,state:string,name?:string)=>{
    setInfo(previous=>previous[vmId]?.state===state && previous[vmId]?.name===name?previous:{...previous,[vmId]:{state,name}});
  },[]);
  useEffect(()=>{
    let alive=true;
    api.request<{max_sessions:number}>("/console/ssh-policy").then(policy=>{if(alive)setLimit(policy.max_sessions);})
      .catch(e=>{if(alive)setError(describeError(e));});
    return ()=>{alive=false;};
  },[]);
  useEffect(()=>{
    if(tabs.includes(id)){setActive(id);return;}
    if(tabs.length>=limit){setError(`最多打开 ${limit} 个标签，请先关闭不需要的标签`);return;}
    setTabs(previous=>addSSHTab(previous,id,limit));setActive(id);
  },[id]);
  useEffect(()=>{
    if(!connected)return;
    const warn=(event:BeforeUnloadEvent)=>{event.preventDefault();event.returnValue="";};
    window.addEventListener("beforeunload",warn);return()=>window.removeEventListener("beforeunload",warn);
  },[connected]);
  useEffect(()=>{
    if(!picker)return;
    const controller=new AbortController();setLoading(true);
    const timer=window.setTimeout(()=>{
      const query=new URLSearchParams({status:"RUNNING",search,page:String(page),page_size:"20"});
      api.request<Paginated<Instance>>(`/instances?${query}`,{signal:controller.signal})
        .then(result=>{if(!controller.signal.aborted){setItems(result.results);setTotal(result.count);setError(null);}})
        .catch(e=>{if(!controller.signal.aborted)setError(describeError(e));})
        .finally(()=>{if(!controller.signal.aborted)setLoading(false);});
    },200);
    return()=>{clearTimeout(timer);controller.abort();};
  },[picker,search,page]);
  function activate(vmId:number){setActive(vmId);navigate(`${prefix}/vms/${vmId}/ssh`);}
  function open(vm:Instance){
    const next=addSSHTab(tabs,vm.id,limit);
    if(next===tabs && !tabs.includes(vm.id)){setError(`最多打开 ${limit} 个标签`);return;}
    setTabs(next);setInfo(previous=>({...previous,[vm.id]:previous[vm.id]||{state:"idle",name:vm.name}}));
    activate(vm.id);setPicker(false);
  }
  function close(vmId:number){
    if(liveStates.includes(info[vmId]?.state)){setPending({kind:"close",id:vmId});return;}
    performClose(vmId);
  }
  function performClose(vmId:number){
    const next=closeSSHTab(tabs,active,vmId);setTabs(next.tabs);setActive(next.active);
    setInfo(previous=>{const copy={...previous};delete copy[vmId];return copy;});
    if(next.active && active===vmId)navigate(`${prefix}/vms/${next.active}/ssh`);
  }
  function leave(){if(connected)setPending({kind:"leave"});else navigate(`${prefix}/vms`);}
  return <section ref={workspace} className={"ssh-workspace"+(full?" ssh-workspace-full":"")}>
    <PageHeader title="SSH 多标签终端" description={`切换标签保持连接 · 每个账号最多 ${limit} 个 SSH 会话 · 离开终端页将断开所有连接`} back={{label:"返回虚拟机列表",onClick:leave}}>
      <button className="action" disabled={!connected} onClick={()=>setPending({kind:"all"})}>断开全部</button>
      <button className="action" onClick={()=>setFull(!full)}>{full?"退出页面全屏":"页面全屏"}</button>
      <button className="action" onClick={()=>void workspace.current?.requestFullscreen().catch(()=>setError("浏览器未允许全屏"))}>浏览器全屏</button>
      <button className="action primary" disabled={tabs.length>=limit} onClick={()=>{setSearch("");setPage(1);setPicker(true);}}>＋ 添加连接</button>
    </PageHeader>
    <ErrorBanner message={error}/>
    <div className="ssh-tab-strip" ref={tablist} role="tablist" aria-label="SSH 虚拟机连接">
      {tabs.map(vmId=><div className={"ssh-tab-item"+(active===vmId?" active":"")} key={vmId}>
        <button role="tab" id={`ssh-tab-${vmId}`} aria-selected={active===vmId} aria-controls={`ssh-panel-${vmId}`} tabIndex={active===vmId?0:-1}
          onClick={()=>activate(vmId)} onKeyDown={event=>{if(!["ArrowLeft","ArrowRight","Home","End"].includes(event.key))return;event.preventDefault();const index=tabs.indexOf(vmId);const target=event.key==="Home"?tabs[0]:event.key==="End"?tabs[tabs.length-1]:tabs[(index+(event.key==="ArrowRight"?1:tabs.length-1))%tabs.length];activate(target);tablist.current?.querySelector<HTMLButtonElement>(`#ssh-tab-${target}`)?.focus();}}>
          <span className={`ssh-tab-dot ssh-tab-${info[vmId]?.state||"idle"}`}/><span>{info[vmId]?.name||`虚拟机 #${vmId}`}<small>{names[info[vmId]?.state||"idle"]}</small></span>
        </button><button className="ssh-tab-close" aria-label={`关闭 ${info[vmId]?.name||vmId} 标签`} onClick={()=>close(vmId)}>×</button>
      </div>)}
    </div>
    {!tabs.length&&<div className="card empty">所有标签已关闭，点击“添加连接”选择自己的虚拟机。</div>}
    {tabs.map(vmId=><div role="tabpanel" id={`ssh-panel-${vmId}`} aria-labelledby={`ssh-tab-${vmId}`} hidden={active!==vmId} key={vmId}>
      <SSHConnectionPane id={vmId} admin={admin} visible={active===vmId} disconnectEpoch={disconnectEpoch} onChange={report}/>
    </div>)}
    {pending&&<ConfirmOperationModal target={pending.kind==="close"?(info[pending.id!]?.name||`虚拟机 #${pending.id}`):"全部 SSH 连接"}
      operation={pending.kind==="close"?"关闭标签并断开连接":pending.kind==="all"?"断开全部连接":"离开 SSH 终端页"}
      description={pending.kind==="close"?"将断开此标签的 SSH，前台命令可能中断。其他标签保持连接。":"将关闭所有 SSH 连接，前台命令可能中断；不会关闭虚拟机。"}
      busy={false} error={null} onCancel={()=>setPending(null)} onConfirm={()=>{const action=pending;setPending(null);if(action.kind==="close")performClose(action.id!);else if(action.kind==="all")setDisconnectEpoch(value=>value+1);else navigate(`${prefix}/vms`);}}/>}
    {picker&&<Drawer wide title="添加虚拟机 SSH 标签" onClose={()=>setPicker(false)}>
      <p className="muted">仅列出当前账号有权访问的运行中虚拟机；每个标签单独登录，凭据不共享。</p>
      <ErrorBanner message={error}/><input aria-label="搜索运行中的虚拟机" placeholder="按虚拟机名称或 UUID 搜索" value={search} onChange={event=>{setSearch(event.target.value);setPage(1);}}/>
      {loading?<p role="status">正在读取虚拟机…</p>:!items.length?<p className="empty">暂无匹配的运行中虚拟机。</p>:<div className="table-scroll"><table className="data-table"><thead><tr><th>虚拟机</th><th>节点</th><th>操作</th></tr></thead><tbody>{items.map(vm=><tr key={vm.id}><td><strong>{vm.name}</strong><small className="muted">{vm.uuid.slice(0,8)}</small></td><td>{vm.node_name}</td><td><button className="action sm" disabled={vm.observed_state_is_stale} onClick={()=>open(vm)}>{tabs.includes(vm.id)?"切换到标签":"打开标签"}</button></td></tr>)}</tbody></table></div>}
      <Pagination page={page} pageSize={20} total={total} onChange={setPage}/>
    </Drawer>}
  </section>;
}
