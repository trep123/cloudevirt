import { useEffect, useState } from "react";
import { api } from "../../api";
import {
  PageHeader,
  Drawer,
  ConfirmOperationModal,
} from "../../components/ConsoleUI";
import {
  ErrorBanner,
  describeError,
  StatusBadge,
  formatTime,
} from "../../components/ui";
import { navigate } from "../../app/router";
import type { Node, Instance } from "../../types";
import { infra, allResources, type Cluster, type Pool } from "./client";

type Form = {
  id?: number;
  name: string;
  description: string;
  cluster_id: number;
  vcpu_limit: number;
  memory_mib_limit: number;
  disk_gib_limit: number;
  node_ids: number[];
  instance_ids: number[];
};
export function OrganizationPage({ kind }: { kind: "clusters" | "pools" }) {
  const [clusters, setClusters] = useState<Cluster[]>([]),
    [pools, setPools] = useState<Pool[]>([]);
  const [nodes, setNodes] = useState<Node[]>([]),
    [vms, setVms] = useState<Instance[]>([]);
  const [loading, setLoading] = useState(true),
    [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState<Form | null>(null),
    [busy, setBusy] = useState(false);
  const [remove, setRemove] = useState<Cluster | Pool | null>(null),
    [refresh, setRefresh] = useState(0);
  const title = kind === "clusters" ? "集群" : "资源池";
  const endpoint =
    "/admin/" + (kind === "clusters" ? "clusters" : "resource-pools") + "/";
  useEffect(() => {
    let live = true;
    setLoading(true);
    setError(null);
    Promise.all([
      infra.clusters(),
      infra.pools(),
      allResources<Node>("/nodes"),
      allResources<Instance>("/instances"),
    ])
      .then(([c, p, n, v]) => {
        if (live) {
          setClusters(c.results);
          setPools(p.results);
          setNodes(n);
          setVms(v);
        }
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
  }, [refresh, kind]);
  function edit(row?: Cluster | Pool) {
    setError(null);
    setForm({
      name: row?.name || "",
      description: row?.description || "",
      id: row?.id,
      cluster_id:
        row && "cluster_id" in row ? row.cluster_id : clusters[0]?.id || 0,
      vcpu_limit: row && "vcpu_limit" in row ? row.vcpu_limit : 32,
      memory_mib_limit:
        row && "memory_mib_limit" in row ? row.memory_mib_limit : 65536,
      disk_gib_limit:
        row && "disk_gib_limit" in row ? row.disk_gib_limit : 1024,
      node_ids: row && "node_ids" in row ? row.node_ids : [],
      instance_ids: row && "instance_ids" in row ? row.instance_ids : [],
    });
  }
  async function save() {
    if (!form) return;
    setBusy(true);
    setError(null);
    try {
      const body =
        kind === "clusters"
          ? {
              name: form.name,
              description: form.description,
              node_ids: form.node_ids,
            }
          : {
              name: form.name,
              description: form.description,
              cluster_id: form.cluster_id,
              vcpu_limit: form.vcpu_limit,
              memory_mib_limit: form.memory_mib_limit,
              disk_gib_limit: form.disk_gib_limit,
              instance_ids: form.instance_ids,
            };
      await infra.save(endpoint + (form.id ? form.id + "/" : ""), body);
      setForm(null);
      setRefresh((x) => x + 1);
    } catch (e) {
      setError(describeError(e));
    } finally {
      setBusy(false);
    }
  }
  const rows = kind === "clusters" ? clusters : pools;
  const selectedCluster = clusters.find((c) => c.id === form?.cluster_id);
  const candidates =
    kind === "clusters"
      ? nodes.map((n) => ({
          id: n.id,
          name: n.name,
          occupied: clusters.some(
            (c) => c.id !== form?.id && c.node_ids.includes(n.id),
          ),
        }))
      : vms
          .filter((vm) => selectedCluster?.node_ids.includes(vm.node))
          .map((vm) => ({
            id: vm.id,
            name: vm.name,
            occupied: pools.some(
              (p) => p.id !== form?.id && p.instance_ids.includes(vm.id),
            ),
          }));
  return (
    <>
      <PageHeader
        title={title + "管理"}
        description={
          kind === "clusters"
            ? "组织物理节点、查看实际健康状态与资源分配；不包含自动迁移或高可用调度"
            : "在集群范围内分组虚拟机，并校验已分配 vCPU、内存和磁盘的容量上限"
        }
      >
        <button
          className="action"
          disabled={loading || busy}
          onClick={() => setRefresh((x) => x + 1)}
        >
          刷新
        </button>
        <button
          className="action primary"
          disabled={loading || (kind === "pools" && !clusters.length)}
          onClick={() => edit()}
        >
          创建{title}
        </button>
      </PageHeader>
      <ErrorBanner message={error} />
      {kind === "pools" && !clusters.length && !loading ? (
        <p className="banner banner-info">请先创建集群并分配节点。</p>
      ) : null}
      <section className="card table-wrap">
        {loading ? (
          <p role="status">正在加载{title}…</p>
        ) : (
          <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>名称</th>
                <th>
                  {kind === "clusters" ? "节点 / 虚拟机" : "所属集群 / 虚拟机"}
                </th>
                <th>vCPU</th>
                <th>内存</th>
                <th>磁盘</th>
                <th className="col-actions">操作</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id}>
                  <td>
                    <strong>{row.name}</strong>
                    <p className="muted">{row.description || "—"}</p>
                  </td>
                  <td>
                    {"nodes" in row ? (
                      <>
                        {row.nodes.map((n) => (
                          <div key={n.id}>
                            <button
                              className="action"
                              onClick={() => navigate(`/admin/nodes/${n.id}`)}
                            >
                              {n.name}
                            </button>
                            <StatusBadge status={n.status} />{" "}
                            {n.resource_is_stale ? (
                              <small>
                                数据过期 · {formatTime(n.last_seen_at)}
                              </small>
                            ) : null}
                          </div>
                        ))}
                        <small>
                          {row.nodes.length} 个节点 · {row.instances} 台虚拟机
                        </small>
                      </>
                    ) : (
                      <>
                        {row.cluster_name} · {row.instance_ids.length} 台
                      </>
                    )}
                  </td>
                  <td>
                    {row.usage.vcpu}
                    {"vcpu_limit" in row ? ` / ${row.vcpu_limit}` : " 核"}
                  </td>
                  <td>
                    {(row.usage.memory_mib / 1024).toFixed(1)}
                    {"memory_mib_limit" in row
                      ? ` / ${(row.memory_mib_limit / 1024).toFixed(1)}`
                      : ""}{" "}
                    GB
                  </td>
                  <td>
                    {row.usage.disk_gib}
                    {"disk_gib_limit" in row
                      ? ` / ${row.disk_gib_limit}`
                      : ""}{" "}
                    GB
                  </td>
                  <td className="actions">
                    <button className="action" onClick={() => edit(row)}>
                      编辑 / 分配
                    </button>
                    <button
                      className="action danger"
                      onClick={() => {
                        setError(null);
                        setRemove(row);
                      }}
                    >
                      删除
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        )}
        {!loading && !rows.length ? (
          <p className="empty">
            暂无{title}，可通过“创建{title}”添加。
          </p>
        ) : null}
      </section>
      {form ? (
        <Drawer
          title={(form.id ? "编辑" : "创建") + title}
          onClose={() => {
            if (!busy) setForm(null);
          }}
          footer={
            <>
              <button
                className="action"
                type="button"
                disabled={busy}
                onClick={() => setForm(null)}
              >
                取消
              </button>
              <button
                className="action primary"
                type="submit"
                form="organization-form"
                disabled={busy}
              >
                {busy ? "保存中…" : "保存配置"}
              </button>
            </>
          }
        >
          <form
            id="organization-form"
            className="infra-form"
            onSubmit={(e) => {
              e.preventDefault();
              void save();
            }}
          >
            <ErrorBanner message={error} />
            <label>
              名称
              <input
                required
                maxLength={64}
                pattern="[\w\- .\u4e00-\u9fff]+"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
              />
            </label>
            <label>
              说明
              <textarea
                maxLength={2000}
                value={form.description}
                onChange={(e) =>
                  setForm({ ...form, description: e.target.value })
                }
              />
            </label>
            {kind === "pools" ? (
              <>
                <label>
                  所属集群
                  <select
                    required
                    value={form.cluster_id}
                    onChange={(e) =>
                      setForm({
                        ...form,
                        cluster_id: Number(e.target.value),
                        instance_ids: [],
                      })
                    }
                  >
                    {clusters.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name}
                      </option>
                    ))}
                  </select>
                </label>
                {(
                  [
                    ["vcpu_limit", "vCPU 上限（核）"],
                    ["memory_mib_limit", "内存上限（MiB）"],
                    ["disk_gib_limit", "磁盘上限（GiB）"],
                  ] as const
                ).map(([key, label]) => (
                  <label key={key}>
                    {label}
                    <input
                      type="number"
                      min={1}
                      max={2147483647}
                      required
                      value={form[key]}
                      onChange={(e) =>
                        setForm({ ...form, [key]: Number(e.target.value) })
                      }
                    />
                  </label>
                ))}
                <p className="muted">
                  限额约束本池已分配虚拟机的配置总量；分组不会更改资源所有权或授予访问权限。
                </p>
              </>
            ) : null}
            <fieldset>
              <legend>{kind === "clusters" ? "成员节点" : "成员虚拟机"}</legend>
              {!candidates.length ? (
                <p>当前没有可分配成员。</p>
              ) : (
                candidates.map((item) => {
                  const key = kind === "clusters" ? "node_ids" : "instance_ids";
                  return (
                    <label className="infra-choice" key={item.id}>
                      <input
                        type="checkbox"
                        disabled={item.occupied || busy}
                        checked={form[key].includes(item.id)}
                        onChange={(e) =>
                          setForm({
                            ...form,
                            [key]: e.target.checked
                              ? [...form[key], item.id]
                              : form[key].filter((id) => id !== item.id),
                          })
                        }
                      />
                      {item.name}
                      {item.occupied ? "（已分配到其他分组）" : ""}
                    </label>
                  );
                })
              )}
            </fieldset>
          </form>
        </Drawer>
      ) : null}
      {remove ? (
        <ConfirmOperationModal
          target={remove.name}
          operation={"删除" + title}
          description="仅允许删除空分组。关联节点、虚拟机或资源池必须先移出，系统不会级联删除实际资源。"
          busy={busy}
          error={error}
          onCancel={() => setRemove(null)}
          onConfirm={() => {
            setBusy(true);
            setError(null);
            api
              .request(endpoint + remove.id + "/", { method: "DELETE" })
              .then(() => {
                setRemove(null);
                setRefresh((x) => x + 1);
              })
              .catch((e) => setError(describeError(e)))
              .finally(() => setBusy(false));
          }}
        />
      ) : null}
    </>
  );
}
