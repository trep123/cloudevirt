import { Field } from "../../components/ui";
export type HardwareConfig = {
  nic_model?: string;
  data_disk_bus?: string;
  clipboard?: boolean;
  video_model?: string;
  video_width?: number;
  video_height?: number;
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
  linked_clone?: boolean;
  clipboard?: boolean;
  video_models?: string[];
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
    <section className="field-wide hardware-details hardware-config" aria-label="虚拟机硬件配置">
      <header className="hardware-config-header">
        <h3>硬件配置</h3>
        <span>{locked ? "只读 · 由管理员或模板控制" : "可配置"}</span>
      </header>
      <p className="muted">
        选项依据节点实际能力。CPU
        模式可能影响迁移兼容性；性能限制不代表物理资源独占。
      </p>
      <div className="infra-form">
        <h4 className="field-wide hardware-group-title">设备接口 · 网卡与磁盘</h4>
        <Field label="创建时网卡型号">
          <select
            value={value.nic_model || "virtio"}
            disabled={locked}
            onChange={(e) => onChange({ ...value, nic_model: e.target.value })}
          >
            <option value="virtio">VirtIO</option>
            <option value="e1000e">Intel e1000e</option>
          </select>
        </Field>
        <Field label="创建时数据盘总线">
          <select
            value={value.data_disk_bus || "virtio"}
            disabled={locked}
            onChange={(e) =>
              onChange({ ...value, data_disk_bus: e.target.value })
            }
          >
            <option value="virtio">VirtIO</option>
            <option value="sata">SATA</option>
          </select>
        </Field>
        <h4 className="field-wide hardware-group-title">显示与交互</h4>
        <label className="check">
          <input
            type="checkbox"
            checked={value.clipboard || false}
            disabled={locked || !caps?.clipboard}
            onChange={(e) =>
              onChange({ ...value, clipboard: e.target.checked })
            }
          />
          启用客体剪贴板通道（需要 spice-vdagent，仅文本）
        </label>
        {!caps?.clipboard && <small className="muted field-wide">{caps ? "节点未声明剪贴板通道支持" : "正在读取节点硬件能力"}</small>}
        <Field label="虚拟机显卡">
          <select
            value={value.video_model || ""}
            disabled={locked || !caps?.video_models?.length}
            onChange={(e) => {
              const next = { ...value };
              if (e.target.value) {
                next.video_model = e.target.value;
                next.video_width = 1920;
                next.video_height = 1080;
              } else {
                delete next.video_model;
                delete next.video_width;
                delete next.video_height;
              }
              onChange(next);
            }}
          >
            <option value="">节点默认（标准 VGA）</option>
            {caps?.video_models?.map((v) => (
              <option key={v} value={v}>
                {v === "virtio"
                  ? "VirtIO GPU（需客体驱动）"
                  : "标准 VGA（64 MiB）"}
              </option>
            ))}
          </select>
        </Field>
        {(
          <>
            <Field label="启动显示宽度">
              <input
                type="number"
                min={640}
                max={3840}
                value={value.video_width || 1920}
                disabled={locked || !value.video_model}
                onChange={(e) =>
                  onChange({ ...value, video_width: Number(e.target.value) })
                }
              />
            </Field>
            <Field label="启动显示高度">
              <input
                type="number"
                min={480}
                max={2160}
                value={value.video_height || 1080}
                disabled={locked || !value.video_model}
                onChange={(e) =>
                  onChange({ ...value, video_height: Number(e.target.value) })
                }
              />
            </Field>
            <p className="muted field-wide">
              {!value.video_model && "选择显卡型号后才会写入下面的启动尺寸，当前使用节点默认配置。"}
              尺寸写入虚拟显卡配置；客体桌面可使用自己的显示设置，不等于强制桌面分辨率。Linux
              建议 VirtIO，Windows 需对应驱动。
            </p>
          </>
        )}
        <h4 className="field-wide hardware-group-title">处理器与系统固件</h4>
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
        {
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
                value={value[key] ?? (key === "cores" ? cpu : 1)}
                disabled={locked || !topology}
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
        <p className="muted field-wide">{value.firmware !== "uefi" ? "Secure Boot 需先选择 UEFI。" : !caps?.secure_boot ? "节点未声明 Secure Boot 支持。" : "Secure Boot 由节点固件能力控制。"} {!caps?.tpm_emulator ? "节点未声明 TPM 模拟器支持。" : "TPM 使用节点支持的模拟器。"}</p>
        <h4 className="field-wide hardware-group-title">性能限制</h4>
        <p className="muted field-wide">{!isAdmin ? "仅管理员可修改性能限制。" : !caps?.performance_limits ? "当前节点未声明性能限制支持，选项只读。" : "0 表示不限制；CPU 100% 对应一个逻辑核心。"}</p>
        {
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
                disabled={locked || !isAdmin || !caps?.performance_limits}
                onChange={(e) =>
                  onChange({ ...value, [key]: Number(e.target.value) })
                }
              />
            </Field>
          ))}
      </div>
    </section>
  );
}
