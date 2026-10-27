import { useCallback, useEffect, useState } from "react";

import { api } from "../api";
import { Card, Empty, ErrorBanner, describeError } from "../components/ui";
import type { Network } from "../types";

export function NetworksPage() {
  const [networks, setNetworks] = useState<Network[]>([]);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      setNetworks((await api.networks()).results);
      setError(null);
    } catch (err) {
      setError(describeError(err));
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  return (
    <>
      <div className="page-head">
        <h2>网络白名单</h2>
        <button className="action" onClick={() => void reload()}>刷新</button>
      </div>
      <ErrorBanner message={error} />
      <Card title={`共 ${networks.length} 个网络`}>
        {networks.length === 0 ? (
          <Empty text="尚未登记网络。管理员需先在后台登记节点上已验证的网络。" />
        ) : (
          <table>
            <thead>
              <tr>
                <th>名称</th>
                <th>类型</th>
                <th>桥接</th>
                <th>VLAN</th>
                <th>属性</th>
                <th>说明</th>
              </tr>
            </thead>
            <tbody>
              {networks.map((network) => (
                <tr key={network.id}>
                  <td>{network.name}</td>
                  <td>{network.type}</td>
                  <td className="mono">{network.bridge || "-"}</td>
                  <td>{network.vlan_id ?? "-"}</td>
                  <td>
                    {network.is_default ? "默认" : ""}
                    {network.is_management ? " 管理网（禁止接入）" : ""}
                    {network.is_usable ? "" : " 不可用"}
                  </td>
                  <td>{network.description || "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </>
  );
}
