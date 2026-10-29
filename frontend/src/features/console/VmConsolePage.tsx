import { lazy, Suspense, useEffect, useState } from "react";
import { api } from "../../api";
import { navigate } from "../../app/router";
import { PageHeader } from "../../components/ConsoleUI";
import { ErrorBanner, LoadingState, describeError } from "../../components/ui";
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
        description="独立控制台页面"
        back={{
          label: "返回虚拟机列表",
          onClick: () => navigate(prefix + "/vms"),
        }}
      >
        <button
          className="action"
          onClick={() => navigate(`${prefix}/vms/${id}`)}
        >
          虚拟机详情
        </button>
      </PageHeader>
      <ErrorBanner message={error} />
      {clipboardConfigured === false && (
        <p className="muted">
          此虚拟机尚未配置客体剪贴板通道。请正常关机后在“硬件”页启用通道，并在客体安装、运行
          spice-vdagent；配置前双向复制粘贴不会生效。
        </p>
      )}
      {vm ? (
        <Suspense fallback={<LoadingState text="正在加载控制台…" />}>
          <Console
            key={id}
            instanceId={id}
            desktopAvailable={vm.observed_state === "RUNNING"}
          />
        </Suspense>
      ) : !error ? (
        <LoadingState text="正在读取虚拟机…" />
      ) : null}
    </div>
  );
}
