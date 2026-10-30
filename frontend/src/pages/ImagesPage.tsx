import { useCallback, useEffect, useState } from "react";

import { api } from "../api";
import { BrowserUpload } from "../features/images/BrowserUpload";
import { allResources } from "../features/infrastructure/client";
import {
  ConfirmOperationModal,
  Drawer,
  TaskProgressDrawer,
} from "../components/ConsoleUI";
import {
  Card,
  Empty,
  ErrorBanner,
  StatusBadge,
  describeError,
  RowMenu,
  formatBytes,
  formatTimeFixed,
} from "../components/ui";
import { PageHeader } from "../components/ConsoleUI";
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
  const [purgeFile, setPurgeFile] = useState(false);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<{
    image: Image;
    purge: boolean;
  } | null>(null);
  const [verifyImage, setVerifyImage] = useState<Image | null>(null);
  const [verifyNode, setVerifyNode] = useState("");
  const [pendingCancel, setPendingCancel] = useState<Image | null>(null);
  const [editImage, setEditImage] = useState<Image | null>(null);
  const [editFamily, setEditFamily] = useState("");
  const [editVersion, setEditVersion] = useState("");
  const [editCloudInit,setEditCloudInit]=useState(false);

  const canImport = can(user, "images.add_image");
  const canDelete = can(user, "images.delete_image");

  const reload = useCallback(async () => {
    try {
      const [imageItems, nodeItems] = await Promise.all([
        allResources<Image>("/images"),
        allResources<Node>("/nodes"),
      ]);
      setImages(imageItems);
      setNodes(nodeItems);
      setNodeId(
        (current) =>
          current || String(nodeItems.find((n) => n.is_schedulable)?.id ?? ""),
      );
      setError(null);
    } catch (err) {
      setError(describeError(err));
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  useEffect(() => {
    if (!images.some((i) => ["VERIFYING", "UPLOADING"].includes(i.status)))
      return;
    const poll = () => {
      if (!document.hidden && !busy) void reload();
    };
    const timer = setInterval(poll, 15000);
    document.addEventListener("visibilitychange", poll);
    return () => {
      clearInterval(timer);
      document.removeEventListener("visibilitychange", poll);
    };
  }, [images, reload, busy]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const result = await api.importImage({
        name,
        node: Number(nodeId),
        relative_path: relativePath,
        os_family: osFamily || undefined,
        os_version: osVersion || undefined,
      });
      setNotice(`镜像 ${result.image.name} 已登记，后台正在检查节点文件。`);
      setTaskId(result.task_id);
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

  async function remove() {
    if (!pendingDelete || busy) return;
    const { image, purge } = pendingDelete;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await api.deleteImage(image.id, purge);
      setPendingDelete(null);
      setNotice(`镜像 ${image.name} 已删除`);
      await reload();
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  }

  function showEdit(image: Image) {
    setEditImage(image);
    setEditFamily(image.os_family || "");
    setEditVersion(image.os_version || "");
    setEditCloudInit(image.supports_cloud_init||false);
  }

  async function saveEdit(event: React.FormEvent) {
    event.preventDefault();
    if (!editImage) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await api.updateImage(editImage.id, {
        os_family: editFamily,
        os_version: editVersion,
        ...(user.console_scope==='admin'?{supports_cloud_init:editCloudInit}:{}),
      });
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
      <PageHeader
        title="镜像"
        description="管理可用于创建虚拟机的操作系统镜像，支持浏览器分片上传与校验"
      >
        <button className="action" onClick={() => void reload()}>
          刷新
        </button>
      </PageHeader>
      <ErrorBanner message={error} />
      {notice ? <div className="banner banner-info">{notice}</div> : null}
      {canImport ? (
        <details className="resource-import"><summary>上传镜像 <span>从浏览器分片上传到节点</span></summary><BrowserUpload
          nodes={nodes}
          onChanged={() => void reload()}
          onSubmitted={(id) => {
            setTaskId(id);
            setNotice(
              "文件已接收，后台正在检测镜像格式和 SHA-256；任务成功后才标记为可用。",
            );
          }}
        /></details>
      ) : null}
      {canImport ? (
        <details className="resource-import"><summary>登记节点已有镜像 <span>文件已存在时使用</span></summary><Card title="登记已有镜像（文件需已存在于节点镜像目录）">
          <form className="inline" onSubmit={submit}>
            <label>
              名称
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
              />
            </label>
            <label>
              节点
              <select
                value={nodeId}
                onChange={(e) => setNodeId(e.target.value)}
              >
                <option value="">请选择在线节点</option>
                {nodes
                  .filter((n) => n.is_schedulable)
                  .map((node) => (
                    <option key={node.id} value={node.id}>
                      {node.name}
                    </option>
                  ))}
              </select>
            </label>
            <label>
              相对路径
              <input
                required
                value={relativePath}
                onChange={(e) => setRelativePath(e.target.value)}
                placeholder="ubuntu.qcow2"
              />
            </label>
            <label>
              系统系列
              <input
                value={osFamily}
                onChange={(e) => setOsFamily(e.target.value)}
                placeholder="ubuntu"
              />
            </label>
            <label>
              系统版本
              <input
                value={osVersion}
                onChange={(e) => setOsVersion(e.target.value)}
                placeholder="24.04"
              />
            </label>
            <button
              className="action primary"
              type="submit"
              disabled={busy || !nodeId}
            >
              {busy ? "提交中…" : "登记并校验"}
            </button>
          </form>
          <p className="muted">
            此方式不会从浏览器传输文件。文件必须已位于所选节点的
            CLOUDVIRT_IMAGE_DIR 中，并允许 cloudvirt-agent
            用户读取。找不到本地文件时请使用上方浏览器上传。
          </p>
        </Card></details>
      ) : null}
      {editImage ? (
        <Card title={`编辑镜像：${editImage.name}`}>
          <form className="inline" onSubmit={saveEdit}>
            <label>
              系统系列
              <input
                value={editFamily}
                onChange={(e) => setEditFamily(e.target.value)}
                placeholder="ubuntu"
              />
            </label>
            <label>
              系统版本
              <input
                value={editVersion}
                onChange={(e) => setEditVersion(e.target.value)}
                placeholder="24.04"
              />
            </label>
            {user.console_scope==='admin'&&<label className="check"><input type="checkbox" checked={editCloudInit} onChange={e=>setEditCloudInit(e.target.checked)}/>已确认镜像支持 cloud-init</label>}
            <button className="action primary" type="submit" disabled={busy}>
              {busy ? "保存中…" : "保存"}
            </button>
            <button
              className="action"
              type="button"
              onClick={() => setEditImage(null)}
            >
              取消
            </button>
          </form>
        </Card>
      ) : null}
      <Card
        title={`共 ${images.length} 个镜像`}
        description={
          canDelete
            ? `删除时${purgeFile ? "将同时清理" : "默认保留"}节点文件，可在删除确认框中调整`
            : undefined
        }
      >
        {images.length === 0 ? (
          <Empty text="暂无镜像" />
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>名称 / 系统</th>
                  <th>所属节点</th>
                  <th>状态</th>
                  <th className="num">文件大小 / 虚拟容量</th>
                  <th>路径</th>
                  <th>导入时间</th>
                  <th className="col-actions">操作</th>
                </tr>
              </thead>
              <tbody>
                {images.map((image) => (
                  <tr key={image.id}>
                    <td>
                      <div className="cell-stack">
                        <strong
                          className="truncate cell-name"
                          title={image.name}
                        >
                          {image.name}
                        </strong>
                        <small className="muted">
                          {image.format.toUpperCase()} ·{" "}
                          {[image.os_family, image.os_version]
                            .filter(Boolean)
                            .join(" ") || "未标注系统"}
                        </small>
                      </div>
                    </td>
                    <td>
                      {image.node_name || (
                        <span className="cell-wrap warn-text">
                          旧记录未绑定，请重新校验
                        </span>
                      )}
                    </td>
                    <td>
                      <StatusBadge status={image.status} />
                      {image.error_message ? (
                        <div
                          className="muted truncate cell-error"
                          title={`${image.error_code}: ${image.error_message}`}
                        >
                          {image.error_code}: {image.error_message}
                        </div>
                      ) : null}
                    </td>
                    <td className="num">
                      <div className="cell-stack">
                        <span>
                          {image.size_bytes
                            ? formatBytes(image.size_bytes)
                            : "—"}
                        </span>
                        <small className="muted">
                          虚拟 {formatBytes(image.virtual_size_bytes)}
                        </small>
                      </div>
                    </td>
                    <td className="cell-path">
                      <span
                        className="mono truncate"
                        title={image.relative_path}
                      >
                        {image.relative_path}
                      </span>
                    </td>
                    <td>
                      <div
                        className="cell-stack time-text"
                        title={formatTimeFixed(image.created_at)}
                      >
                        <span>
                          {formatTimeFixed(image.created_at).slice(0, 10)}
                        </span>
                        <small className="muted">
                          {formatTimeFixed(image.created_at).slice(11)}
                        </small>
                      </div>
                    </td>
                    <td className="col-actions">
                      <div className="row-actions">
                        {canImport ? (
                          <button
                            className="action sm"
                            disabled={busy}
                            onClick={() => showEdit(image)}
                          >
                            编辑
                          </button>
                        ) : null}
                        {(canImport &&
                          !["UPLOADING", "VERIFYING", "DELETING"].includes(
                            image.status,
                          )) ||
                        (canImport &&
                          ["UPLOADING", "FAILED"].includes(image.status) &&
                          image.upload_id) ||
                        (canDelete &&
                          !["UPLOADING", "VERIFYING"].includes(
                            image.status,
                          )) ? (
                          <RowMenu disabled={busy}>
                            {canImport &&
                            !["UPLOADING", "VERIFYING", "DELETING"].includes(
                              image.status,
                            ) ? (
                              <button
                                disabled={busy}
                                onClick={() => {
                                  setError(null);
                                  setVerifyImage(image);
                                  setVerifyNode(
                                    image.node ? String(image.node) : "",
                                  );
                                }}
                              >
                                重新校验
                              </button>
                            ) : null}
                            {canImport &&
                            ["UPLOADING", "FAILED"].includes(image.status) &&
                            image.upload_id ? (
                              <button
                                className="danger-text"
                                disabled={busy}
                                onClick={() => {
                                  setError(null);
                                  setPendingCancel(image);
                                }}
                              >
                                {image.status === "UPLOADING"
                                  ? "取消上传"
                                  : "清理未发布分片"}
                              </button>
                            ) : null}
                            {canDelete &&
                            !["UPLOADING", "VERIFYING"].includes(
                              image.status,
                            ) ? (
                              <button
                                className="danger-text"
                                disabled={busy}
                                onClick={() => {
                                  setError(null);
                                  setPendingDelete({ image, purge: purgeFile });
                                }}
                              >
                                删除
                              </button>
                            ) : null}
                          </RowMenu>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      {verifyImage ? (
        <Drawer
          title={`重新校验：${verifyImage.name}`}
          onClose={() => {
            if (!busy) setVerifyImage(null);
          }}
          footer={
            <>
              <button
                className="action"
                type="button"
                disabled={busy}
                onClick={() => setVerifyImage(null)}
              >
                取消
              </button>
              <button
                className="action primary"
                type="submit"
                form="image-verify-form"
                disabled={busy || !verifyNode}
              >
                提交校验任务
              </button>
            </>
          }
        >
          <form
            id="image-verify-form"
            className="infra-form"
            onSubmit={async (e) => {
              e.preventDefault();
              setBusy(true);
              setError(null);
              try {
                const result = await api.request<{ task_id: string }>(
                  `/images/${verifyImage.id}/verify`,
                  {
                    method: "POST",
                    body: JSON.stringify({ node: Number(verifyNode) }),
                  },
                );
                setVerifyImage(null);
                setTaskId(result.task_id);
                await reload();
              } catch (e) {
                setError(describeError(e));
              } finally {
                setBusy(false);
              }
            }}
          >
            <ErrorBanner message={error} />
            <div className="callout callout-muted">
              相对路径：
              <span className="mono">{verifyImage.relative_path}</span>
              。选择文件实际所在节点；已绑定的镜像不能改为其他节点。
            </div>
            <label>
              所属节点
              <select
                required
                disabled={!!verifyImage.node || busy}
                value={verifyNode}
                onChange={(e) => setVerifyNode(e.target.value)}
              >
                <option value="">请选择实际节点</option>
                {nodes.map((n) => (
                  <option key={n.id} value={n.id}>
                    {n.name}
                  </option>
                ))}
              </select>
            </label>
          </form>
        </Drawer>
      ) : null}
      {pendingDelete ? (
        <ConfirmOperationModal
          target={`${pendingDelete.image.name} / ${pendingDelete.image.node_name || "未绑定节点"} / ${pendingDelete.image.relative_path}`}
          operation="删除镜像"
          description={
            pendingDelete.purge
              ? "将删除镜像记录及所属节点上的文件，操作不可逆；被虚拟机引用时禁止删除。节点必须开启破坏性操作开关。"
              : "将移除镜像记录，保留节点文件。被虚拟机引用时禁止删除。"
          }
          busy={busy}
          error={error}
          onCancel={() => setPendingDelete(null)}
          onConfirm={() => void remove()}
        >
          {canDelete ? (
            <label className="check">
              <input
                type="checkbox"
                checked={pendingDelete.purge}
                disabled={busy}
                onChange={(e) => {
                  setPurgeFile(e.target.checked);
                  setPendingDelete({
                    ...pendingDelete,
                    purge: e.target.checked,
                  });
                }}
              />
              删除时清理节点文件
            </label>
          ) : null}
        </ConfirmOperationModal>
      ) : null}
      {pendingCancel ? (
        <ConfirmOperationModal
          target={pendingCancel.name}
          operation="取消镜像上传"
          description="仅清理尚未发布的临时分片，并移除上传记录。不能取消已进入校验的文件。"
          busy={busy}
          error={error}
          onCancel={() => setPendingCancel(null)}
          onConfirm={async () => {
            setBusy(true);
            setError(null);
            try {
              await api.request(`/images/uploads/${pendingCancel.upload_id}`, {
                method: "DELETE",
              });
              setPendingCancel(null);
              await reload();
            } catch (e) {
              setError(describeError(e));
            } finally {
              setBusy(false);
            }
          }}
        />
      ) : null}
      {taskId ? (
        <TaskProgressDrawer
          id={taskId}
          onClose={() => {
            setTaskId(null);
            void reload();
          }}
        />
      ) : null}
    </>
  );
}
