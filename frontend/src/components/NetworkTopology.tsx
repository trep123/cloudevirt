import type { Instance, InstanceInterface, Network } from "../types";

const TYPE_LABEL: Record<string, string> = {
  LIBVIRT_NETWORK: "libvirt 网络",
  BRIDGE: "Linux 网桥",
  OVS: "OVS 网桥",
};

const TYPE_COLOR: Record<string, { fill: string; stroke: string; line: string }> = {
  LIBVIRT_NETWORK: { fill: "#f1f5f9", stroke: "#94a3b8", line: "#94a3b8" },
  BRIDGE: { fill: "#dbeafe", stroke: "#3b82f6", line: "#3b82f6" },
  OVS: { fill: "#dcfce7", stroke: "#16a34a", line: "#16a34a" },
};

const EMPTY_COLOR = { fill: "#f8fafc", stroke: "#cbd5e1", line: "#cbd5e1" };

function shortAddress(value: string | null): string {
  if (!value) return "-";
  const parts = value.split(".");
  return parts.length === 4 ? parts[3] : value;
}

export function NetworkTopology({
  networks,
  instances,
  interfaces,
}: {
  networks: Network[];
  instances: Instance[];
  interfaces: Record<number, InstanceInterface[]>;
}) {
  if (networks.length === 0 && instances.length === 0) {
    return <p className="empty">暂无网络或虚拟机，登记网络并创建虚拟机后将显示拓扑。</p>;
  }

  const sortedInstances = [...instances].sort((left, right) => {
    const nodeCompare = left.node_name.localeCompare(right.node_name);
    return nodeCompare !== 0 ? nodeCompare : left.name.localeCompare(right.name);
  });

  const rowHeight = 88;
  const top = 70;
  const networkX = 30;
  const networkWidth = 280;
  const vmX = 650;
  const vmWidth = 320;
  const width = 1000;
  const height = Math.max(networks.length, sortedInstances.length, 1) * rowHeight + top + 50;
  const networkIndex = new Map(networks.map((network, index) => [network.name, index]));
  const vmY = (index: number) => top + index * rowHeight;

  return (
    <svg className="network-topology" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="网络与接口拓扑">
      <defs>
        <marker id="topology-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
          <path d="M0,0 L8,4 L0,8 z" fill="#94a3b8" />
        </marker>
      </defs>
      <g className="topology-legend">
        <text x={30} y={30}>网络</text>
        <line x1={30} y1={42} x2={70} y2={42} stroke="#94a3b8" strokeWidth={2} />
        <text x={78} y={46}>libvirt</text>
        <line x1={150} y1={42} x2={190} y2={42} stroke="#3b82f6" strokeWidth={2} />
        <text x={198} y={46}>Linux 网桥</text>
        <line x1={300} y1={42} x2={340} y2={42} stroke="#16a34a" strokeWidth={2} />
        <text x={348} y={46}>OVS 网桥</text>
        <text x={620} y={46}>虚拟机（含节点与接口）</text>
      </g>

      {networks.map((network, index) => {
        const color = TYPE_COLOR[network.type] ?? EMPTY_COLOR;
        const y = top + index * rowHeight;
        return (
          <g key={`net-${network.id}`}>
            <rect
              x={networkX}
              y={y}
              width={networkWidth}
              height={64}
              rx={8}
              fill={color.fill}
              stroke={color.stroke}
              strokeWidth={network.is_management ? 2 : 1}
              strokeDasharray={network.is_management ? "5 3" : undefined}
            />
            <text x={networkX + 12} y={y + 20} className="topology-title">{network.name}</text>
            <text x={networkX + 12} y={y + 38} className="topology-sub">
              {TYPE_LABEL[network.type] ?? network.type}
              {network.bridge ? ` · ${network.bridge}` : ""}
              {network.vlan_id ? ` · VLAN ${network.vlan_id}` : ""}
            </text>
            <text x={networkX + 12} y={y + 54} className="topology-sub">
              {network.subnet ? `子网 ${network.subnet}` : "子网未配置"}
              {network.dhcp_enabled
                ? ` · DHCP ${shortAddress(network.dhcp_start)}-${shortAddress(network.dhcp_end)}`
                : " · DHCP 关闭"}
            </text>
            {network.is_management ? <text x={networkX + networkWidth - 10} y={y + 20} textAnchor="end" className="topology-warn">管理网</text> : null}
            {network.is_default ? <text x={networkX + networkWidth - 10} y={y + 20} textAnchor="end" className="topology-ok">默认</text> : null}
          </g>
        );
      })}

      {sortedInstances.map((instance, index) => {
        const y = vmY(index);
        const networkIndexValue = networkIndex.get(instance.network_name);
        const network = networkIndexValue === undefined ? null : networks[networkIndexValue];
        const color = network ? TYPE_COLOR[network.type] ?? EMPTY_COLOR : EMPTY_COLOR;
        const vnic = interfaces[instance.id]?.[0];
        const midX = (networkX + networkWidth + vmX) / 2;
        const networkY = networkIndexValue === undefined ? y : top + networkIndexValue * rowHeight;
        const startY = networkY + 32;
        const endY = y + 26;
        return (
          <g key={`vm-${instance.id}`}>
            {network ? (
              <>
                <path
                  d={`M ${networkX + networkWidth} ${startY} C ${midX} ${startY}, ${midX} ${endY}, ${vmX} ${endY}`}
                  fill="none"
                  stroke={color.line}
                  strokeWidth={2}
                  markerEnd="url(#topology-arrow)"
                />
                <text x={midX} y={(startY + endY) / 2 - 5} textAnchor="middle" className="topology-link">
                  {vnic ? `${vnic.name} · ${vnic.mac}` : "vNIC"}
                </text>
              </>
            ) : null}
            <rect
              x={vmX}
              y={y}
              width={vmWidth}
              height={52}
              rx={8}
              fill="#ffffff"
              stroke={network ? color.stroke : "#cbd5e1"}
              strokeDasharray={network ? undefined : "5 3"}
            />
            <text x={vmX + 12} y={y + 20} className="topology-title">{instance.name}</text>
            <text x={vmX + 12} y={y + 38} className="topology-sub">
              {instance.node_name} · {instance.observed_state}
              {network ? ` · ${network.name}` : " · 未接入网络"}
            </text>
            <text x={vmX + vmWidth - 10} y={y + 20} textAnchor="end" className="topology-sub">
              {vnic ? vnic.type : "vNIC"}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
