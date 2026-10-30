import { useEffect, useState } from "react";
import { api } from "../../api";
import { describeError } from "../../components/ui";

export function StoragePoolField({ node, value, onChange, disabled = false }: {
  node: string; value: string; onChange: (value: string) => void; disabled?: boolean;
}) {
  const [data, setData] = useState<{ results: { name: string; path: string }[]; default: string; legacy_available: boolean } | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let alive = true;
    setData(null); setError(""); onChange("");
    if (node) void api.request<NonNullable<typeof data>>(`/storage-pools/available/?node=${node}&purpose=images`).then((result) => {
      if (alive) { setData(result); onChange(result.default || (result.legacy_available ? "__legacy__" : "")); }
    }).catch((err) => { if (alive) setError(describeError(err)); });
    return () => { alive = false; };
  }, [node]);
  return <label>存储池
    <select required disabled={disabled || !data} value={value} onChange={(event) => onChange(event.target.value)}>
      <option value="">{data ? "请选择存储池" : "正在读取存储池…"}</option>
      {data?.legacy_available && <option value="__legacy__">节点原有镜像目录</option>}
      {data?.results.map((pool) => <option key={pool.name} value={pool.name}>{pool.name} · {pool.path}</option>)}
    </select>
    {error && <small role="alert">{error}</small>}
    <small>相对路径以所选池目录为起点；普通用户使用管理员指定的默认池。</small>
  </label>;
}
