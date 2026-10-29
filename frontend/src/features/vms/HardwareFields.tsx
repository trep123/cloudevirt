import { Field } from "../../components/ui";
export type HardwareConfig = {
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
    <details className="field-wide">
      <summary>�߼�Ӳ�������ܿ���{locked ? "��ģ����������" : ""}</summary>
      <p className="muted">
        ѡ�����ݽڵ�ʵ��������CPU
        ģʽ����Ӱ��Ǩ�Ƽ����ԣ��������Ʋ�����������Դ��ռ��
      </p>
      <div className="infra-form">
        <Field label="������Կ�">
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
            <option value="">�ڵ�Ĭ�ϣ���׼ VGA��</option>
            {caps?.video_models?.map((v) => (
              <option key={v} value={v}>
                {v === "virtio"
                  ? "VirtIO GPU�������������"
                  : "��׼ VGA��64 MiB��"}
              </option>
            ))}
          </select>
        </Field>
        {value.video_model && (
          <>
            <Field label="������ʾ����">
              <input
                type="number"
                min={640}
                max={3840}
                value={value.video_width || 1920}
                disabled={locked}
                onChange={(e) =>
                  onChange({ ...value, video_width: Number(e.target.value) })
                }
              />
            </Field>
            <Field label="������ʾ�߶�">
              <input
                type="number"
                min={480}
                max={2160}
                value={value.video_height || 1080}
                disabled={locked}
                onChange={(e) =>
                  onChange({ ...value, video_height: Number(e.target.value) })
                }
              />
            </Field>
            <p className="muted field-wide">
              �ߴ�д�������Կ����ã����������ʹ���Լ�����ʾ���ã�������ǿ������ֱ��ʡ�Linux
              ���� VirtIO��Windows ���Ӧ������
            </p>
          </>
        )}
        <Field label="CPU ģʽ">
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
            <option value="">�ڵ�Ĭ��</option>
            {caps?.cpu_modes?.map((mode) => (
              <option key={mode} value={mode}>
                {mode}
              </option>
            ))}
          </select>
        </Field>
        <Field label="�̼�">
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
          ָ�� CPU ����
        </label>
        {topology &&
          (["sockets", "cores", "threads"] as const).map((key) => (
            <Field
              key={key}
              label={
                { sockets: "���", cores: "ÿ��ۺ���", threads: "ÿ�����߳�" }[
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
          Secure Boot����Ҫ UEFI �̼�����Կ��
        </label>
        <label className="check">
          <input
            type="checkbox"
            checked={value.tpm || false}
            disabled={locked || !caps?.tpm_emulator}
            onChange={(e) => onChange({ ...value, tpm: e.target.checked })}
          />
          TPM 2.0 ģ����
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
                  cpu_quota_percent: "CPU ���޶100%=1�ˣ�0=���ޣ�",
                  disk_read_iops: "ÿ�̶�ȡ IOPS��0=���ޣ�",
                  disk_write_iops: "ÿ��д�� IOPS��0=���ޣ�",
                  network_mbps: "ÿ����˫�� Mbit/s��0=���ޣ�OVS �ݲ�֧�֣�",
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
