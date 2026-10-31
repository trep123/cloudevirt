package libvirt

import (
	"encoding/xml"
	"fmt"
	"strings"
)

// replaceCDROM changes only a named optical device and preserves every disk.
func replaceCDROM(content, target, path string, remove bool) (string, error) {
	if len(target) != 3 || !strings.HasPrefix(target, "sd") || target[2] < 'a' || target[2] > 'z' { return "", fmt.Errorf("光驱设备号无效") }
	parts, err := xmlParts(content, "domain/devices", "disk")
	if err != nil { return "", err }
	var found *xmlPart
	for i := range parts {
		var d struct { Device string `xml:"device,attr"`; Target struct { Dev string `xml:"dev,attr"` } `xml:"target"` }
		if err := xml.Unmarshal([]byte(parts[i].raw), &d); err != nil { return "", err }
		if d.Target.Dev != target { continue }
		if d.Device != "cdrom" { return "", fmt.Errorf("设备号已被磁盘占用，禁止替换") }
		if found != nil { return "", fmt.Errorf("光驱设备号重复") }
		found = &parts[i]
	}
	if remove {
		if found == nil { return content, nil }
		return content[:found.start] + content[found.end:], nil
	}
	if path == "" { return "", fmt.Errorf("ISO 路径不能为空") }
	var escaped strings.Builder
	if err := xml.EscapeText(&escaped, []byte(path)); err != nil { return "", err }
	raw := fmt.Sprintf(`<disk type="file" device="cdrom"><driver name="qemu" type="raw"/><source file="%s"/><target dev="%s" bus="sata"/><readonly/></disk>`, escaped.String(), target)
	if found != nil { return content[:found.start] + raw + content[found.end:], nil }
	if strings.Count(content, "</devices>") != 1 { return "", fmt.Errorf("无法唯一定位设备列表") }
	return strings.Replace(content, "</devices>", raw+"</devices>", 1), nil
}

func opticalBootOrder(content string, installed bool) (string, error) {
	parts, err := xmlParts(content, "domain/os", "boot")
	if err != nil { return "", err }
	for i := len(parts)-1; i >= 0; i-- { content = content[:parts[i].start] + content[parts[i].end:] }
	if strings.Contains(content, "<boot order=") { return "", fmt.Errorf("存在设备级启动顺序，请先人工核对") }
	if strings.Count(content, "</os>") != 1 { return "", fmt.Errorf("无法唯一定位操作系统配置") }
	boot := `<boot dev="hd"/>`
	if !installed { boot = `<boot dev="cdrom"/>` + boot }
	return strings.Replace(content, "</os>", boot+"</os>", 1), nil
}
