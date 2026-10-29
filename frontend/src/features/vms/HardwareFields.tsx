import { Field } from "../../components/ui";
export type HardwareConfig = {
  cpu_mode?: string;
  sockets?: number;
  cores?: number;
  threads?: number;
  firmware?: string;
  secure_boot?: boolean;
  tpm?: boolean;
  cpu_quota_percent?: number;
  disk_read_iops?: number;
  disk_write_iops?: number;
  network_mbps?: number;
};
export type CreationCapabilities = {
  static_networks?: boolean;
  policy?: { vcpu: number; memory_mib: number; disk_gib: number };
  cpu_modes?: string[];
  firmware?: string[];
  secure_boot?: boolean;
  tpm_emulator?: boolean;
  cloud_init?: boolean;
  multi_disk?: boolean;
  multi_nic?: boolean;
  performance_limits?: boolean;
};
export function HardwareFields({
  value,
  onChange,
  caps,
  cpu,
  isAdmin,
  locked = false,
}: {
  value: HardwareConfig;
  onChange: (v: HardwareConfig) => void;
  caps: CreationCapabilities | null;
  cpu: number;
  isAdmin: boolean;
  locked?: boolean;
}) {
  const topology = value.sockets !== undefined;
  return (
    <details className="field-wide">
      <summary>高级硬件与性能控制{locked ? "（模板已锁定）" : ""}</summary>
      <p className="muted">
        选项依据节点实际能力。CPU
        模式可能影响迁移兼容性；性能限制不代表物理资源独占。
      </p>
      <div className="infra-form">
        <Field label="CPU 模式">
          <select
            value={value.cpu_mode || ""}
            disabled={locked || !caps}
            onChange={(e) => {
              const next = { ...value };
              if (e.target.value) next.cpu_mode = e.target.value;
              else delete next.cpu_mode;
              onChange(next);
            }}
          >
            <option value="">节点默认</option>
            {caps?.cpu_modes?.map((mode) => (
              <option key={mode} value={mode}>
                {mode}
              </option>
            ))}
          </select>
        </Field>
        <Field label="固件">
          <select
            value={value.firmware || "bios"}
            disabled={locked || !caps}
            onChange={(e) =>
              onChange({
                ...value,
                firmware: e.target.value,
                secure_boot: false,
              })
            }
          >
            {(caps?.firmware || ["bios"]).map((f) => (
              <option key={f} value={f}>
                {f.toUpperCase()}
              </option>
            ))}
          </select>
        </Field>
        <label className="check">
          <input
            type="checkbox"
            checked={topology}
            disabled={locked || !caps?.cpu_modes?.length}
            onChange={(e) => {
              const next = { ...value };
              if (e.target.checked) {
                next.sockets = 1;
                next.cores = cpu;
                next.threads = 1;
              } else {
                delete next.sockets;
                delete next.cores;
                delete next.threads;
              }
              onChange(next);
            }}
          />
          指定 CPU 拓扑
        </label>
        {topology &&
          (["sockets", "cores", "threads"] as const).map((key) => (
            <Field
              key={key}
              label={
                { sockets: "插槽", cores: "每插槽核心", threads: "每核心线程" }[
                  key
                ]
              }
            >
              <input
                type="number"
                min={1}
                max={128}
                value={value[key]}
                disabled={locked}
                onChange={(e) =>
                  onChange({ ...value, [key]: Number(e.target.value) })
                }
              />
            </Field>
          ))}
        <label className="check">
          <input
            type="checkbox"
            checked={value.secure_boot || false}
            disabled={locked || value.firmware !== "uefi" || !caps?.secure_boot}
            onChange={(e) =>
              onChange({ ...value, secure_boot: e.target.checked })
            }
          />
          Secure Boot（需要 UEFI 固件和密钥）
        </label>
        <label className="check">
          <input
            type="checkbox"
            checked={value.tpm || false}
            disabled={locked || !caps?.tpm_emulator}
            onChange={(e) => onChange({ ...value, tpm: e.target.checked })}
          />
          TPM 2.0 模拟器
        </label>
        {isAdmin &&
          caps?.performance_limits &&
          (
            [
              "cpu_quota_percent",
              "disk_read_iops",
              "disk_write_iops",
              "network_mbps",
            ] as const
          ).map((key) => (
            <Field
              key={key}
              label={
                {
                  cpu_quota_percent: "CPU 总限额（100%=1核，0=不限）",
                  disk_read_iops: "每盘读取 IOPS（0=不限）",
                  disk_write_iops: "每盘写入 IOPS（0=不限）",
                  network_mbps: "每网卡双向 Mbit/s（0=不限，OVS 暂不支持）",
                }[key]
              }
            >
              <input
                type="number"
                min={0}
                max={
                  key === "cpu_quota_percent"
                    ? cpu * 100
                    : key === "network_mbps"
                      ? 100000
                      : 1000000
                }
                value={value[key] || 0}
                disabled={locked}
                onChange={(e) =>
                  onChange({ ...value, [key]: Number(e.target.value) })
                }
              />
            </Field>
          ))}
      </div>
    </details>
  );
}
