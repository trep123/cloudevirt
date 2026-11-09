# CloudVirt 统一命令入口
# 用法: make help

PYTHON      ?= python3
VENV        ?= .venv
GO          ?= go
BACKEND_DIR := apps/management
AGENT_DIR   := services/virt-node-agent
WEB_DIR     := frontend
# Offline Go builds must not reach the network or auto-download a toolchain;
# they compile strictly from the committed vendor tree.
GO_OFFLINE_ENV := CGO_ENABLED=0 GOTOOLCHAIN=local GOPROXY=off GOSUMDB=off GOFLAGS=-mod=vendor

.PHONY: help venv backend-install backend-check backend-test backend-migrate backend-run         agent-fmt agent-vet agent-test agent-build agent-run agent-vendor-check agent-build-offline agent-test-offline go-preflight         web-install web-build web-dev serve nginx-reload lint precheck

help: ## 显示可用命令
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-18s %s\n", $$1, $$2}'

venv: ## 创建后端虚拟环境
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/python -m pip install --upgrade pip

backend-install: ## 安装后端开发依赖
	$(VENV)/bin/python -m pip install -r $(BACKEND_DIR)/requirements/dev.txt

backend-check: ## Django 配置检查
	cd $(BACKEND_DIR) && $(CURDIR)/$(VENV)/bin/python manage.py check

backend-test: ## 后端测试
	cd $(BACKEND_DIR) && $(CURDIR)/$(VENV)/bin/python manage.py test

backend-migrate: ## 执行数据库迁移
	cd $(BACKEND_DIR) && $(CURDIR)/$(VENV)/bin/python manage.py migrate

backend-run: ## 启动后端开发服务
	cd $(BACKEND_DIR) && $(CURDIR)/$(VENV)/bin/python manage.py runserver 127.0.0.1:8000

agent-fmt: ## 检查 Go 代码格式
	cd $(AGENT_DIR) && gofmt -l .

agent-vet: ## Go 静态检查
	cd $(AGENT_DIR) && go vet ./...

agent-test: ## Go 单元测试
	cd $(AGENT_DIR) && go test ./...

agent-build: ## 构建 Agent 二进制
	cd $(AGENT_DIR) && go build -o bin/virt-node-agent ./cmd/virt-node-agent

agent-run: ## 启动节点 Agent（需先配置环境变量）
	cd $(AGENT_DIR) && go run ./cmd/virt-node-agent

agent-vendor-check: ## 校验离线构建所需的 vendor 目录存在
	@test -f $(AGENT_DIR)/vendor/modules.txt || { \
		echo '缺少 vendor 目录，请先执行: cd $(AGENT_DIR) && $(GO) mod vendor'; exit 1; }

agent-build-offline: agent-vendor-check ## 使用 vendor 离线构建 Agent 二进制
	cd $(AGENT_DIR) && $(GO_OFFLINE_ENV) $(GO) build -trimpath -o bin/virt-node-agent ./cmd/virt-node-agent

agent-test-offline: agent-vendor-check ## 使用 vendor 离线运行 Agent 测试
	cd $(AGENT_DIR) && $(GO_OFFLINE_ENV) $(GO) test ./...

go-preflight: ## 校验本地 Go 工具链满足 go.mod 版本要求
	@cd $(AGENT_DIR) && $(GO) version && GOTOOLCHAIN=local $(GO) list -m >/dev/null && \
		echo 'Go 工具链版本满足 go.mod 要求'

web-install: ## 安装前端依赖
	cd $(WEB_DIR) && npm install

web-build: ## 构建前端产物（含类型检查）
	cd $(WEB_DIR) && npm run build

web-dev: ## 启动前端开发服务器（代理到 127.0.0.1:8000）
	cd $(WEB_DIR) && npm run dev

serve: ## 一键构建前端并启动后端/Agent/nginx（需 CLOUDVIRT_AGENT_TOKEN）
	CLOUDVIRT_AGENT_TOKEN=${CLOUDVIRT_AGENT_TOKEN:-} bash scripts/serve_local.sh

nginx-reload: ## 重载 nginx 站点配置
	nginx -t && nginx -s reload

lint: ## 全量静态检查
	cd $(WEB_DIR) && npm run typecheck
	cd $(BACKEND_DIR) && $(CURDIR)/$(VENV)/bin/python -m ruff check .
	cd $(BACKEND_DIR) && $(CURDIR)/$(VENV)/bin/python -m ruff format --check .
	$(MAKE) agent-fmt agent-vet

precheck: ## 部署前环境检查
	bash scripts/precheck.sh
