import { useCallback, useEffect, useState } from "react";

import { api } from "../api";
import { Card, Empty, ErrorBanner, StatusBadge, describeError, formatBytes } from "../components/ui";
import type { Image, Node } from "../types";


export function ImagesPage() {
  const [images, setImages] = useState<Image[]>([]);
  const [nodes, setNodes] = useState<Node[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [nodeId, setNodeId] = useState<string>("");
  const [relativePath, setRelativePath] = useState("");
  const [osFamily, setOsFamily] = useState("");
  const [osVersion, setOsVersion] = useState("");
  const [busy, setBusy] = useState(false);
  const [editImage, setEditImage] = useState<Image | null>(null);
  const [editFamily, setEditFamily] = useState("");
  const [editVersion, setEditVersion] = useState("");

  const reload = useCallback(async () => {
    try {
      const [imagePage, nodePage] = await Promise.all([api.images(), api.nodes()]);
      setImages(imagePage.results);
      setNodes(nodePage.results);
      setNodeId((current) => current || String(nodePage.results[0]?.id ?? ""));
      setError(null);
    } catch (err) {
      setError(describeError(err));
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.importImage({
        name,
        node: Number(nodeId),
        relative_path: relativePath,
        os_family: osFamily || undefined,
        os_version: osVersion || undefined,
      });
      setName("");
      setRelativePath(""); setOsFamily(""); setOsVersion("");
      await reload();
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  }

  async function remove(image: Image) {
    if (!window.confirm(`确认删除镜像 ${image.name}？将同时清理节点上的文件。`)) return;
    try {
      await api.deleteImage(image.id);
      await reload();
    } catch (err) {
      setError(describeError(err));
    }
  }

  function showEdit(image: Image) {
    setEditImage(image);
    setEditFamily(image.os_family || "");
    setEditVersion(image.os_version || "");
  }

  async function saveEdit() {
    if (!editImage) return;
    try {
      await api.request<Image>(`/images/${editImage.id}`, {
        method: "PATCH",
        body: JSON.stringify({ os_family: editFamily, os_version: editVersion }),
      });
      setEditImage(null);
      await reload();
    } catch (err) {
      setError(describeError(err));
    }
  }

  return (
    <>
      <div className="page-head">
        <h2>镜像</h2>
      </div>
      <ErrorBanner message={error} />
      <Card title="登记已有镜像（文件需已存在于节点镜像目录）">
        <form className="inline" onSubmit={submit}>
          <label>
            名称
            <input value={name} onChange={(e) => setName(e.target.value)} required />
          </label>
          <label>
            节点
            <select value={nodeId} onChange={(e) => setNodeId(e.target.value)}>
              {nodes.map((node) => (
                <option key={node.id} value={node.id}>
                  {node.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            相对路径
            <input value={relativePath} onChange={(e) => setRelativePath(e.target.value)} placeholder="ubuntu" />
          </label>
          <button className="action primary" type="submit" disabled={busy || !nodeId}>
            {busy ? "校验中…" : "导入"}
          </button>
        </form>
      </Card>
      <Card title={`共 ${images.length} 个镜像`}>
        {images.length === 0 ? (
          <Empty text="暂无镜像" />
        ) : (
          <table>
            <thead>
              <tr>
                <th>名称</th>
                <th>格式</th>
                <th>状态</th>
                <th>文件大小</th>
                <th>虚拟容量</th>
                <th>路径</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {images.map((image) => (
                <tr key={image.id}>
                  <td>{image.name}</td>
                  <td>{image.format}</td>
                  <td>
                    <StatusBadge status={image.status} />
                    {image.error_message ? <div className="muted">{image.error_message}</div> : null}
                  </td>
                  <td>{formatBytes(image.size_bytes)}</td>
                  <td>{formatBytes(image.virtual_size_bytes)}</td>
                  <td className="mono">{image.relative_path}</td>
                  <td>
                    <button className="action" onClick={() => showEdit(image)}>编辑</button>
                    <button className="action danger" onClick={() => void remove(image)}>删除</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
      {editImage ? (
        <Card title={`编辑镜像：${editImage.name}`}>
          <form className="inline" onSubmit={(e) => { e.preventDefault(); void saveEdit(); }}>
            <label>系统系列<input value={editFamily} onChange={(e) => setEditFamily(e.target.value)} placeholder="ubuntu" /></label>
            <label>系统版本<input value={editVersion} onChange={(e) => setEditVersion(e.target.value)} placeholder="24.04" /></label>
            <button className="action primary" type="submit">保存</button>
            <button className="action" type="button" onClick={() => setEditImage(null)}>取消</button>
          </form>
        </Card>
      ) : null}
    </>
  );
}
