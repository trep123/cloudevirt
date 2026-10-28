import { useEffect, useState } from "react";
import { api } from "../../api";
import {
  PageHeader,
  ConfirmOperationModal,
  TaskProgressDrawer,
} from "../../components/ConsoleUI";
import { ErrorBanner, describeError } from "../../components/ui";
import type { Instance } from "../../types";
import { infra, allResources } from "./client";

type Snapshot = {
  name: string;
  state: string;
  created_at: number;
  parent: string;
  supported: boolean;
};
type SnapshotData = {
  results: Snapshot[];
  sampled_at: string;
  allow_destructive: boolean;
};
type Operation = {
  action: "create" | "revert" | "delete";
  name: string;
  key: string;
};
export function SnapshotsPage({
  admin,
  instance,
}: {
  admin: boolean;
  instance?: Instance;
}) {
  const [vms, setVms] = useState<Instance[]>(instance ? [instance] : []),
    [selected, setSelected] = useState(instance?.id || 0);
  const [data, setData] = useState<SnapshotData | null>(null),
    [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true),
    [busy, setBusy] = useState(false),
    [refresh, setRefresh] = useState(0);
  const [operation, setOperation] = useState<Operation | null>(null),
    [task, setTask] = useState<string | null>(null);
  useEffect(() => {
    if (instance) {
      setVms([instance]);
      setSelected(instance.id);
      return;
    }
    let live = true;
    allResources<Instance>("/instances")
      .then((v) => {
        if (live) {
          setVms(v);
          setSelected(v[0]?.id || 0);
          if (!v.length) setLoading(false);
        }
      })
      .catch((e) => {
        if (live) {
          setError(describeError(e));
          setLoading(false);
        }
      });
    return () => {
      live = false;
    };
  }, [instance?.id]);
  useEffect(() => {
    if (!selected) return;
    let live = true;
    setLoading(true);
    setData(null);
    setError(null);
    api
      .request<SnapshotData>(`/snapshots/instances/${selected}/`)
      .then((d) => {
        if (live) setData(d);
      })
      .catch((e) => {
        if (live) setError(describeError(e));
      })
      .finally(() => {
        if (live) setLoading(false);
      });
    return () => {
      live = false;
    };
  }, [selected, refresh]);
  const vm = instance || vms.find((v) => v.id === selected);
  const canWrite =
    admin &&
    vm?.observed_state === "SHUTOFF" &&
    !vm.observed_state_is_stale &&
    !busy &&
    !!data;
  const names = { create: "创建快照", revert: "恢复快照", delete: "删除快照" };
  function choose(action: Operation["action"], name: string) {
    setError(null);
    setOperation({ action, name, key: crypto.randomUUID() });
  }
  return (
    <>
      <PageHeader
        title="虚拟机快照"
        description="关机状态下的 qcow2 内部快照；快照与原磁盘位于同一存储，不作为独立备份"
      >
        {!instance ? (
          <select
            aria-label="选择虚拟机"
            value={selected}
            disabled={busy}
            onChange={(e) => setSelected(Number(e.target.value))}
          >
            {vms.map((v) => (
              <option key={v.id} value={v.id}>
                {v.name}
              </option>
            ))}
          </select>
        ) : null}
        <button
          className="action"
          disabled={!selected || loading}
          onClick={() => setRefresh((x) => x + 1)}
        >
          刷新快照
        </button>
        {admin ? (
          <button
            className="action primary"
            disabled={!canWrite}
            title="必须正常关机并等待状态同步"
            onClick={() =>
              choose("create", "cv-" + crypto.randomUUID().replaceAll("-", ""))
            }
          >
            创建快照
          </button>
        ) : null}
      </PageHeader>
      <ErrorBanner message={error} />
      <p className="banner banner-info">
        {admin
          ? "请先正常关闭虚拟机。恢复和删除需节点开启破坏性操作；恢复会丢失快照之后的磁盘变更。"
          : "可查看自己虚拟机的快照；创建、恢复与删除由管理员执行。"}
      </p>
      <section className="card table-wrap">
        {loading ? (
          <p role="status">正在查询真实快照…</p>
        ) : !selected ? (
          <p className="empty">没有可访问的虚拟机。</p>
        ) : null}
        {data ? (
          <>
            <p className="muted">
              成功采集时间：{new Date(data.sampled_at).toLocaleString()}
            </p>
            <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>名称</th>
                  <th>创建时间</th>
                  <th>父快照</th>
                  <th>类型</th>
                  {admin ? <th className="col-actions">操作</th> : null}
                </tr>
              </thead>
              <tbody>
                {data.results.map((s) => (
                  <tr key={s.name}>
                    <td>{s.name}</td>
                    <td>{new Date(s.created_at * 1000).toLocaleString()}</td>
                    <td>{s.parent || "—"}</td>
                    <td>
                      {s.supported ? "关机内部快照" : "仅查看 · 其他类型"}
                    </td>
                    {admin ? (
                      <td className="actions">
                        <button
                          className="action danger"
                          disabled={
                            !canWrite || !s.supported || !data.allow_destructive
                          }
                          onClick={() => choose("revert", s.name)}
                        >
                          恢复
                        </button>
                        <button
                          className="action danger"
                          disabled={
                            !canWrite ||
                            !s.supported ||
                            !data.allow_destructive ||
                            data.results.some(
                              (child) => child.parent === s.name,
                            )
                          }
                          onClick={() => choose("delete", s.name)}
                        >
                          删除
                        </button>
                      </td>
                    ) : null}
                  </tr>
                ))}
              </tbody>
            </table>
            </div>
            {!data.results.length ? <p className="empty">暂无快照。</p> : null}
          </>
        ) : null}
      </section>
      {operation && vm ? (
        <ConfirmOperationModal
          target={`${vm.name} / ${operation.name}`}
          operation={names[operation.action]}
          busy={busy}
          error={error}
          description={
            operation.action === "revert"
              ? "恢复将覆盖该虚拟机磁盘当前内容，快照之后的变更将丢失。不会自动启动虚拟机。"
              : operation.action === "delete"
                ? "将永久删除此快照的恢复点；不删除虚拟机磁盘。存在子快照时必须先处理子快照。"
                : "为虚拟机创建关机内部快照，实际执行结果请查看异步任务。"
          }
          onCancel={() => setOperation(null)}
          onConfirm={async () => {
            setBusy(true);
            setError(null);
            try {
              const result = await infra.save(
                `/snapshots/instances/${selected}/`,
                { action: operation.action, name: operation.name },
                operation.key,
              );
              setOperation(null);
              setTask(result.task_id);
            } catch (e) {
              setError(describeError(e));
            } finally {
              setBusy(false);
            }
          }}
        />
      ) : null}
      {task ? (
        <TaskProgressDrawer
          id={task}
          onClose={() => {
            setTask(null);
            setRefresh((x) => x + 1);
          }}
        />
      ) : null}
    </>
  );
}
