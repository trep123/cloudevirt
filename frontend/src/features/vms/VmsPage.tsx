import { lazy, Suspense, useEffect, useState } from "react";
import { api } from "../../api";
import { navigate } from "../../app/router";
import {
  PageHeader,
  ConfirmOperationModal,
  TaskProgressDrawer,
} from "../../components/ConsoleUI";
import {
  Card,
  StatusBadge,
  ErrorBanner,
  describeError,
  formatTime,
} from "../../components/ui";
const VncConsole = lazy(() =>
  import("../../components/VncConsole").then((module) => ({
    default: module.VncConsole,
  })),
);
import { VmWizard } from "./VmWizard";
import { SnapshotsPage } from "../infrastructure/SnapshotsPage";
import type { CurrentUser, Instance, Paginated } from "../../types";
const ACTIVE = [
  "PENDING",
  "VALIDATING",
  "PREPARING",
  "CREATING",
  "VERIFYING",
  "RECONCILING",
];
const TABS = [
  "概览",
  "监控",
  "硬件",
  "磁盘",
  "网络",
  "快照",
  "任务日志",
  "权限",
];
export function VmsPage({ user, path }: { user: CurrentUser; path: string }) {
  const [items, setItems] = useState<Instance[]>([]),
    [total, setTotal] = useState(0),
    [detail, setDetail] = useState<Instance | null>(null),
    [error, setError] = useState<string | null>(null),
    [loading, setLoading] = useState(true);
  const [search, setSearch] = useState(
      new URLSearchParams(location.search).get("search") || "",
    ),
    [status, setStatus] = useState(""),
    [node, setNode] = useState(""),
    [page, setPage] = useState(1),
    [tab, setTab] = useState("概览"),
    [consoleOpen, setConsoleOpen] = useState(false),
    [taskId, setTaskId] = useState<string | null>(null),
    [pending, setPending] = useState<{ vm: Instance; action: string } | null>(
      null,
    ),
    [busy, setBusy] = useState(false),
    [refresh, setRefresh] = useState(0);
  const prefix = path.startsWith("/admin") ? "/admin" : "/app",
    admin = prefix === "/admin",
    rawId = path.split("/")[3],
    id = rawId && rawId !== "create" ? Number(rawId) : null;
  const can = (p: string) => user.permissions.includes(p);
  useEffect(() => {
    setSearch(new URLSearchParams(location.search).get("search") || "");
  }, [path, location.search]);
  useEffect(() => {
    let alive = true,
      working = false;
    const load = async () => {
      if (working || document.hidden) return;
      working = true;
      try {
        if (id) {
          const vm = await api.instance(id);
          if (alive) setDetail(vm);
        } else {
          const params = new URLSearchParams({
            page: String(page),
            page_size: "20",
            search,
            status,
            node,
          });
          const data = await api.request<Paginated<Instance>>(
            "/instances?" + params,
          );
          if (alive) {
            setItems(data.results);
            setTotal(data.count);
          }
        }
        if (alive) setError(null);
      } catch (e) {
        if (alive) setError(describeError(e));
      } finally {
        working = false;
        if (alive) setLoading(false);
      }
    };
    setLoading(true);
    if (id) setDetail(null);
    void load();
    const timer = setInterval(() => void load(), 15000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [id, page, search, status, node, refresh]);
  async function execute() {
    if (!pending || busy) return;
    setBusy(true);
    setError(null);
    try {
      const result =
        pending.action === "delete"
          ? await api.deleteInstance(pending.vm.id, false)
          : await api.instanceAction(pending.vm.id, pending.action);
      if (result.task) setTaskId(result.task.id);
      setPending(null);
      setRefresh((v) => v + 1);
    } catch (e) {
      setError(describeError(e));
    } finally {
      setBusy(false);
    }
  }
  function actions(vm: Instance) {
    const active = ACTIVE.includes(vm.operation_status),
      running = vm.observed_state === "RUNNING",
      stopped = vm.observed_state === "SHUTOFF";
    return (
      <div className="actions">
        <button
          className="action"
          disabled={!running || active}
          title={!running ? "运行后可打开控制台" : ""}
          onClick={() => {
            setConsoleOpen(true);
            navigate(prefix + "/vms/" + vm.id);
          }}
        >
          控制台
        </button>
        {stopped && can("instances.start_instance") ? (
          <button
            className="action"
            disabled={active || busy}
            onClick={() => setPending({ vm, action: "start" })}
          >
            启动
          </button>
        ) : null}
        {running && can("instances.shutdown_instance") ? (
          <button
            className="action"
            disabled={active || busy}
            onClick={() => setPending({ vm, action: "shutdown" })}
          >
            正常关机
          </button>
        ) : null}
        <details className="row-menu">
          <summary>更多 ▾</summary>
          <div>
            {running && can("instances.reboot_instance") ? (
              <button
                disabled={active || busy}
                onClick={() => setPending({ vm, action: "reboot" })}
              >
                重启
              </button>
            ) : null}
            {running && can("instances.force_stop_instance") ? (
              <button
                className="danger-text"
                disabled={active || busy}
                onClick={() => setPending({ vm, action: "force-stop" })}
              >
                强制关机
              </button>
            ) : null}
            {stopped && can("instances.delete_instance") ? (
              <button
                className="danger-text"
                disabled={active || busy}
                onClick={() => setPending({ vm, action: "delete" })}
              >
                删除（保留磁盘）
              </button>
            ) : null}
            <button onClick={() => navigate(prefix + "/tasks")}>
              查看任务
            </button>
          </div>
        </details>
      </div>
    );
  }
  if (rawId && rawId !== "create" && !/^\d+$/.test(rawId)) {
    return (
      <Card title="404 · 虚拟机不存在">
        <p>请从授权资源列表选择虚拟机。</p>
      </Card>
    );
  }
  if (rawId === "create")
    return can("instances.add_instance") ? (
      <VmWizard
        onCreated={(id) => {
          setTaskId(id);
          navigate(prefix + "/vms");
        }}
        onCancel={() => navigate(prefix + "/vms")}
      />
    ) : (
      <Card title="无权访问">
        <p>没有创建虚拟机权限。</p>
      </Card>
    );
  return (
    <>
      <ErrorBanner message={error} />
      {id ? (
        <>
          <PageHeader
            title={detail?.name || "虚拟机详情"}
            description={
              detail
                ? `UUID：${detail.uuid} · 所属节点：${detail.node_name}`
                : "正在读取资源"
            }
          >
            <button
              className="action"
              onClick={() => navigate(prefix + "/vms")}
            >
              返回列表
            </button>
            {detail ? actions(detail) : null}
          </PageHeader>
          {detail && !loading ? (
            <>
              <div className="detail-summary">
                <StatusBadge status={detail.observed_state} />
                <span>QEMU / KVM</span>
                <span>{detail.vcpu} vCPU</span>
                <span>{detail.memory_mib / 1024} GB 内存</span>
                <span>{detail.disk_gib} GB 磁盘</span>
              </div>
              {detail.observed_state_is_stale ? (
                <div className="banner banner-info">
                  观测数据已过期 · 最后更新{" "}
                  {formatTime(detail.observed_state_updated_at)}
                </div>
              ) : null}
              <nav className="detail-tabs" aria-label="虚拟机详情">
                {TABS.filter((t) => admin || t !== "权限").map((t) => (
                  <button
                    key={t}
                    className={t === tab ? "active" : ""}
                    onClick={() => setTab(t)}
                  >
                    {t}
                  </button>
                ))}
              </nav>
              <Card title={tab}>
                {tab === "概览" ? (
                  <>
                    <dl className="info-grid">
                      <dt>名称</dt>
                      <dd>{detail.name}</dd>
                      <dt>节点</dt>
                      <dd>{detail.node_name}</dd>
                      <dt>镜像</dt>
                      <dd>{detail.image_name}</dd>
                      <dt>网络</dt>
                      <dd>{detail.network_name || "未接入"}</dd>
                      <dt>期望状态</dt>
                      <dd>{detail.desired_state}</dd>
                      <dt>最近观测</dt>
                      <dd>{formatTime(detail.observed_state_updated_at)}</dd>
                      <dt>创建时间</dt>
                      <dd>{formatTime(detail.created_at)}</dd>
                    </dl>
                    {detail.last_error_message ? (
                      <p role="alert">
                        {detail.last_error_code}：{detail.last_error_message}
                      </p>
                    ) : null}
                  </>
                ) : tab === "硬件" ? (
                  <dl className="info-grid">
                    <dt>处理器</dt>
                    <dd>{detail.vcpu} 核</dd>
                    <dt>内存</dt>
                    <dd>{detail.memory_mib / 1024} GB</dd>
                    <dt>系统盘</dt>
                    <dd>{detail.disk_gib} GB · qcow2</dd>
                    <dt>硬件编辑</dt>
                    <dd>当前后端尚未提供硬件变更 API</dd>
                  </dl>
                ) : tab === "磁盘" ? (
                  <table>
                    <thead>
                      <tr>
                        <th>名称</th>
                        <th>容量</th>
                        <th>状态</th>
                        <th>设备</th>
                      </tr>
                    </thead>
                    <tbody>
                      {detail.disks.map((d) => (
                        <tr key={d.id}>
                          <td>{d.name}</td>
                          <td>{d.size_gib} GB</td>
                          <td>
                            <StatusBadge status={d.status} />
                          </td>
                          <td>{d.target_dev}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : tab === "网络" ? (
                  <p>
                    已登记网络：{detail.network_name || "未接入"}
                    。实际网卡连接可在网络拓扑中查看。
                  </p>
                ) : tab === "快照" ? (
                  <SnapshotsPage
                    admin={user.console_scope === "admin"}
                    instance={detail}
                  />
                ) : tab === "任务日志" ? (
                  <button
                    className="action"
                    onClick={() => navigate(prefix + "/tasks")}
                  >
                    打开授权任务中心
                  </button>
                ) : (
                  <div className="chart-empty">
                    暂无{tab}数据<p>当前后端尚未提供此能力。</p>
                  </div>
                )}
              </Card>
              {consoleOpen && detail.observed_state === "RUNNING" ? (
                <Card title="远程控制台">
                  <button
                    className="action"
                    onClick={() => setConsoleOpen(false)}
                  >
                    关闭控制台
                  </button>
                  <Suspense fallback={<p role="status">正在加载远程控制台…</p>}>
                    <VncConsole instanceId={detail.id} />
                  </Suspense>
                </Card>
              ) : null}
            </>
          ) : (
            <p role="status">
              {loading
                ? "正在读取虚拟机…"
                : error
                  ? "无法读取该资源"
                  : "资源不存在或无权访问"}
            </p>
          )}
        </>
      ) : (
        <>
          <PageHeader
            title={admin ? "虚拟机" : "我的虚拟机"}
            description="管理授权范围内的实例，资源状态以服务端观测结果为准"
          >
            <button className="action" onClick={() => setRefresh((v) => v + 1)}>
              刷新
            </button>
            {can("instances.add_instance") ? (
              <button
                className="action primary"
                onClick={() => navigate(prefix + "/vms/create")}
              >
                ＋ 创建虚拟机
              </button>
            ) : null}
          </PageHeader>
          <div className="filter-bar">
            <label>
              搜索名称
              <input
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value);
                  setPage(1);
                }}
                placeholder="名称或 UUID"
              />
            </label>
            <label>
              运行状态
              <select
                value={status}
                onChange={(e) => {
                  setStatus(e.target.value);
                  setPage(1);
                }}
              >
                <option value="">全部状态</option>
                {["RUNNING", "SHUTOFF", "PAUSED", "CRASHED", "UNKNOWN"].map(
                  (s) => (
                    <option key={s}>{s}</option>
                  ),
                )}
              </select>
            </label>
            <label>
              节点 ID
              <input
                value={node}
                onChange={(e) => {
                  setNode(e.target.value);
                  setPage(1);
                }}
                placeholder="全部节点"
                inputMode="numeric"
              />
            </label>
            <button
              className="action"
              onClick={() => {
                setSearch("");
                setStatus("");
                setNode("");
                setPage(1);
              }}
            >
              重置
            </button>
          </div>
          <Card title={`虚拟机列表 · ${total} 台`}>
            {loading ? <p role="status">正在读取虚拟机…</p> : null}
            <div className="table-scroll">
              <table className="vm-table">
                <thead>
                  <tr>
                    <th>名称</th>
                    <th>状态</th>
                    <th>节点</th>
                    <th>vCPU</th>
                    <th>内存</th>
                    <th>IP 地址</th>
                    <th>创建时间</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((vm) => (
                    <tr key={vm.id}>
                      <td>
                        <button
                          className="text-link"
                          onClick={() => {
                            setConsoleOpen(false);
                            navigate(prefix + "/vms/" + vm.id);
                          }}
                        >
                          {vm.name}
                        </button>
                        <div className="mono muted">{vm.uuid.slice(0, 8)}</div>
                      </td>
                      <td>
                        <StatusBadge
                          status={
                            ACTIVE.includes(vm.operation_status)
                              ? vm.operation_status
                              : vm.observed_state
                          }
                        />
                        {vm.observed_state_is_stale ? (
                          <small className="stale-label">数据已过期</small>
                        ) : null}
                      </td>
                      <td>{vm.node_name}</td>
                      <td>{vm.vcpu} 核</td>
                      <td>{vm.memory_mib / 1024} GB</td>
                      <td title="IP 地址尚未缓存">—</td>
                      <td>{formatTime(vm.created_at)}</td>
                      <td>{actions(vm)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {!loading && !items.length ? (
              <p className="empty">暂无符合条件的虚拟机</p>
            ) : null}
            <footer className="pagination">
              <span>共 {total} 台 · 每页 20 台</span>
              <button
                className="action"
                disabled={page <= 1}
                onClick={() => setPage(page - 1)}
              >
                上一页
              </button>
              <span>
                {page} / {Math.max(1, Math.ceil(total / 20))}
              </span>
              <button
                className="action"
                disabled={page * 20 >= total}
                onClick={() => setPage(page + 1)}
              >
                下一页
              </button>
            </footer>
          </Card>
        </>
      )}
      {pending ? (
        <ConfirmOperationModal
          target={pending.vm.name}
          operation={
            (
              {
                start: "启动",
                shutdown: "正常关机",
                reboot: "重启",
                "force-stop": "强制关机",
                delete: "删除实例",
              } as Record<string, string>
            )[pending.action]
          }
          description={
            pending.action === "force-stop"
              ? "此操作等同断电，未保存的数据可能丢失。"
              : pending.action === "delete"
                ? "通过后端任务删除 libvirt 实例并保留磁盘文件，可在数据卷中核对。"
                : "操作将提交为异步任务，最终状态以节点观测结果为准。"
          }
          busy={busy}
          error={error}
          onCancel={() => {
            setPending(null);
            setError(null);
          }}
          onConfirm={() => void execute()}
        />
      ) : null}
      {taskId ? (
        <TaskProgressDrawer id={taskId} onClose={() => setTaskId(null)} />
      ) : null}
    </>
  );
}
