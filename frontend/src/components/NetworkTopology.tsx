import {
  connectionError,
  type TopologyVM as Instance,
} from "../features/networks/topologyModel";
import { useRef, useState } from "react";
import type { InstanceInterface, Network } from "../types";
import "./network-topology.css";

type Draft = { kind: "vm" | "net"; id: number; x: number; y: number };
const labels: Record<string, string> = {
  LIBVIRT_NETWORK: "Libvirt",
  BRIDGE: "Linux Bridge",
  OVS: "Open vSwitch",
};
export function NetworkTopology({
  networks,
  instances,
  interfaces,
  editable = false,
  onConnect,
}: {
  networks: Network[];
  instances: Instance[];
  interfaces: Record<number, InstanceInterface[]>;
  editable?: boolean;
  onConnect?: (vm: Instance, network: Network) => void;
}) {
  const [search, setSearch] = useState(""),
    [scope, setScope] = useState(""),
    [zoom, setZoom] = useState(1),
    [draft, setDraft] = useState<Draft | null>(null),
    [cursor, setCursor] = useState({ x: 0, y: 0 }),
    [hint, setHint] = useState(""),
    [selected, setSelected] = useState<number | null>(null);
  const svg = useRef<SVGSVGElement>(null),
    draftRef = useRef<Draft | null>(null);
  const put = (d: Draft | null) => {
    draftRef.current = d;
    setDraft(d);
  };
  const nodeNames = new Map(instances.map((v) => [v.node, v.node_name]));
  for (const n of networks)
    if (n.node && !nodeNames.has(n.node))
      nodeNames.set(n.node, `节点 #${n.node}`);
  const nets = networks.filter(
    (n) => !scope || !n.node || n.node === Number(scope),
  );
  const vms = instances
    .filter(
      (v) =>
        (!scope || v.node === Number(scope)) &&
        (`${v.name} ${v.node_name} ${v.uuid}`
          .toLowerCase()
          .includes(search.toLowerCase()) ||
          (interfaces[v.id] || []).some((i) =>
            i.source.toLowerCase().includes(search.toLowerCase()),
          )),
    )
    .sort(
      (a, b) =>
        a.node_name.localeCompare(b.node_name) || a.name.localeCompare(b.name),
    );
  const ny = (id: number) => 76 + nets.findIndex((n) => n.id === id) * 100,
    vy = (id: number) => 76 + vms.findIndex((v) => v.id === id) * 100;
  const height = Math.max(nets.length, vms.length, 2) * 100 + 120;
  const valid = (v: Instance | undefined, n: Network) =>
    !connectionError(v, n, interfaces[v?.id || 0] || []);
  function complete(kind: "vm" | "net", id: number) {
    if (!editable) {
      put(null);
      return;
    }
    const from = draftRef.current;
    if (!from || from.kind === kind) return;
    const v = instances.find((v) => v.id === (kind === "vm" ? id : from.id)),
      n = networks.find((n) => n.id === (kind === "net" ? id : from.id));
    put(null);
    if (!v || !n) return;
    if (!valid(v, n)) {
      setHint("无法连接：请核对节点范围、状态、重复网卡或管理网络保护。");
      return;
    }
    setHint("");
    onConnect?.(v, n);
  }
  function port(kind: "vm" | "net", id: number, x: number, y: number) {
    if (!editable) return;
    const vm = kind === "vm" ? instances.find((v) => v.id === id) : undefined;
    const net = kind === "net" ? networks.find((n) => n.id === id) : undefined;
    if (
      (vm &&
        (vm.observed_state_is_stale ||
          !["RUNNING", "SHUTOFF"].includes(vm.observed_state))) ||
      (net && (!net.is_usable || net.is_management))
    ) {
      setHint("该端口当前不可接入。");
      return;
    }
    const from = draftRef.current;
    if (from && from.kind !== kind) {
      complete(kind, id);
      return;
    }
    put({ kind, id, x, y });
    setCursor({ x, y });
    setHint("拖到目标端口，或点击另一侧端口；Esc 取消。");
  }
  function point(event: React.PointerEvent) {
    const matrix = svg.current?.getScreenCTM();
    if (!matrix) return;
    const p = new DOMPoint(event.clientX, event.clientY).matrixTransform(
      matrix.inverse(),
    );
    setCursor({ x: p.x, y: p.y });
  }
  function drop(event: React.PointerEvent) {
    const target = document
      .elementFromPoint(event.clientX, event.clientY)
      ?.closest("[data-port-kind]");
    if (target) {
      const kind = target.getAttribute("data-port-kind");
      if (kind === "vm" || kind === "net")
        complete(kind, Number(target.getAttribute("data-port-id")));
    } else if (draftRef.current) {
      put(null);
      setHint("连接已取消，请从端口拖线。");
    }
    if (svg.current?.hasPointerCapture(event.pointerId))
      svg.current.releasePointerCapture(event.pointerId);
  }
  const portEvents = (
    kind: "vm" | "net",
    id: number,
    x: number,
    y: number,
  ) => ({
    onPointerDown: (event: React.PointerEvent) => {
      event.preventDefault();
      port(kind, id, x, y);
      if (draftRef.current) svg.current?.setPointerCapture(event.pointerId);
    },
    onKeyDown: (event: React.KeyboardEvent) => {
      if (["Enter", " "].includes(event.key)) {
        event.preventDefault();
        port(kind, id, x, y);
      }
    },
  });
  const curve = (x1: number, y1: number, x2: number, y2: number) =>
    `M ${x1} ${y1} C ${(x1 + x2) / 2} ${y1}, ${(x1 + x2) / 2} ${y2}, ${x2} ${y2}`;
  return (
    <section
      className="topology-workspace"
      aria-label="交互网络拓扑"
      onKeyDown={(e) => {
        if (e.key === "Escape") {
          put(null);
          setHint("");
        }
      }}
    >
      <div className="topology-toolbar">
        <input
          aria-label="搜索拓扑虚拟机或网络"
          placeholder="搜索虚拟机、节点或已连接网络"
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            put(null);
          }}
        />
        <select
          aria-label="拓扑节点范围"
          value={scope}
          onChange={(e) => {
            setScope(e.target.value);
            put(null);
          }}
        >
          <option value="">全部节点</option>
          {[...nodeNames].map(([id, name]) => (
            <option key={id} value={id}>
              {name}
            </option>
          ))}
        </select>
        <button
          className="action sm"
          aria-label="缩小拓扑"
          onClick={() => setZoom((v) => Math.max(0.6, v - 0.2))}
        >
          −
        </button>
        <span>{Math.round(zoom * 100)}%</span>
        <button
          className="action sm"
          aria-label="放大拓扑"
          onClick={() => setZoom((v) => Math.min(2, v + 0.2))}
        >
          ＋
        </button>
        <button
          className="action sm"
          onClick={() => {
            setZoom(1);
            put(null);
          }}
        >
          重置视图
        </button>
      </div>
      <div className="topology-caption">
        <span>
          {nets.length} 个网络 · {vms.length} 台虚拟机 · 展示所有已登记网卡
        </span>
        <span>
          {editable ? "从蓝色端口拖线新增网卡，运行中支持热接入" : "只读拓扑"}
        </span>
      </div>
      <div className="topology-canvas">
        <svg
          ref={svg}
          viewBox={`0 0 1060 ${height}`}
          style={{ width: `${zoom * 100}%`, minWidth: 960 * zoom }}
          onPointerMove={(e) => {
            if (draftRef.current) point(e);
          }}
          onPointerUp={drop}
          onPointerCancel={() => put(null)}
          aria-label="网络与全部网卡配置拓扑"
        >
          <defs>
            <pattern
              id="topology-grid"
              width="24"
              height="24"
              patternUnits="userSpaceOnUse"
            >
              <circle cx="1" cy="1" r="1" fill="#dde4ee" />
            </pattern>
          </defs>
          <rect width="1060" height={height} fill="url(#topology-grid)" />
          <text x="32" y="35" className="topology-heading">
            虚拟网络 / 网桥
          </text>
          <text x="704" y="35" className="topology-heading">
            虚拟机 / 网卡
          </text>
          {vms.flatMap((v) =>
            (interfaces[v.id] || []).map((nic, index) => {
              const net =
                nets.find(
                  (n) =>
                    n.id ===
                    (nic as InstanceInterface & { network_id?: number })
                      .network_id,
                ) || nets.find((n) => n.name === nic.source);
              if (!net) return null;
              const y = vy(v.id) + 34 + (index % 4) * 5;
              return (
                <g key={`${v.id}-${nic.mac}`}>
                  <path
                    d={curve(344, ny(net.id) + 36, 704, y)}
                    stroke={selected === v.id ? "#2563eb" : "#b8c6d9"}
                    strokeWidth={selected === v.id ? 2.4 : 1.6}
                    fill="none"
                    strokeDasharray={
                      v.observed_state_is_stale ? "5 4" : undefined
                    }
                  >
                    <title>
                      {v.name} → {net.name} · {nic.name} · {nic.mac}
                    </title>
                  </path>
                  {selected === v.id && (
                    <text
                      x="520"
                      y={y - 5 + index * 14}
                      className="topology-edge-label"
                    >
                      {nic.name} · {nic.mac}
                    </text>
                  )}
                </g>
              );
            }),
          )}
          {nets.map((n) => (
            <g key={n.id} className="topology-resource">
              <rect
                x="32"
                y={ny(n.id)}
                width="312"
                height="76"
                rx="8"
                fill="white"
                stroke={
                  draft?.kind === "vm" &&
                  valid(
                    instances.find((v) => v.id === draft.id),
                    n,
                  )
                    ? "#2563eb"
                    : "#d9e1ec"
                }
              />
              <rect
                x="32"
                y={ny(n.id) + 10}
                width="4"
                height="56"
                rx="2"
                fill={n.type === "OVS" ? "#0f766e" : "#2563eb"}
              />
              <text x="48" y={ny(n.id) + 23} className="topology-title">
                {n.name.length > 28 ? n.name.slice(0, 27) + "…" : n.name}
              </text>
              <text x="48" y={ny(n.id) + 43} className="topology-sub">
                {labels[n.type] || n.type} · {n.bridge || "—"}
                {n.vlan_id ? ` · VLAN ${n.vlan_id}` : ""}
              </text>
              <text x="48" y={ny(n.id) + 62} className="topology-sub">
                {n.subnet || "未配置子网"} ·{" "}
                {n.is_management
                  ? "管理网络 · 受保护"
                  : n.is_usable
                    ? "可接入"
                    : "不可用"}
              </text>
              <circle
                cx="344"
                cy={ny(n.id) + 36}
                r="11"
                className="topology-port"
                role="button"
                tabIndex={editable ? 0 : -1}
                aria-label={`连接网络 ${n.name}`}
                aria-disabled={!editable || !n.is_usable || n.is_management}
                data-port-kind="net"
                data-port-id={n.id}
                {...portEvents("net", n.id, 344, ny(n.id) + 36)}
              />
            </g>
          ))}
          {vms.map((v) => (
            <g
              key={v.id}
              className="topology-resource"
              onClick={() => setSelected(v.id)}
            >
              <rect
                x="704"
                y={vy(v.id)}
                width="324"
                height="76"
                rx="8"
                fill="white"
                stroke={selected === v.id ? "#2563eb" : "#d9e1ec"}
              />
              <text x="724" y={vy(v.id) + 23} className="topology-title">
                {v.name.length > 28 ? v.name.slice(0, 27) + "…" : v.name}
              </text>
              <text x="724" y={vy(v.id) + 43} className="topology-sub">
                {v.node_name} ·{" "}
                {v.observed_state_is_stale
                  ? "状态待同步"
                  : v.observed_state === "RUNNING"
                    ? "运行中"
                    : v.observed_state === "SHUTOFF"
                      ? "已关机"
                      : v.observed_state}
              </text>
              <text x="724" y={vy(v.id) + 62} className="topology-sub">
                {(interfaces[v.id] || []).length} 个已登记网卡 ·{" "}
                {v.uuid.slice(0, 8)}
              </text>
              <circle
                cx="704"
                cy={vy(v.id) + 36}
                r="11"
                className="topology-port"
                role="button"
                tabIndex={editable ? 0 : -1}
                aria-label={`为虚拟机 ${v.name} 添加网卡`}
                aria-disabled={!editable || v.observed_state_is_stale}
                data-port-kind="vm"
                data-port-id={v.id}
                {...portEvents("vm", v.id, 704, vy(v.id) + 36)}
              />
            </g>
          ))}
          {draft && (
            <path
              d={curve(draft.x, draft.y, cursor.x, cursor.y)}
              stroke="#2563eb"
              strokeWidth="2.5"
              strokeDasharray="6 4"
              fill="none"
              pointerEvents="none"
            />
          )}
        </svg>
      </div>
      <p className="muted" role="status">
        {hint ||
          "连线表示服务端登记的网卡配置；虚线表示虚拟机状态过期。点击虚拟机可突出显示全部网卡连线。"}
      </p>
    </section>
  );
}
