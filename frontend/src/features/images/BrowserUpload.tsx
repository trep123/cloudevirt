import { useEffect, useRef, useState } from "react";
import { api, ApiError, uploadImageChunk } from "../../api";
import {
  Card,
  ErrorBanner,
  describeError,
  formatBytes,
} from "../../components/ui";
import type { Node } from "../../types";
import { newUploadId } from "./uploadId";

type Upload = {
  id: string;
  image_id: number;
  chunk_bytes: number;
  size_bytes: number;
  status: string;
  task_id: string | null;
  offset?: number;
};
export function BrowserUpload({
  nodes,
  onSubmitted,
  onChanged,
}: {
  nodes: Node[];
  onSubmitted: (id: string) => void;
  onChanged: () => void;
}) {
  const [file, setFile] = useState<File | null>(null),
    [name, setName] = useState(""),
    [node, setNode] = useState("");
  const [family, setFamily] = useState(""),
    [version, setVersion] = useState("");
  const [caps, setCaps] = useState<{
    max_bytes: number;
    chunk_bytes: number;
  } | null>(null);
  const [session, setSession] = useState<Upload | null>(null),
    [attempted, setAttempted] = useState(false);
  const [busy, setBusy] = useState(false),
    [received, setReceived] = useState(0),
    [sent, setSent] = useState(0);
  const [error, setError] = useState<string | null>(null),
    [status, setStatus] = useState("");
  const [confirmCancel, setConfirmCancel] = useState(false);
  const controller = useRef<AbortController | null>(null),
    id = useRef(newUploadId()),
    input = useRef<HTMLInputElement>(null);
  const working = useRef(false);
  const targetNode =
    node || String(nodes.find((n) => n.is_schedulable)?.id || "");
  function loadCaps() {
    api
      .request<{ max_bytes: number; chunk_bytes: number }>("/images/uploads")
      .then(setCaps)
      .catch((e) => setError(describeError(e)));
  }
  useEffect(() => {
    loadCaps();
    return () => controller.current?.abort();
  }, []);
  function reset() {
    setSession(null);
    setFile(null);
    setName("");
    setAttempted(false);
    setReceived(0);
    setSent(0);
    setStatus("");
    id.current = newUploadId();
    if (input.current) input.current.value = "";
  }
  async function upload() {
    if (!file || !caps || !targetNode || working.current) return;
    if (!file.size || file.size > caps.max_bytes) {
      setError(`文件必须非空且不超过 ${formatBytes(caps.max_bytes)}`);
      return;
    }
    working.current = true;
    setBusy(true);
    setError(null);
    setAttempted(true);
    const abort = new AbortController();
    controller.current = abort;
    try {
      let current = session;
      if (!current) {
        setStatus("正在创建上传会话…");
        current = await api.request<Upload>("/images/uploads", {
          method: "POST",
          signal: abort.signal,
          body: JSON.stringify({
            id: id.current,
            name,
            node: Number(targetNode),
            original_name: file.name,
            size_bytes: file.size,
            os_family: family,
            os_version: version,
          }),
        });
        setSession(current);
        onChanged();
      }
      const progress = await api.request<Upload>(
        `/images/uploads/${current.id}`,
        { signal: abort.signal },
      );
      if (progress.task_id) {
        onSubmitted(progress.task_id);
        reset();
        return;
      }
      let offset = progress.offset || 0;
      if (!Number.isSafeInteger(offset) || offset < 0 || offset > file.size)
        throw new Error("节点返回了无效的上传进度");
      setReceived(offset);
      setSent(offset);
      while (offset < file.size) {
        if (abort.signal.aborted)
          throw new DOMException("已暂停", "AbortError");
        setStatus("正在发送分片，等待节点确认…");
        const chunk = file.slice(offset, offset + current.chunk_bytes);
        const response = await uploadImageChunk(
          current.id,
          offset,
          chunk,
          abort.signal,
          (bytes) => setSent(Math.min(offset + bytes, file.size)),
        );
        if (response.offset !== offset + chunk.size)
          throw new Error("节点返回的分片偏移不一致，请查询进度后继续");
        offset = response.offset;
        setReceived(offset);
        setSent(offset);
      }
      setStatus("文件已接收，正在提交后台校验…");
      const result = await api.request<{ task_id: string }>(
        `/images/uploads/${current.id}/complete`,
        { method: "POST", signal: abort.signal },
      );
      onSubmitted(result.task_id);
      onChanged();
      reset();
    } catch (e) {
      if (abort.signal.aborted)
        setStatus("上传已暂停；继续时会先查询节点实际接收进度。");
      else {
        setError(describeError(e));
        setStatus("上传未完成，已接收的数据保留，可继续或取消。");
      }
    } finally {
      working.current = false;
      setBusy(false);
    }
  }
  async function cancel() {
    if (working.current) return;
    setBusy(true);
    setError(null);
    try {
      await api.request(`/images/uploads/${session?.id || id.current}`, {
        method: "DELETE",
      });
      reset();
      onChanged();
      setConfirmCancel(false);
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) {
        reset();
        setConfirmCancel(false);
      } else setError(describeError(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Card title="从浏览器上传镜像">
      <ErrorBanner message={error} />
      <form
        className="inline"
        onSubmit={(e) => {
          e.preventDefault();
          void upload();
        }}
      >
        <label>
          镜像文件
          <input
            ref={input}
            type="file"
            accept=".qcow2,.raw,.img,.iso"
            required={!file}
            disabled={attempted || busy}
            onChange={(e) => {
              const selected = e.target.files?.[0] || null;
              setFile(selected);
              if (selected && !name)
                setName(selected.name.replace(/\.(qcow2|raw|img|iso)$/i, ""));
            }}
          />
        </label>
        <label>
          名称
          <input
            minLength={2}
            maxLength={128}
            required
            value={name}
            disabled={attempted || busy}
            onChange={(e) => setName(e.target.value)}
          />
        </label>
        <label>
          目标节点
          <select
            required
            value={targetNode}
            disabled={attempted || busy}
            onChange={(e) => setNode(e.target.value)}
          >
            <option value="">请选择在线节点</option>
            {nodes
              .filter((n) => n.is_schedulable)
              .map((n) => (
                <option key={n.id} value={n.id}>
                  {n.name}
                </option>
              ))}
          </select>
        </label>
        <label>
          系统系列
          <input
            maxLength={32}
            value={family}
            disabled={attempted || busy}
            onChange={(e) => setFamily(e.target.value)}
          />
        </label>
        <label>
          系统版本
          <input
            maxLength={32}
            value={version}
            disabled={attempted || busy}
            onChange={(e) => setVersion(e.target.value)}
          />
        </label>
        <button
          className="action primary"
          disabled={busy || !file || !caps || !targetNode}
        >
          {attempted ? "查询进度并继续" : "开始上传"}
        </button>
        {busy ? (
          <button
            type="button"
            className="action"
            onClick={() => controller.current?.abort()}
          >
            暂停
          </button>
        ) : null}
        {attempted && !busy ? (
          <button
            type="button"
            className="action danger"
            onClick={() => setConfirmCancel(true)}
          >
            取消本次上传
          </button>
        ) : null}
      </form>
      <p className="muted">
        支持 qcow2、raw、img、ISO。
        {caps
          ? `当前单文件上限 ${formatBytes(caps.max_bytes)}，分片 ${formatBytes(caps.chunk_bytes)}。`
          : "正在读取服务端上传限制…"}
        上传完成后由节点检测格式并计算 SHA-256，通过后才可用。
      </p>
      {!caps ? (
        <button className="action" onClick={loadCaps}>
          重新获取上传限制
        </button>
      ) : null}
      {file && attempted ? (
        <div aria-live="polite">
          <progress
            max={file.size || 1}
            value={received}
          />
          <p>
            节点已确认：{formatBytes(received)} / {formatBytes(file.size)}（
            {((received * 100) / file.size).toFixed(1)}%） · 已发送：
            {formatBytes(sent)}
          </p>
          <p role="status">{status}</p>
        </div>
      ) : null}
      {confirmCancel ? (
        <div className="banner banner-info">
          <p>
            确认取消 {file?.name}{" "}
            的上传？只清理未发布的临时分片，不删除已有镜像。
          </p>
          <button
            className="action danger"
            disabled={busy}
            onClick={() => void cancel()}
          >
            确认取消上传
          </button>
          <button
            className="action"
            disabled={busy}
            onClick={() => setConfirmCancel(false)}
          >
            保留并继续
          </button>
        </div>
      ) : null}
    </Card>
  );
}
