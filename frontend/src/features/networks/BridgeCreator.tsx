import { newRequestId } from "../../utils/requestId";
import { useEffect, useRef, useState } from "react";
import { api, fetchAllOptions } from "../../api";
import { Drawer } from "../../components/ConsoleUI";
import { ErrorBanner, describeError } from "../../components/ui";
import type { Node } from "../../types";
type Port = {
  name: string;
  mac: string;
  state: string;
  eligible: boolean;
  reason: string;
};
export function BridgeCreator({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (id: string) => void;
}) {
  const [nodes, setNodes] = useState<Node[]>([]),
    [node, setNode] = useState(""),
    [ports, setPorts] = useState<Port[]>([]),
    [types, setTypes] = useState<string[]>([]);
  const [name, setName] = useState(""),
    [bridge, setBridge] = useState(""),
    [uplink, setUplink] = useState(""),
    [kind, setKind] = useState("BRIDGE");
  const [loading, setLoading] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<string | null>(null),
    [confirmed, setConfirmed] = useState(false),
    [refresh, setRefresh] = useState(0);
  const pending = useRef(false),
    key = useRef(newRequestId()),
    last = useRef("");
  useEffect(() => {
    let alive = true;
    fetchAllOptions<Node>("/nodes")
      .then((v) => {
        if (alive) setNodes(v.filter((n) => n.is_schedulable));
      })
      .catch((e) => {
        if (alive) setError(describeError(e));
      });
    return () => {
      alive = false;
    };
  }, []);
  useEffect(() => {
    let alive = true;
    setPorts([]);
    setTypes([]);
    setUplink("");
    setConfirmed(false);
    if (!node) return;
    setLoading(true);
    setError(null);
    api
      .request<{ interfaces: Port[]; bridge_types: string[] }>(
        `/networks/nodes/${node}/physical-interfaces`,
      )
      .then((v) => {
        if (alive) {
          setPorts(v.interfaces);
          setTypes(v.bridge_types || ["BRIDGE"]);
        }
      })
      .catch((e) => {
        if (alive) setError(describeError(e));
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [node, refresh]);
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (pending.current || !confirmed) return;
    const data = {
      name,
      node: Number(node),
      type: kind,
      bridge,
      uplink,
      description: "",
    };
    const encoded = JSON.stringify(data);
    if (last.current && last.current !== encoded) key.current = newRequestId();
    last.current = encoded;
    pending.current = true;
    setBusy(true);
    setError(null);
    try {
      const result = await api.request<{ task_id: string }>(
        "/networks/bridges",
        {
          method: "POST",
          headers: { "Idempotency-Key": key.current },
          body: encoded,
        },
      );
      onCreated(result.task_id);
    } catch (e) {
      setError(
        describeError(e) +
          "。请求结果不确定时请先核对任务；相同配置重试会复用幂等键。",
      );
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }
  return (
    <Drawer
      wide
      title="创建桥接网络"
      onClose={() => {
        if (!busy) onClose();
      }}
      footer={
        <>
          <button className="action" disabled={busy} onClick={onClose}>
            取消
          </button>
          <button
            className="action primary"
            type="submit"
            form="bridge-create"
            disabled={
              busy ||
              loading ||
              !confirmed ||
              !ports.some((p) => p.name === uplink && p.eligible) ||
              !types.includes(kind)
            }
          >
            {busy ? "正在提交…" : "提交创建任务"}
          </button>
        </>
      }
    >
      <div className="deployment-flow">
        <span>
          <b>01</b>目标节点
        </span>
        <i />
        <span>
          <b>02</b>物理网卡与网桥
        </span>
        <i />
        <span>
          <b>03</b>确认并异步创建
        </span>
      </div>
      <ErrorBanner message={error} />
      <form id="bridge-create" onSubmit={submit}>
        <fieldset disabled={busy} style={{ border: 0, padding: 0, margin: 0 }}>
          <div className="wizard-fields">
            <label>
              网络名称
              <input
                required
                value={name}
                onChange={(e) => {
                  setName(e.target.value);
                  setConfirmed(false);
                }}
                pattern="[A-Za-z0-9][A-Za-z0-9_-]{1,63}"
                placeholder="production-lan"
              />
            </label>
            <label>
              目标节点
              <select
                required
                value={node}
                onChange={(e) => setNode(e.target.value)}
              >
                <option value="">选择在线节点</option>
                {nodes.map((n) => (
                  <option value={n.id} key={n.id}>
                    {n.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              网桥类型
              <select
                value={kind}
                onChange={(e) => {
                  setKind(e.target.value);
                  setConfirmed(false);
                }}
              >
                <option value="BRIDGE" disabled={!types.includes("BRIDGE")}>
                  Linux Bridge
                </option>
                <option value="OVS" disabled={!types.includes("OVS")}>
                  Open vSwitch Bridge
                </option>
              </select>
            </label>
            <label>
              网桥设备名
              <input
                required
                value={bridge}
                pattern="[A-Za-z][A-Za-z0-9_-]{0,14}"
                maxLength={15}
                placeholder="br-data"
                onChange={(e) => {
                  setBridge(e.target.value);
                  setConfirmed(false);
                }}
              />
            </label>
            <label className="field-wide">
              桥接物理网卡
              <select
                required
                value={uplink}
                disabled={loading || !node}
                onChange={(e) => {
                  setUplink(e.target.value);
                  setConfirmed(false);
                }}
              >
                <option value="">
                  {loading ? "正在读取节点接口…" : "选择未占用的物理网卡"}
                </option>
                {ports.map((p) => (
                  <option value={p.name} disabled={!p.eligible} key={p.name}>
                    {p.name} · {p.mac}
                    {p.eligible ? " · 可用" : ` · 禁止：${p.reason}`}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <button
            type="button"
            className="action sm"
            disabled={!node || loading}
            onClick={() => setRefresh((v) => v + 1)}
          >
            重新检测接口
          </button>
          {node && !loading && ports.length === 0 && (
            <p className="muted">
              未发现可枚举的物理接口。请检查节点网络服务与硬件配置。
            </p>
          )}
          {ports.length > 0 && (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>物理接口</th>
                    <th>链路</th>
                    <th>创建资格</th>
                  </tr>
                </thead>
                <tbody>
                  {ports.map((p) => (
                    <tr key={p.name}>
                      <td>
                        {p.name}
                        <small className="muted"> · {p.mac}</small>
                      </td>
                      <td>{p.state}</td>
                      <td>{p.eligible ? "可桥接" : p.reason}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="callout callout-muted">
            带 IP
            地址、承载路由、已加入网桥或聚合的接口均不可选择。节点执行时会再次校验。创建不会迁移管理地址、修改默认路由或启用
            DHCP /
            NAT；物理网络负责地址分配。配置持久保存，并由网络服务在重启后恢复。
          </div>
          <label className="check">
            <input
              type="checkbox"
              checked={confirmed}
              required
              onChange={(e) => setConfirmed(e.target.checked)}
            />
            确认将节点 {nodes.find((n) => String(n.id) === node)?.name || "—"}{" "}
            的物理网卡 {uplink || "—"} 加入 {kind === "OVS" ? "OVS" : "Linux"}{" "}
            网桥 {bridge || "—"}。
          </label>
        </fieldset>
      </form>
    </Drawer>
  );
}
