// Package auth 提供节点 Agent 的共享令牌校验。
package auth

import (
	"crypto/subtle"
	"net/http"
	"strings"
)

// TokenMiddleware 校验 Bearer 令牌，未通过时返回 401。
//
// 使用常量时间比较，避免通过响应耗时猜测令牌内容。
func TokenMiddleware(token string, next http.Handler) http.Handler {
	expected := []byte(token)
	return http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		provided := []byte(extractToken(request.Header.Get("Authorization")))
		if len(expected) == 0 || subtle.ConstantTimeCompare(expected, provided) != 1 {
			http.Error(writer, `{"code":"UNAUTHORIZED","message":"令牌无效或缺失"}`, http.StatusUnauthorized)
			return
		}
		next.ServeHTTP(writer, request)
	})
}

// extractToken 从 Authorization 头提取令牌，支持 Bearer 前缀。
func extractToken(header string) string {
	value := strings.TrimSpace(header)
	if value == "" {
		return ""
	}
	if prefix := "Bearer "; strings.HasPrefix(value, prefix) {
		return strings.TrimSpace(strings.TrimPrefix(value, prefix))
	}
	return value
}
