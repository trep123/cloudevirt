package httpapi

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"net/http"
	"regexp"
)

// RequestIDHeader 是请求与响应使用的链路追踪头。
const RequestIDHeader = "X-Request-ID"

var requestIDPattern = regexp.MustCompile(`^[A-Za-z0-9_-]{8,64}$`)

type requestIDKey struct{}

// RequestIDMiddleware 为请求生成或复用 request_id。
func RequestIDMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		requestID := resolveRequestID(request.Header.Get(RequestIDHeader))
		writer.Header().Set(RequestIDHeader, requestID)
		ctx := context.WithValue(request.Context(), requestIDKey{}, requestID)
		next.ServeHTTP(writer, request.WithContext(ctx))
	})
}

// RequestIDFromContext 取出上下文中的 request_id。
func RequestIDFromContext(ctx context.Context) string {
	value, _ := ctx.Value(requestIDKey{}).(string)
	return value
}

// resolveRequestID 复用合法入参，否则生成新的，避免回显任意输入。
func resolveRequestID(inbound string) string {
	if requestIDPattern.MatchString(inbound) {
		return inbound
	}
	return newRequestID()
}

// newRequestID 生成 32 位十六进制的 request_id。
func newRequestID() string {
	buffer := make([]byte, 16)
	if _, err := rand.Read(buffer); err != nil {
		return "unknown-request-id"
	}
	return hex.EncodeToString(buffer)
}
