# CloudVirt 统一命令入口
# 用法: make help

PYTHON      ?= python3
VENV        ?= .venv
BACKEND_DIR := apps/management
AGENT_DIR   := services/virt-node-agent
WEB_DIR     := frontend

.PHONY: help venv backend-install backend-check backend-test backend-migrate backend-run         agent-fmt agent-vet agent-test agent-build agent-run         web-install web-build lint precheck

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

web-install: ## 安装前端依赖
	cd $(WEB_DIR) && npm install

web-build: ## 构建前端产物（含类型检查）
	cd $(WEB_DIR) && npm run build

web-dev: ## 启动前端开发服务器（代理到 127.0.0.1:8000）
	cd $(WEB_DIR) && npm run dev

lint: ## 全量静态检查
	cd $(WEB_DIR) && npm run typecheck 2>/dev/null || true
	cd $(BACKEND_DIR) && $(CURDIR)/$(VENV)/bin/python -m ruff check .
	cd $(BACKEND_DIR) && $(CURDIR)/$(VENV)/bin/python -m ruff format --check .
	$(MAKE) agent-fmt agent-vet

precheck: ## 部署前环境检查
	bash scripts/precheck.sh
