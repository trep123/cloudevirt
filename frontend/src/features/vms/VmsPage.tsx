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
  "����",
  "���",
  "Ӳ��",
  "����",
  "����",
  "����",
  "������־",
  "Ȩ��",
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
    [tab, setTab] = useState("����"),
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
          title={!running ? "���к�ɴ򿪿���̨" : ""}
          onClick={() => {
            setConsoleOpen(true);
            navigate(prefix + "/vms/" + vm.id);
          }}
        >
          ����̨
        </button>
        {stopped && can("instances.start_instance") ? (
          <button
            className="action sm"
            disabled={active || busy}
            onClick={() => setPending({ vm, action: "start" })}
          >
            ����
          </button>
        ) : null}
        {running && can("instances.shutdown_instance") ? (
          <button
            className="action sm"
            disabled={active || busy}
            onClick={() => setPending({ vm, action: "shutdown" })}
          >
            �����ػ�
          </button>
        ) : null}
        <RowMenu>
          {running && can("instances.reboot_instance") ? (
            <button
              disabled={active || busy}
              onClick={() => setPending({ vm, action: "reboot" })}
            >
              ����
            </button>
          ) : null}
          {running && can("instances.force_stop_instance") ? (
            <button
              className="danger-text"
              disabled={active || busy}
              onClick={() => setPending({ vm, action: "force-stop" })}
            >
              ǿ�ƹػ�
            </button>
          ) : null}
          {stopped && can("instances.delete_instance") ? (
            <button
              className="danger-text"
              disabled={active || busy}
              onClick={() => setPending({ vm, action: "delete" })}
            >
              ɾ�����������̣�
            </button>
          ) : null}
          <button onClick={() => navigate(prefix + "/tasks")}>�鿴����</button>
        </RowMenu>
      </div>
    );
  }
  if (rawId && rawId !== "create" && !/^\d+$/.test(rawId)) {
    return (
      <Card title="404 �� �����������">
        <p>�����Ȩ��Դ�б�ѡ���������</p>
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
      <Card title="��Ȩ����">
        <p>û�д��������Ȩ�ޡ�</p>
      </Card>
    );
  const memGb = (mib: number) =>
    mib % 1024 === 0 ? `${mib / 1024} GB` : `${(mib / 1024).toFixed(1)} GB`;
  const STATUS_FILTERS = [
    { value: "", label: "ȫ��" },
    { value: "RUNNING", label: "������" },
    { value: "SHUTOFF", label: "�ѹر�" },
    { value: "PAUSED", label: "����ͣ" },
    { value: "CRASHED", label: "�쳣" },
  ];
  return (
    <>
      {id ? (
        <>
          <PageHeader
            back={{
              label: "������б�",
              onClick: () => navigate(prefix + "/vms"),
            }}
            title={detail?.name || "���������"}
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
                  <span className="mono">{detail.uuid}</span> �� �����ڵ�{" "}
                  {detail.node_name}
                </>
              ) : (
                "���ڶ�ȡ��Դ"
              )
            }
          >
            {detail ? (
              <button className="action" onClick={() => setConsoleOpen(true)}>
                <Icon name="console" size={15} />
                Զ�̿���̨
              </button>
            ) : null}
            {detail ? actions(detail) : null}
          </PageHeader>
          <ErrorBanner message={error} />
          {detail && !loading ? (
            <>
              <div className="summary-strip">
                {[
                  ["cpu", "vCPU", `${detail.vcpu} ��`],
                  ["memory", "�ڴ�", memGb(detail.memory_mib)],
                  ["disk", "ϵͳ��", `${detail.disk_gib} GB`],
                  ["server", "�ڵ�", detail.node_name],
                  ["image", "����", detail.image_name],
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
                  �۲������ѹ��� �� ������{" "}
                  {formatTime(detail.observed_state_updated_at)}
                </div>
              ) : null}
              <Tabs
                label="���������"
                tabs={TABS.filter((t) => admin || t !== "Ȩ��")}
                value={tab}
                onChange={setTab}
              />
              <Card title={tab} flush={tab === "����"}>
                {tab === "����" ? (
                  <>
                    <DescList
                      columns={3}
                      items={[
                        ["����", detail.name],
                        ["UUID", <span className="mono">{detail.uuid}</span>],
                        [
                          "Libvirt ����",
                          <span className="mono">
                            {detail.libvirt_domain_name}
                          </span>,
                        ],
                        ["�����ڵ�", detail.node_name],
                        ["����", detail.image_name],
                        ["����", detail.network_name || "δ����"],
                        [
                          "����״̬",
                          <StatusBadge status={detail.desired_state} />,
                        ],
                        [
                          "�۲�״̬",
                          <StatusBadge status={detail.observed_state} />,
                        ],
                        ["��������", detail.autostart ? "��" : "��"],
                        [
                          "����۲�",
                          formatTime(detail.observed_state_updated_at),
                        ],
                        ["����ʱ��", formatTime(detail.created_at)],
                        ["����ʱ��", formatTime(detail.updated_at)],
                      ]}
                    />
                    {detail.last_error_message ? (
                      <p role="alert" className="inline-alert">
                        <Icon name="alert" size={15} />
                        {detail.last_error_code}��{detail.last_error_message}
                      </p>
                    ) : null}
                  </>
                ) : tab === "Ӳ��" ? (
                  <>
                    <DescList
                      columns={2}
                      items={[
                        ["������", `${detail.vcpu} ��`],
                        ["�ڴ�", memGb(detail.memory_mib)],
                        ["ϵͳ��", `${detail.disk_gib} GB �� qcow2`],
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
                ) : tab === "����" ? (
                  detail.disks.length ? (
                    <div className="table-scroll">
                      <table className="data-table">
                        <thead>
                          <tr>
                            <th>����</th>
                            <th>��ɫ</th>
                            <th className="num">����</th>
                            <th>״̬</th>
                            <th>�豸</th>
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
                    <EmptyState title="���޴���" icon="disk" />
                  )
                ) : tab === "����" ? (
                  <DescList
                    columns={2}
                    items={[
                      ["�ѵǼ�����", detail.network_name || "δ����"],
                      ["˵��", "ʵ���������ӿ������������в鿴��"],
                    ]}
                  />
                ) : tab === "����" ? (
                  <SnapshotsPage
                    admin={user.console_scope === "admin"}
                    instance={detail}
                  />
                ) : tab === "������־" ? (
                  <EmptyState
                    icon="task"
                    title="������־����������ͳһ�鿴"
                    description="������������Ĵ�������ͣ��ɾ�����첽�����¼���"
                    action={
                      <button
                        className="action"
                        onClick={() => navigate(prefix + "/tasks")}
                      >
                        ����Ȩ��������
                      </button>
                    }
                  />
                ) : (
                  <EmptyState
                    icon={tab === "���" ? "trend" : "info"}
                    title={`����${tab}����`}
                    description="��ǰ�����δ�ṩ��������"
                  />
                )}
              </Card>
              {consoleOpen ? (
                <Card
                  title="Զ�̿���̨"
                  extra={
                    <button
                      className="action sm"
                      onClick={() => setConsoleOpen(false)}
                    >
                      �رտ���̨
                    </button>
                  }
                >
                  <Suspense
                    fallback={<LoadingState text="���ڼ���Զ�̿���̨��" />}
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
                <LoadingState text="���ڶ�ȡ�������" />
              ) : (
                <EmptyState
                  title={error ? "�޷���ȡ����Դ" : "��Դ�����ڻ���Ȩ����"}
                />
              )}
            </div>
          )}
        </>
      ) : (
        <>
          <PageHeader
            title={admin ? "�����" : "�ҵ������"}
            description="������Ȩ��Χ�ڵ�ʵ������Դ״̬�Է���˹۲���Ϊ׼"
          >
            <button className="action" onClick={() => setRefresh((v) => v + 1)}>
              <Icon name="refresh" size={15} />
              ˢ��
            </button>
            {can("instances.add_instance") ? (
              <button
                className="action primary"
                onClick={() => navigate(prefix + "/vms/create")}
              >
                <Icon name="plus" size={15} />
                ���������
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
                  ����
                </button>
              ) : null
            }
          >
            <SearchInput
              label="��������"
              value={search}
              onChange={(v) => {
                setSearch(v);
                setPage(1);
              }}
              placeholder="���ƻ� UUID"
              width={260}
            />
            <Segmented
              label="����״̬"
              value={status}
              options={STATUS_FILTERS}
              onChange={(v) => {
                setStatus(v);
                setPage(1);
              }}
            />
            <input
              aria-label="�ڵ� ID"
              className="input-narrow"
              value={node}
              onChange={(e) => {
                setNode(e.target.value);
                setPage(1);
              }}
              placeholder="�ڵ� ID��ȫ����"
              inputMode="numeric"
            />
          </Toolbar>
          <Card
            flush
            title="������б�"
            description={`�� ${total} ̨ʵ��`}
            footer={
              <Pagination
                page={page}
                pageSize={20}
                total={total}
                unit="̨"
                onChange={setPage}
              />
            }
          >
            <div className="table-scroll table-scroll-menus">
              <table className="data-table vm-table">
                <thead>
                  <tr>
                    <th>����</th>
                    <th>״̬</th>
                    <th>�ڵ�</th>
                    <th>���</th>
                    <th className="col-image">����</th>
                    <th>IP ��ַ</th>
                    <th>����ʱ��</th>
                    <th className="col-actions">����</th>
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
                            <small className="stale-label">�����ѹ���</small>
                          ) : null}
                        </div>
                      </td>
                      <td>{vm.node_name}</td>
                      <td className="spec-text">
                        {vm.vcpu} vCPU �� {memGb(vm.memory_mib)}
                      </td>
                      <td className="col-image">
                        <span className="truncate muted" title={vm.image_name}>
                          {vm.image_name}
                        </span>
                      </td>
                      <td className="muted" title="IP ��ַ��δ����">
                        ��
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
              <LoadingState text="���ڶ�ȡ�������" />
            ) : null}
            {!loading && !items.length ? (
              <EmptyState
                icon="vm"
                title="���޷��������������"
                description="����ɸѡ�������򴴽�һ̨�µ��������"
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
                start: "����",
                shutdown: "�����ػ�",
                reboot: "����",
                "force-stop": "ǿ�ƹػ�",
                delete: "ɾ��ʵ��",
              } as Record<string, string>
            )[pending.action]
          }
          description={
            pending.action === "force-stop"
              ? "�˲�����ͬ�ϵ磬δ��������ݿ��ܶ�ʧ��"
              : pending.action === "delete"
                ? "ͨ���������ɾ�� libvirt ʵ�������������ļ����������ݾ��к˶ԡ�"
                : "�������ύΪ�첽��������״̬�Խڵ�۲���Ϊ׼��"
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
