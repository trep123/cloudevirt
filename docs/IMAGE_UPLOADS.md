# 镜像故障修复与浏览器上传

截图中的 OPERATION_FAILED 只表示旧后端丢弃了 Agent 的具体错误，不能单凭截图认定是文件缺失、权限还是认证故障。本次修复错误传递，并增加浏览器到节点的分片上传通道。

## 操作方式

镜像页面提供两种独立操作：

1. **从浏览器上传**：选择 qcow2、raw、img 或 ISO 文件、镜像名称及目标节点。浏览器按 8 MiB 分片发送，展示发送进度和节点已确认的字节数。完整接收后提交后台任务，由节点检测格式、文件大小和 SHA-256；任务成功才标记为 READY。
2. **登记已有镜像**：只登记节点镜像目录中已经存在的文件，不传输浏览器文件。登记也改为后台校验，立即返回任务 ID。

默认上传上限为 16 GiB，使用管理端 `IMAGE_UPLOAD_MAX_BYTES` 配置，最大不超过 Agent 硬上限 64 GiB。每个账号最多保留 3 个未完成上传；节点在每个分片写入前检查实际可用空间并保留 64 MiB 余量，不承诺预留后续所有分片空间。

同一页面可以暂停、查询节点进度并继续；连接中断或分片响应丢失后先查询节点的已接收偏移，避免重复追加。暂停不会删除已接收分片。刷新或离开页面后浏览器 File 对象会丢失；当前界面不跨刷新恢复文件，未完成会话可在镜像列表中取消，再重新上传。

取消只清理该上传私有的未发布临时文件。文件发布后必须走镜像删除流程，并受节点破坏性开关约束。上传临时文件不会自动过期清理，避免误删仍需继续的上传；请从镜像列表取消不再需要的会话。失败的未发布会话也可使用“清理未发布分片”。

## 修复内容

- 保留 Agent 对外提供的 NOT_FOUND、CONFLICT、INVALID_ARGUMENT 等具体错误及 Agent request_id；不会透传代理 HTML 或堆栈。Agent 的 401/403 映射为节点认证失败，不使浏览器用户会话失效。
- 镜像增加所属节点。上传、登记、重新校验和文件删除使用实际绑定节点；不再选取“第一个在线节点”删除文件。
- 旧记录不猜测归属。对未绑定节点的旧镜像，点击“重新校验”并明确选择文件实际所在节点；校验完成后保留绑定。无法确认归属时可取消“删除时清理节点文件”，只移除未引用的记录。
- 缺失文件、不可读目录、不可读文件、空文件、缺少 qemu-img 分别返回可理解的错误。ISO9660 介质按 ISO 识别；拒绝依赖外部 backing/data 文件的镜像。
- SHA-256 按块读取，不将整个镜像读入内存。管理端 worker/Agent 校验通道最长默认 30 分钟；`IMAGE_INSPECT_TIMEOUT_SECONDS` 可设置管理端超时，Agent 上限仍为 30 分钟。
- 分片接口按权限、会话归属、节点 ACL、总大小、偏移和每片 8 MiB 强制校验。浏览器不会拿到节点令牌，也不能指定宿主机绝对路径。
- 上传文件名由 UUID 生成，原始文件名仅作元数据。重复分片必须与已保存数据一致；完整文件通过原子硬链接发布，不覆盖已有文件。未完成文件不进入可用镜像列表。
- 默认删除只移除记录；勾选文件清理时明确确认节点和路径。引用中的镜像和仍在校验的镜像不能删除。

## 新接口

所有接口位于 `/api/v1/`，使用现有 Session、CSRF 和镜像导入权限；上传会话仅创建者与管理员可访问，节点 ACL 仍必须通过。

| 方法与路径 | 用途 |
| --- | --- |
| `GET images/uploads` | 上传上限及分片大小 |
| `POST images/uploads` | 创建会话；客户端 UUID 作为重复提交标识 |
| `GET images/uploads/{uuid}` | 节点实际已接收进度 |
| `PUT images/uploads/{uuid}/chunk?offset=...` | 原始二进制分片，Content-Type 为 application/octet-stream |
| `POST images/uploads/{uuid}/complete` | 完整接收后入队校验；重复请求复用原任务 |
| `DELETE images/uploads/{uuid}` | 清理未发布分片，取消上传记录 |
| `POST images/{id}/verify` | 重新校验，旧记录须提供实际 node ID |

`POST images` 的成功响应现在是 202：`{"image": {...}, "task_id": "...", "status": "PENDING"}`，不会假装同步完成。已有外部客户端需要适配此响应。

## 升级与现场排查

更新 **master** 源码，沿用原部署参数重跑 install.sh。必须同时更新管理端、worker、前端及节点 Agent，并执行 images/0002 迁移。安装器会完成这些步骤，不能只替换前端静态文件。安装器无本地源码时默认拉取 master。

浏览器上传无需手工复制节点文件；由 Agent 自身写入镜像目录并设置可用权限。已有文件登记失败时，在实际节点上核对配置与权限（示例路径为默认安装目录）：

```sh
sudo grep '^CLOUDVIRT_IMAGE_DIR=' /etc/cloudvirt/agent.env
sudo -u cloudvirt-agent test -r /var/lib/libvirt/images/cloudvirt/images/rocky10.qcow2
sudo -u cloudvirt-agent qemu-img info --output=json /var/lib/libvirt/images/cloudvirt/images/rocky10.qcow2
sudo journalctl -u cloudvirt-agent -u cloudvirt-worker -u cloudvirt-management -n 100
```

文件必须位于 Agent 实际配置的镜像目录中，路径输入相对此目录；Agent 账号需要上级目录的遍历权限及文件读权限。安装 qemu-img 使用 Ubuntu 的 qemu-utils 包。不要通过开放整个宿主机目录权限来规避边界检查。

清理已发布的文件需要 `CLOUDVIRT_ALLOW_DESTRUCTIVE=true`；未启用时可只移除镜像记录并保留文件。

## 验证范围

前端类型/生产构建、修改 Python 文件的 Ruff 静态检查、Bash 语法和 Linux/amd64 Agent 编译用于本次验证。
补充了分片重放、越界和覆盖拒绝、会话越权、节点 ACL、任务提交、取消、所属节点及错误保留测试代码。
当前环境未运行这些测试，也未连接用户的 Ubuntu 实例执行上传、迁移或 qemu-img 验收。

实现参考：[QEMU qemu-img 文档](https://www.qemu.org/docs/master/tools/qemu-img.html)、[Django 流式请求 API](https://docs.djangoproject.com/en/6.0/ref/request-response/#django.http.HttpRequest.read)。
