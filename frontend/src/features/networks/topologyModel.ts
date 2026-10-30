import type { Instance, Network, InstanceInterface } from "../../types";
export type TopologyVM = Pick<
  Instance,
  | "id"
  | "uuid"
  | "name"
  | "node"
  | "node_name"
  | "network_name"
  | "observed_state"
  | "observed_state_is_stale"
  | "observed_state_updated_at"
  | "operation_status"
>;
export type TopologyNIC = InstanceInterface & { network_id?: number };
export function connectionError(
  vm: TopologyVM | undefined,
  network: Network,
  nics: TopologyNIC[],
): string | null {
  if (!vm) return "虚拟机已不在当前范围";
  if (!network.is_usable || network.is_management)
    return "网络不可用或属于受保护管理网络";
  if (network.node && network.node !== vm.node)
    return "网络与虚拟机不在同一节点";
  if (
    vm.observed_state_is_stale ||
    !["RUNNING", "SHUTOFF"].includes(vm.observed_state)
  )
    return "请等待虚拟机状态同步为运行或关机";
  if (
    nics.some((n) => n.network_id === network.id || n.source === network.name)
  )
    return "虚拟机已连接该网络";
  if (nics.length >= 8) return "最多支持 8 个网卡";
  return null;
}
