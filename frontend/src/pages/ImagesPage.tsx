import { useCallback, useEffect, useState } from "react";

import { api } from "../api";
import { Card, Empty, ErrorBanner, StatusBadge, describeError, formatBytes, formatTime } from "../components/ui";
import { can } from "../permissions";
import type { CurrentUser, Image, Node } from "../types";

export function ImagesPage({ user }: { user: CurrentUser }) {
  const [images, setImages] = useState<Image[]>([]);
  const [nodes, setNodes] = useState<Node[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [nodeId, setNodeId] = useState("");
  const [relativePath, setRelativePath] = useState("");
  const [osFamily, setOsFamily] = useState("");
  const [osVersion, setOsVersion] = useState("");
  const [busy, setBusy] = useState(false);
  const [purgeFile, setPurgeFile] = useState(true);
  const [editImage, setEditImage] = useState<Image | null>(null);
  const [editFamily, setEditFamily] = useState("");
  const [editVersion, setEditVersion] = useState("");

  const canImport = can(user, "images.add_image");
  const canDelete = can(user, "images.delete_image");

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
    setNotice(null);
    try {
      const image = await api.importImage({
        name,
        node: Number(nodeId),
        relative_path: relativePath,
        os_family: osFamily || undefined,
        os_version: osVersion || undefined,
      });
      setNotice(image.is_ready ? `镜像 ${image.name} 已导入` : `镜像 ${image.name} 已登记，当前状态 ${image.status}`);
      setName("");
      setRelativePath("");
      setOsFamily("");
      setOsVersion("");
      await reload();
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  }

  async function remove(image: Image) {
    const suffix = purgeFile ? "将同时清理节点上的文件。" : "保留节点上的文件。";
    if (!window.confirm(`确认删除镜像 ${image.name}？${suffix}`)) return;
    setError(null);
    setNotice(null);
    try {
      await api.deleteImage(image.id, purgeFile);
      setNotice(`镜像 ${image.name} 已删除`);
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

  async function saveEdit(event: React.FormEvent) {
    event.preventDefault();
    if (!editImage) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await api.updateImage(editImage.id, { os_family: editFamily, os_version: editVersion });
      setNotice(`镜像 ${editImage.name} 元数据已更新`);
      setEditImage(null);
      await reload();
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="page-head">
        <h2>镜像</h2>
        <button className="action" onClick={() => void reload()}>刷新</button>
      </div>
      <ErrorBanner message={error} />
      {notice ? <div className="banner banner-info">{notice}</div> : null}
      {canImport ? (
        <Card title="登记已有镜像（文件需已存在于节点镜像目录）">
          <form className="inline" onSubmit={submit}>
            <label>名称<input value={name} onChange={(e) => setName(e.target.value)} required /></label>
            <label>节点
              <select value={nodeId} onChange={(e) => setNodeId(e.target.value)}>
                {nodes.map((node) => <option key={node.id} value={node.id}>{node.name}</option>)}
              </select>
            </label>
            <label>相对路径<input value={relativePath} onChange={(e) => setRelativePath(e.target.value)} placeholder="ubuntu.qcow2" /></label>
            <label>系统系列<input value={osFamily} onChange={(e) => setOsFamily(e.target.value)} placeholder="ubuntu" /></label>
            <label>系统版本<input value={osVersion} onChange={(e) => setOsVersion(e.target.value)} placeholder="24.04" /></label>
            <button className="action primary" type="submit" disabled={busy || !nodeId}>{busy ? "校验中…" : "导入"}</button>
          </form>
        </Card>
      ) : null}
      {editImage ? (
        <Card title={`编辑镜像：${editImage.name}`}>
          <form className="inline" onSubmit={saveEdit}>
            <label>系统系列<input value={editFamily} onChange={(e) => setEditFamily(e.target.value)} placeholder="ubuntu" /></label>
            <label>系统版本<input value={editVersion} onChange={(e) => setEditVersion(e.target.value)} placeholder="24.04" /></label>
            <button className="action primary" type="submit" disabled={busy}>{busy ? "保存中…" : "保存"}</button>
            <button className="action" type="button" onClick={() => setEditImage(null)}>取消</button>
          </form>
        </Card>
      ) : null}
      <Card
        title={`共 ${images.length} 个镜像`}
        extra={canDelete ? (
          <label className="check"><input type="checkbox" checked={purgeFile} onChange={(e) => setPurgeFile(e.target.checked)} /> 删除时清理节点文件</label>
        ) : null}
      >
        {images.length === 0 ? <Empty text="暂无镜像" /> : (
          <table>
            <thead>
              <tr>
                <th>名称</th>
                <th>格式</th>
                <th>状态</th>
                <th>系统</th>
                <th>文件大小</th>
                <th>虚拟容量</th>
                <th>路径</th>
                <th>导入时间</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {images.map((image) => (
                <tr key={image.id}>
                  <td><strong>{image.name}</strong></td>
                  <td>{image.format}</td>
                  <td>
                    <StatusBadge status={image.status} />
                    {image.error_message ? <div className="muted">{image.error_code}: {image.error_message}</div> : null}
                  </td>
                  <td>{[image.os_family, image.os_version].filter(Boolean).join(" ") || "-"}</td>
                  <td>{formatBytes(image.size_bytes)}</td>
                  <td>{formatBytes(image.virtual_size_bytes)}</td>
                  <td className="mono">{image.relative_path}</td>
                  <td>{formatTime(image.created_at)}</td>
                  <td className="actions">
                    {canImport ? <button className="action" onClick={() => showEdit(image)}>编辑</button> : null}
                    {canDelete ? <button className="action danger" onClick={() => void remove(image)}>删除</button> : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </>
  );
}
