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
  DescList,
  EmptyState,
  ErrorBanner,
  LoadingState,
  Pagination,
  SearchInput,
  Segmented,
  StatusBadge,
  Tabs,
  Toolbar,
  describeError,
  formatTime,
  formatTimeFixed,
  RowMenu,
} from "../../components/ui";
import { Icon } from "../../components/icons";
const VncConsole = lazy(() =>
  import("../../components/VncConsole").then((module) => ({
    default: module.VncConsole,
  })),
);
import { VmWizard } from "./VmWizard";
import { DisplayPanel } from "./DisplayPanel";
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
      <div className="row-actions">
        <button
          className="action sm"
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
            className="action sm"
            disabled={active || busy}
            onClick={() => setPending({ vm, action: "start" })}
          >
            启动
          </button>
        ) : null}
        {running && can("instances.shutdown_instance") ? (
          <button
            className="action sm"
            disabled={active || busy}
            onClick={() => setPending({ vm, action: "shutdown" })}
          >
            正常关机
          </button>
        ) : null}
        <RowMenu>
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
          <button onClick={() => navigate(prefix + "/tasks")}>查看任务</button>
        </RowMenu>
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
        isAdmin={user.console_scope === "admin"}
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
  const memGb = (mib: number) =>
    mib % 1024 === 0 ? `${mib / 1024} GB` : `${(mib / 1024).toFixed(1)} GB`;
  const STATUS_FILTERS = [
    { value: "", label: "全部" },
    { value: "RUNNING", label: "运行中" },
    { value: "SHUTOFF", label: "已关闭" },
    { value: "PAUSED", label: "已暂停" },
    { value: "CRASHED", label: "异常" },
  ];
  return (
    <>
      {id ? (
        <>
          <PageHeader
            back={{
              label: "虚拟机列表",
              onClick: () => navigate(prefix + "/vms"),
            }}
            title={detail?.name || "虚拟机详情"}
            meta={
              detail ? (
                <StatusBadge
                  status={
                    ACTIVE.includes(detail.operation_status)
                      ? detail.operation_status
                      : detail.observed_state
                  }
                />
              ) : null
            }
            description={
              detail ? (
                <>
                  <span className="mono">{detail.uuid}</span> · 所属节点{" "}
                  {detail.node_name}
                </>
              ) : (
                "正在读取资源"
              )
            }
          >
            {detail ? (
              <button className="action" onClick={() => setConsoleOpen(true)}>
                <Icon name="console" size={15} />
                远程控制台
              </button>
            ) : null}
            {detail ? actions(detail) : null}
          </PageHeader>
          <ErrorBanner message={error} />
          {detail && !loading ? (
            <>
              <div className="summary-strip">
                {[
                  ["cpu", "vCPU", `${detail.vcpu} 核`],
                  ["memory", "内存", memGb(detail.memory_mib)],
                  ["disk", "系统盘", `${detail.disk_gib} GB`],
                  ["server", "节点", detail.node_name],
                  ["image", "镜像", detail.image_name],
                ].map(([icon, label, value]) => (
                  <div className="summary-item" key={label}>
                    <Icon name={icon} size={18} />
                    <div>
                      <span>{label}</span>
                      <strong title={value}>{value}</strong>
                    </div>
                  </div>
                ))}
              </div>
              {detail.observed_state_is_stale ? (
                <div className="banner banner-info">
                  观测数据已过期 · 最后更新{" "}
                  {formatTime(detail.observed_state_updated_at)}
                </div>
              ) : null}
              <Tabs
                label="虚拟机详情"
                tabs={TABS.filter((t) => admin || t !== "权限")}
                value={tab}
                onChange={setTab}
              />
              <Card title={tab} flush={tab === "磁盘"}>
                {tab === "概览" ? (
                  <>
                    <DescList
                      columns={3}
                      items={[
                        ["名称", detail.name],
                        ["UUID", <span className="mono">{detail.uuid}</span>],
                        [
                          "Libvirt 域名",
                          <span className="mono">
                            {detail.libvirt_domain_name}
                          </span>,
                        ],
                        ["所属节点", detail.node_name],
                        ["镜像", detail.image_name],
                        ["网络", detail.network_name || "未接入"],
                        [
                          "期望状态",
                          <StatusBadge status={detail.desired_state} />,
                        ],
                        [
                          "观测状态",
                          <StatusBadge status={detail.observed_state} />,
                        ],
                        ["开机自启", detail.autostart ? "是" : "否"],
                        [
                          "最近观测",
                          formatTime(detail.observed_state_updated_at),
                        ],
                        ["创建时间", formatTime(detail.created_at)],
                        ["更新时间", formatTime(detail.updated_at)],
                      ]}
                    />
                    {detail.last_error_message ? (
                      <p role="alert" className="inline-alert">
                        <Icon name="alert" size={15} />
                        {detail.last_error_code}：{detail.last_error_message}
                      </p>
                    ) : null}
                  </>
                ) : tab === "硬件" ? (
                  <>
                    <DescList
                      columns={2}
                      items={[
                        ["处理器", `${detail.vcpu} 核`],
                        ["内存", memGb(detail.memory_mib)],
                        ["系统盘", `${detail.disk_gib} GB · qcow2`],
                      ]}
                    />
                    <DisplayPanel
                      id={detail.id}
                      admin={admin}
                      stopped={
                        detail.observed_state === "SHUTOFF" &&
                        !detail.observed_state_is_stale
                      }
                    />
                  </>
                ) : tab === "磁盘" ? (
                  detail.disks.length ? (
                    <div className="table-scroll">
                      <table className="data-table">
                        <thead>
                          <tr>
                            <th>名称</th>
                            <th>角色</th>
                            <th className="num">容量</th>
                            <th>状态</th>
                            <th>设备</th>
                          </tr>
                        </thead>
                        <tbody>
                          {detail.disks.map((d) => (
                            <tr key={d.id}>
                              <td className="strong">{d.name}</td>
                              <td className="muted">{d.role}</td>
                              <td className="num">{d.size_gib} GB</td>
                              <td>
                                <StatusBadge status={d.status} />
                              </td>
                              <td className="mono">{d.target_dev}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <EmptyState title="暂无磁盘" icon="disk" />
                  )
                ) : tab === "网络" ? (
                  <DescList
                    columns={2}
                    items={[
                      ["已登记网络", detail.network_name || "未接入"],
                      ["说明", "实际网卡连接可在网络拓扑中查看。"],
                    ]}
                  />
                ) : tab === "快照" ? (
                  <SnapshotsPage
                    admin={user.console_scope === "admin"}
                    instance={detail}
                  />
                ) : tab === "任务日志" ? (
                  <EmptyState
                    icon="task"
                    title="任务日志在任务中心统一查看"
                    description="包含该虚拟机的创建、启停、删除等异步任务及事件。"
                    action={
                      <button
                        className="action"
                        onClick={() => navigate(prefix + "/tasks")}
                      >
                        打开授权任务中心
                      </button>
                    }
                  />
                ) : (
                  <EmptyState
                    icon={tab === "监控" ? "trend" : "info"}
                    title={`暂无${tab}数据`}
                    description="当前后端尚未提供此能力。"
                  />
                )}
              </Card>
              {consoleOpen ? (
                <Card
                  title="远程控制台"
                  extra={
                    <button
                      className="action sm"
                      onClick={() => setConsoleOpen(false)}
                    >
                      关闭控制台
                    </button>
                  }
                >
                  <Suspense
                    fallback={<LoadingState text="正在加载远程控制台…" />}
                  >
                    <VncConsole
                      instanceId={detail.id}
                      desktopAvailable={detail.observed_state === "RUNNING"}
                    />
                  </Suspense>
                </Card>
              ) : null}
            </>
          ) : (
            <div className="card">
              {loading ? (
                <LoadingState text="正在读取虚拟机…" />
              ) : (
                <EmptyState
                  title={error ? "无法读取该资源" : "资源不存在或无权访问"}
                />
              )}
            </div>
          )}
        </>
      ) : (
        <>
          <PageHeader
            title={admin ? "虚拟机" : "我的虚拟机"}
            description="管理授权范围内的实例，资源状态以服务端观测结果为准"
          >
            <button className="action" onClick={() => setRefresh((v) => v + 1)}>
              <Icon name="refresh" size={15} />
              刷新
            </button>
            {can("instances.add_instance") ? (
              <button
                className="action primary"
                onClick={() => navigate(prefix + "/vms/create")}
              >
                <Icon name="plus" size={15} />
                创建虚拟机
              </button>
            ) : null}
          </PageHeader>
          <ErrorBanner message={error} />
          <Toolbar
            extra={
              search || status || node ? (
                <button
                  className="action ghost"
                  onClick={() => {
                    setSearch("");
                    setStatus("");
                    setNode("");
                    setPage(1);
                  }}
                >
                  重置
                </button>
              ) : null
            }
          >
            <SearchInput
              label="搜索名称"
              value={search}
              onChange={(v) => {
                setSearch(v);
                setPage(1);
              }}
              placeholder="名称或 UUID"
              width={260}
            />
            <Segmented
              label="运行状态"
              value={status}
              options={STATUS_FILTERS}
              onChange={(v) => {
                setStatus(v);
                setPage(1);
              }}
            />
            <input
              aria-label="节点 ID"
              className="input-narrow"
              value={node}
              onChange={(e) => {
                setNode(e.target.value);
                setPage(1);
              }}
              placeholder="节点 ID（全部）"
              inputMode="numeric"
            />
          </Toolbar>
          <Card
            flush
            title="虚拟机列表"
            description={`共 ${total} 台实例`}
            footer={
              <Pagination
                page={page}
                pageSize={20}
                total={total}
                unit="台"
                onChange={setPage}
              />
            }
          >
            <div className="table-scroll table-scroll-menus">
              <table className="data-table vm-table">
                <thead>
                  <tr>
                    <th>名称</th>
                    <th>状态</th>
                    <th>节点</th>
                    <th>规格</th>
                    <th className="col-image">镜像</th>
                    <th>IP 地址</th>
                    <th>创建时间</th>
                    <th className="col-actions">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((vm) => (
                    <tr key={vm.id}>
                      <td>
                        <div className="cell-stack">
                          <button
                            className="text-link"
                            onClick={() => {
                              setConsoleOpen(false);
                              navigate(prefix + "/vms/" + vm.id);
                            }}
                          >
                            {vm.name}
                          </button>
                          <small className="mono muted">
                            {vm.uuid.slice(0, 8)}
                          </small>
                        </div>
                      </td>
                      <td>
                        <div className="cell-stack">
                          <span>
                            <StatusBadge
                              status={
                                ACTIVE.includes(vm.operation_status)
                                  ? vm.operation_status
                                  : vm.observed_state
                              }
                            />
                          </span>
                          {vm.observed_state_is_stale ? (
                            <small className="stale-label">数据已过期</small>
                          ) : null}
                        </div>
                      </td>
                      <td>{vm.node_name}</td>
                      <td className="spec-text">
                        {vm.vcpu} vCPU · {memGb(vm.memory_mib)}
                      </td>
                      <td className="col-image">
                        <span className="truncate muted" title={vm.image_name}>
                          {vm.image_name}
                        </span>
                      </td>
                      <td className="muted" title="IP 地址尚未缓存">
                        —
                      </td>
                      <td>
                        <span className="mono time-text">
                          {formatTimeFixed(vm.created_at)}
                        </span>
                      </td>
                      <td className="col-actions">{actions(vm)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {loading && !items.length ? (
              <LoadingState text="正在读取虚拟机…" />
            ) : null}
            {!loading && !items.length ? (
              <EmptyState
                icon="vm"
                title="暂无符合条件的虚拟机"
                description="调整筛选条件，或创建一台新的虚拟机。"
              />
            ) : null}
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
