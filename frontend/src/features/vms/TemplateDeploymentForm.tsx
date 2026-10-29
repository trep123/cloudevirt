import { newRequestId } from "../../utils/requestId";
import { useRef, useState } from "react";
import { api } from "../../api";
import { PageHeader } from "../../components/ConsoleUI";
import {
  Card,
  DescList,
  ErrorBanner,
  Field,
  describeError,
} from "../../components/ui";
import type { Network } from "../../types";

export function TemplateDeploymentForm({
  version,
  networks,
  onBack,
  onCancel,
  onCreated,
}: {
  version: {
    id: number;
    template_name: string;
    version: number;
    configuration: Record<string, unknown>;
  };
  networks: Network[];
  onBack: () => void;
  onCancel: () => void;
  onCreated: (id: string) => void;
}) {
  const c = version.configuration;
  const [name, setName] = useState(""),
    [primary, setPrimary] = useState(String(c.network_name || ""));
  const [extra, setExtra] = useState<string[]>(
    (c.additional_networks as string[]) || [],
  );
  const [busy, setBusy] = useState(false),
    [error, setError] = useState<string | null>(null);
  const key = useRef(newRequestId()),
    pending = useRef(false);
  const options = networks.filter(
    (n) => n.is_usable && (!n.node || !c.node || n.node === Number(c.node)),
  );
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (pending.current) return;
    if (!/^[A-Za-z0-9][A-Za-z0-9-]{1,62}[A-Za-z0-9]$/.test(name)) {
      setError("名称须为 3–64 位字母、数字或连字符，首尾为字母或数字");
      return;
    }
    const names = [primary, ...extra].filter(Boolean);
    if (
      new Set(names).size !== names.length ||
      extra.some((n) => !n) ||
      names.some((n) => !options.some((o) => o.name === n))
    ) {
      setError("请选择有效且不重复的网卡网络");
      return;
    }
    pending.current = true;
    setBusy(true);
    setError(null);
    const data = {
      template_version: version.id,
      name,
      network_name: primary,
      additional_networks: extra,
    };
    try {
      await api.request("/instances/preflight", {
        method: "POST",
        body: JSON.stringify(data),
      });
      const result = await api.createInstance(data, key.current);
      onCreated(result.task.id);
    } catch (e) {
      setError(
        describeError(e) +
          "。结果不确定时请先核对任务中心，再使用当前表单重试。",
      );
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }
  return (
    <>
      <PageHeader
        title="从模板创建虚拟机"
        description="硬件与系统配置固定继承发布版本，只需填写名称并指定网卡接入网络"
        back={{ label: "选择其他模板", onClick: onBack }}
      />
      <div className="wizard-layout">
        <Card
          title={`${version.template_name} · v${version.version}`}
          description="管理员发布的固定配置 · 创建时由服务端重新校验"
        >
          <form onSubmit={submit}>
            <ErrorBanner message={error} />
            <div className="wizard-fields">
              <Field label="虚拟机名称" hint="3–64 位字母、数字或连字符">
                <input
                  required
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="vm-web-01"
                  maxLength={64}
                />
              </Field>
              {[primary, ...extra].map((value, index) => (
                <Field
                  key={index}
                  label={
                    index === 0
                      ? "主网卡接入网络"
                      : `网卡 ${index + 1} 接入网络`
                  }
                >
                  <select
                    value={value}
                    required={index > 0}
                    onChange={(e) =>
                      index === 0
                        ? setPrimary(e.target.value)
                        : setExtra(
                            extra.map((v, i) =>
                              i === index - 1 ? e.target.value : v,
                            ),
                          )
                    }
                  >
                    <option value="">
                      {index === 0 ? "不接入网络" : "选择接入网络"}
                    </option>
                    {options.map((n) => (
                      <option value={n.name} key={n.id}>
                        {n.name} · {n.bridge || n.type}
                      </option>
                    ))}
                  </select>
                </Field>
              ))}
            </div>
            <p className="muted">
              网卡型号和数量由模板决定；每台虚拟机使用独立磁盘和 MAC
              地址。配额、节点权限、网络范围与镜像状态均由后端校验。
            </p>
            <div className="device-actions">
              <button
                className="action"
                type="button"
                disabled={busy}
                onClick={onCancel}
              >
                取消
              </button>
              <button className="action primary" disabled={busy}>
                {busy ? "正在校验并提交…" : "创建虚拟机"}
              </button>
            </div>
          </form>
        </Card>
        <aside className="wizard-summary">
          <Card title="模板配置 · 只读">
            <DescList
              columns={1}
              items={[
                ["vCPU", `${c.vcpu} 核`],
                ["内存", `${Number(c.memory_mib) / 1024} GiB`],
                ["系统盘", `${c.disk_gib} GiB · qcow2`],
                [
                  "数据盘",
                  ((c.data_disks as number[]) || [])
                    .map((v) => `${v} GiB`)
                    .join(" / ") || "无",
                ],
                [
                  "网卡",
                  `${extra.length + 1} 个槽位 · ${String((c.hardware as Record<string, unknown>)?.nic_model || "virtio")}`,
                ],
                ["创建后启动", c.start_after_create === false ? "否" : "是"],
                ["开机自启", c.autostart ? "是" : "否"],
              ]}
            />
            <p className="muted">
              CPU
              拓扑、固件、显卡、磁盘总线、性能限制及初始化配置均继承模板。需要修改时由管理员发布新版本。
            </p>
          </Card>
        </aside>
      </div>
    </>
  );
}
