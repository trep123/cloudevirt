// Package apierr 定义节点 Agent 的稳定错误码，与管理后端保持一致。
package apierr

// Code 是稳定错误码，禁止直接把内部错误文本返回给调用方。
type Code string

// 错误码取值。
const (
	CodeUnauthorized         Code = "UNAUTHORIZED"
	CodeInvalidArgument      Code = "INVALID_ARGUMENT"
	CodeNotFound             Code = "NOT_FOUND"
	CodeConflict             Code = "CONFLICT"
	CodeInsufficientResource Code = "INSUFFICIENT_RESOURCE"
	CodeLibvirtUnavailable   Code = "LIBVIRT_UNAVAILABLE"
	CodeCommandTimeout       Code = "COMMAND_TIMEOUT"
	CodeOperationFailed      Code = "OPERATION_FAILED"
	CodeInternalError        Code = "INTERNAL_ERROR"
)

// Error 携带错误码与脱敏后的信息，便于跨层传递。
type Error struct {
	Code    Code
	Message string
	Cause   error
}

// New 构造一个带错误码的错误。
func New(code Code, message string, cause error) *Error {
	return &Error{Code: code, Message: message, Cause: cause}
}

func (e *Error) Error() string {
	if e.Cause != nil {
		return e.Message + ": " + e.Cause.Error()
	}
	return e.Message
}

// Unwrap 返回底层错误，支持 errors.Is / errors.As。
func (e *Error) Unwrap() error {
	return e.Cause
}
