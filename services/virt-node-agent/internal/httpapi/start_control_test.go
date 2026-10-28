package httpapi

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

type autostartOperator struct {
	fakeOperator
	auto  bool
	calls int
}

func (f *autostartOperator) SetDomainAutostart(ctx context.Context, name string, enabled bool) error {
	f.auto = enabled
	f.calls++
	return nil
}
func TestCreateCanRemainStoppedWithHostAutostart(t *testing.T) {
	operator := &autostartOperator{fakeOperator: fakeOperator{state: "SHUTOFF", dumpXML: fakeDump()}}
	deps := testDependencies()
	deps.DiskDir = t.TempDir()
	deps.Virtualizer = operator
	body := strings.TrimSuffix(createPayload(t), "}") + `,"start_after_create":false,"autostart":true}`
	request := httptest.NewRequest(http.MethodPost, "/api/v1/domains", strings.NewReader(body))
	request.Header.Set("Authorization", "Bearer "+deps.Token)
	recorder := httptest.NewRecorder()
	NewRouter(deps).ServeHTTP(recorder, request)
	if recorder.Code != http.StatusCreated {
		t.Fatal(recorder.Code, recorder.Body.String())
	}
	if operator.startCall != 0 || operator.calls != 1 || !operator.auto {
		t.Fatal("startup flags were conflated")
	}
}
