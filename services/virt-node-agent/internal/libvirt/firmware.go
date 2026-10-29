package libvirt

import (
	"encoding/xml"
	"fmt"
	"os"
	"regexp"
	"strings"
)

type firmwareChild struct {
	XMLName xml.Name
	Attrs   []xml.Attr `xml:",any,attr"`
	Inner   string     `xml:",innerxml"`
}
type firmwareOS struct {
	XMLName  xml.Name
	Attrs    []xml.Attr      `xml:",any,attr"`
	Children []firmwareChild `xml:",any"`
}

var osElement = regexp.MustCompile(`(?s)<os(?:\s[^>]*)?>.*?</os>`)

func normalizeFirmware(content string) (string, error) {
	return normalizeFirmwareWith(content, func(path string) bool { info, err := os.Stat(path); return err == nil && info.Mode().IsRegular() })
}
func normalizeFirmwareWith(content string, exists func(string) bool) (string, error) {
	if strings.Contains(content, "<launchSecurity") {
		return content, nil
	}
	location := osElement.FindStringIndex(content)
	if location == nil {
		return content, nil
	}
	var config firmwareOS
	if err := xml.Unmarshal([]byte(content[location[0]:location[1]]), &config); err != nil {
		return "", err
	}
	automatic := false
	for _, attr := range config.Attrs {
		if attr.Name.Local == "firmware" && attr.Value == "efi" {
			automatic = true
		}
	}
	if !automatic {
		return content, nil
	}
	secure := false
	loader := ""
	nvram := false
	for _, child := range config.Children {
		switch child.XMLName.Local {
		case "loader":
			loader = strings.TrimSpace(child.Inner)
		case "nvram":
			nvram = true
		case "firmware":
			var features struct {
				Items []struct {
					Name    string `xml:"name,attr"`
					Enabled string `xml:"enabled,attr"`
				} `xml:"feature"`
			}
			_ = xml.Unmarshal([]byte("<firmware>"+child.Inner+"</firmware>"), &features)
			for _, feature := range features.Items {
				if feature.Name == "secure-boot" && feature.Enabled == "yes" {
					secure = true
				}
			}
		}
	}
	if loader != "" && !strings.HasSuffix(loader, "/OVMF.amdsev.fd") {
		return content, nil
	}
	if nvram {
		return "", fmt.Errorf("自动固件存在 NVRAM，禁止自动替换密钥状态，请人工核对")
	}
	code := "/usr/share/OVMF/OVMF_CODE_4M.fd"
	vars := "/usr/share/OVMF/OVMF_VARS_4M.fd"
	if secure {
		code = "/usr/share/OVMF/OVMF_CODE_4M.secboot.fd"
		vars = "/usr/share/OVMF/OVMF_VARS_4M.ms.fd"
	}
	if !exists(code) || !exists(vars) {
		return "", fmt.Errorf("缺少标准 OVMF 固件或变量模板，请安装 ovmf")
	}
	attrs := []xml.Attr{}
	for _, attr := range config.Attrs {
		if attr.Name.Local != "firmware" {
			attrs = append(attrs, attr)
		}
	}
	config.Attrs = attrs
	children := []firmwareChild{}
	for _, child := range config.Children {
		if child.XMLName.Local != "firmware" && child.XMLName.Local != "loader" {
			children = append(children, child)
		}
	}
	config.Children = append(children, firmwareChild{XMLName: xml.Name{Local: "loader"}, Attrs: []xml.Attr{{Name: xml.Name{Local: "readonly"}, Value: "yes"}, {Name: xml.Name{Local: "type"}, Value: "pflash"}, {Name: xml.Name{Local: "format"}, Value: "raw"}}, Inner: code}, firmwareChild{XMLName: xml.Name{Local: "nvram"}, Attrs: []xml.Attr{{Name: xml.Name{Local: "template"}, Value: vars}}})
	replacement, err := xml.Marshal(config)
	if err != nil {
		return "", err
	}
	return content[:location[0]] + string(replacement) + content[location[1]:], nil
}
