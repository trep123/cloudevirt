import { lazy, Suspense, useEffect, useState } from "react";
import { api } from "../../api";
import { navigate } from "../../app/router";
import { PageHeader } from "../../components/ConsoleUI";
import {
  ErrorBanner,
  LoadingState,
  describeError,
  StatusBadge,
} from "../../components/ui";
import { Icon } from "../../components/icons";
import type { Instance } from "../../types";
const Console = lazy(() =>
  import("../../components/VncConsole").then((m) => ({
    default: m.VncConsole,
  })),
);
export function VmConsolePage({ id, admin }: { id: number; admin: boolean }) {
  const [vm, setVm] = useState<Instance | null>(null),
    [error, setError] = useState<string | null>(null);
  const [clipboardConfigured, setClipboardConfigured] = useState<
    boolean | null
  >(null);
  const prefix = admin ? "/admin" : "/app";
  useEffect(() => {
    let alive = true;
    setClipboardConfigured(null);
    api
      .request<{ configured: { clipboard: boolean } }>(
        `/instances/${id}/display`,
      )
      .then((v) => {
        if (alive) setClipboardConfigured(v.configured.clipboard);
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [id]);
  useEffect(() => {
    let alive = true,
      loading = false;
    setVm(null);
    setError(null);
    const load = async () => {
      if (loading || document.hidden) return;
      loading = true;
      try {
        const data = await api.instance(id);
        if (alive) {
          setVm(data);
          setError(null);
        }
      } catch (e) {
        if (alive) {
          setError(describeError(e));
          setVm(null);
        }
      } finally {
        loading = false;
      }
    };
    void load();
    const timer = setInterval(() => void load(), 15000);
    document.addEventListener("visibilitychange", load);
    return () => {
      alive = false;
      clearInterval(timer);
      document.removeEventListener("visibilitychange", load);
    };
  }, [id]);
  return (
    <div className="vm-console-page">
      <PageHeader
        title={`${vm?.name || "虚拟机"} · 远程控制台`}
        description={
          vm
            ? `${vm.node_name} · ${vm.vcpu} vCPU · ${vm.memory_mib / 1024} GiB 内存`
            : "正在读取控制台信息"
        }
        meta={vm ? <StatusBadge status={vm.observed_state} /> : undefined}
        back={{
          label: "返回虚拟机列表",
          onClick: () => navigate(prefix + "/vms"),
        }}
      >
        <button
          className="action"
          onClick={() => navigate(`${prefix}/vms/${id}`)}
        >
          <Icon name="settings" size={15} />
          虚拟机详情
        </button>
      </PageHeader>
      <ErrorBanner message={error} />
      {vm ? (
        <Suspense fallback={<LoadingState text="正在加载控制台…" />}>
          <Console
            key={id}
            instanceId={id}
            desktopAvailable={vm.observed_state === "RUNNING"}
            instanceName={vm.name}
            clipboardConfigured={clipboardConfigured}
          />
        </Suspense>
      ) : !error ? (
        <LoadingState text="正在读取虚拟机…" />
      ) : null}
    </div>
  );
}
