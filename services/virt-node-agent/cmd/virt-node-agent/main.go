// Command virt-node-agent 启动 CloudVirt 节点 Agent。
//
// Agent 是宿主机上的高权限组件，只暴露受限 API：
//   - GET /health：进程存活检查（免认证）；
//   - GET /api/v1/node/resources：资源采集；
//   - GET /api/v1/domains：域列表与状态。
//
// 配置全部来自环境变量，启动时一次性加载并校验，校验失败立即退出。
package main

import (
	"context"
	"errors"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/config"
	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/hostbridge"
	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/httpapi"
	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/libvirt"
)

func main() {
	if len(os.Args) == 2 && os.Args[1] == "--network-service" {
		if err := hostbridge.Serve(); err != nil {
			slog.Error("网络服务退出", "error", err)
			os.Exit(1)
		}
		return
	}
	logger := slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelInfo}))
	slog.SetDefault(logger)

	cfg, err := config.Load()
	if err != nil {
		slog.Error("配置加载失败", "error", err)
		os.Exit(1)
	}

	client := libvirt.NewClient(time.Duration(cfg.MaxRequestSeconds) * time.Second)
	client.LeaseFile = cfg.DHCPLeaseFile
	handler := httpapi.NewRouter(httpapi.Dependencies{
		Version:          cfg.Version,
		Token:            cfg.Token,
		StoragePaths:     []string{cfg.ImageDir, cfg.DiskDir},
		ImageDir:         cfg.ImageDir,
		DiskDir:          cfg.DiskDir,
		StorageRoots:     cfg.StorageRoots,
		AllowDestructive: cfg.AllowDestructive,
		Domains:          client,
		Virtualizer:      client,
		Networks:         client,
		Logger:           logger,
	})

	server := &http.Server{
		Addr:              cfg.Listen,
		Handler:           handler,
		ReadHeaderTimeout: 10 * time.Second,
		ReadTimeout:       time.Duration(cfg.MaxRequestSeconds) * time.Second,
		WriteTimeout:      time.Duration(cfg.MaxRequestSeconds) * time.Second,
	}

	shutdown := make(chan os.Signal, 1)
	signal.Notify(shutdown, syscall.SIGINT, syscall.SIGTERM)

	go func() {
		slog.Info("节点 Agent 启动", "listen", cfg.Listen, "version", cfg.Version)
		if err := server.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			slog.Error("服务异常退出", "error", err)
			os.Exit(1)
		}
	}()

	<-shutdown
	slog.Info("收到退出信号，开始优雅关闭")

	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()

	if err := server.Shutdown(ctx); err != nil {
		slog.Error("优雅关闭失败", "error", err)
		os.Exit(1)
	}
	slog.Info("节点 Agent 已停止")
}
