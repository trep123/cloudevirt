import { useEffect, useState } from "react";
import { api } from "../../api";
import { DisksPage } from "../../pages/DisksPage";
import { PageHeader, ResourceStatCard } from "../../components/ConsoleUI";
import { ErrorBanner, describeError, formatBytes } from "../../components/ui";
import { navigate } from "../../app/router";
import type { Node } from "../../types";
export function StoragePage() {
  const [nodes, setNodes] = useState<Node[] | null>(null),
    [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api
      .nodes()
      .then((p) => setNodes(p.results))
      .catch((e) => setError(describeError(e)));
  }, []);
  const fresh = nodes?.filter(
      (n) =>
        !n.resource_is_stale &&
        n.storage_total_bytes !== null &&
        n.storage_free_bytes !== null,
    ),
    total = fresh?.reduce((s, n) => s + (n.storage_total_bytes || 0), 0),
    free = fresh?.reduce((s, n) => s + (n.storage_free_bytes || 0), 0);
  return (
    <>
      <PageHeader title="数据卷与存储" description="节点容量采集与磁盘生命周期管理">
        <button className="action" onClick={() => navigate("/admin/images")}>
          镜像管理
        </button>
        <button
          className="action"
          onClick={() => navigate("/admin/storage-pools")}
        >
          管理存储池
        </button>
      </PageHeader>
      <ErrorBanner message={error} />
      <div className="resource-stats">
        <ResourceStatCard
          label="容量采集节点"
          value={nodes ? fresh?.length : "—"}
          note="仅统计未过期数据"
        />
        <ResourceStatCard
          label="总容量"
          value={formatBytes(total)}
          note="节点目录文件系统容量"
        />
        <ResourceStatCard
          label="已用容量"
          value={
            total !== undefined && free !== undefined
              ? formatBytes(total - free)
              : "—"
          }
          note="文件系统实际占用"
        />
        <ResourceStatCard
          label="数据过期节点"
          value={nodes ? nodes.filter((n) => n.resource_is_stale).length : "—"}
          note="过期数据不参与容量合计"
        />
      </div>
      <DisksPage embedded />
    </>
  );
}
