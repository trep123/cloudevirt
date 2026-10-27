package domainxml

import (
	"strings"
	"testing"
)

func validSpec() Spec {
	return Spec{
		Name:      "cv-abc12345",
		UUID:      "0f6f2b1e-1111-4a22-9f33-000000000001",
		VCPU:      2,
		MemoryMiB: 2048,
		DiskPath:    "/var/lib/cloudvirt/disks/cv-abc12345.qcow2",
		Network:     "default",
		VNCPassword: "abcd1234",
	}
}

// TestBuildAndValidate 校验生成的 XML 结构完整且可解析。
func TestBuildAndValidate(t *testing.T) {
	content, err := Build(validSpec())
	if err != nil {
		t.Fatalf("生成失败: %v", err)
	}
	for _, fragment := range []string{
		`<domain type="kvm">`,
		"<name>cv-abc12345</name>",
		"<vcpu>2</vcpu>",
		`<memory unit="MiB">2048</memory>`,
		`<target dev="vda" bus="virtio">`,
		`<graphics type="vnc"`,
		`passwd="abcd1234"`,
	} {
		if !strings.Contains(content, fragment) {
			t.Errorf("XML 缺少片段 %q:\n%s", fragment, content)
		}
	}
	if err := Validate(content); err != nil {
		t.Errorf("校验不应失败: %v", err)
	}
}

// TestBuildEscapesSpecialCharacters 校验名称/路径中的特殊字符被转义而不是注入。
func TestBuildEscapesSpecialCharacters(t *testing.T) {
	spec := validSpec()
	spec.Name = "cv-test"
	spec.DiskPath = `/var/lib/cloudvirt/disks/a&b<c>.qcow2`

	content, err := Build(spec)
	if err != nil {
		t.Fatalf("生成失败: %v", err)
	}
	if strings.Contains(content, "a&b<c>") {
		t.Error("特殊字符未被转义")
	}
	if !strings.Contains(content, "&amp;") {
		t.Errorf("应包含转义后的字符:\n%s", content)
	}
}

// TestValidateSpecRejectsInvalidInput 校验非法输入被拒绝。
func TestValidateSpecRejectsInvalidInput(t *testing.T) {
	cases := map[string]Spec{
		"EmptyName":  func() Spec { s := validSpec(); s.Name = ""; return s }(),
		"BadName":    func() Spec { s := validSpec(); s.Name = "bad name!"; return s }(),
		"BadUUID":    func() Spec { s := validSpec(); s.UUID = "not-a-uuid"; return s }(),
		"ZeroVCPU":   func() Spec { s := validSpec(); s.VCPU = 0; return s }(),
		"HugeMemory": func() Spec { s := validSpec(); s.MemoryMiB = 99999999; return s }(),
		"EmptyDisk":  func() Spec { s := validSpec(); s.DiskPath = ""; return s }(),
		"BadNetwork": func() Spec { s := validSpec(); s.Network = "a/b"; return s }(),
	}
	for name, spec := range cases {
		t.Run(name, func(t *testing.T) {
			if err := ValidateSpec(spec); err == nil {
				t.Error("应返回错误")
			}
		})
	}
}

// TestValidateRejectsMalformedXML 校验残缺 XML 被拒绝。
func TestValidateRejectsMalformedXML(t *testing.T) {
	if err := Validate("<domain><name>only-name</name></domain>"); err == nil {
		t.Error("缺少必要字段应返回错误")
	}
	if err := Validate("not xml at all"); err == nil {
		t.Error("非 XML 应返回错误")
	}
}
