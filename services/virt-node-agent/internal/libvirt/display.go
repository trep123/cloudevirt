package libvirt

import (
	"context"
	"encoding/xml"
	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/apierr"
	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/domainxml"
	"regexp"
	"strings"
)

type DisplayConfig struct {
	Model  string `json:"model"`
	Width  int    `json:"width"`
	Height int    `json:"height"`
}

var videoElement = regexp.MustCompile(`(?s)<video(?:\s[^>]*)?>.*?</video>`)
var videoModelElement = regexp.MustCompile(`(?s)<model\b[^>]*(?:/>|>.*?</model>)`)

func parseDisplay(content string) (DisplayConfig, error) {
	var root struct {
		Devices struct {
			Video []struct {
				Model struct {
					Type       string                    `xml:"type,attr"`
					Resolution domainxml.VideoResolution `xml:"resolution"`
				} `xml:"model"`
			} `xml:"video"`
		} `xml:"devices"`
	}
	if err := xml.Unmarshal([]byte(content), &root); err != nil {
		return DisplayConfig{}, err
	}
	if len(root.Devices.Video) != 1 {
		return DisplayConfig{}, apierr.New(apierr.CodeConflict, "仅支持单显卡虚拟机的显示配置", nil)
	}
	m := root.Devices.Video[0].Model
	return DisplayConfig{Model: m.Type, Width: m.Resolution.X, Height: m.Resolution.Y}, nil
}

func replaceDisplay(content string, config DisplayConfig) (string, error) {
	if _, err := parseDisplay(content); err != nil {
		return "", err
	}
	video, err := domainxml.BuildVideo(config.Model, config.Width, config.Height)
	if err != nil {
		return "", err
	}
	model, err := xml.Marshal(struct {
		XMLName xml.Name `xml:"model"`
		domainxml.VideoModel
	}{VideoModel: video.Model})
	if err != nil {
		return "", err
	}
	locations := videoElement.FindAllStringIndex(content, -1)
	if len(locations) != 1 {
		return "", apierr.New(apierr.CodeConflict, "无法安全识别单显卡配置", nil)
	}
	loc := locations[0]
	section := content[loc[0]:loc[1]]
	m := videoModelElement.FindStringIndex(section)
	if m == nil {
		return "", apierr.New(apierr.CodeConflict, "缺少显卡型号配置", nil)
	}
	section = section[:m[0]] + string(model) + section[m[1]:]
	result := content[:loc[0]] + section + content[loc[1]:]
	if _, err := parseDisplay(result); err != nil {
		return "", err
	}
	return result, nil
}

func (c *Client) DomainDisplay(ctx context.Context, name string) (DisplayConfig, error) {
	content, err := c.run(ctx, "dumpxml", name, "--inactive")
	if err != nil {
		return DisplayConfig{}, err
	}
	return parseDisplay(content)
}
func (c *Client) ConfigureDisplay(ctx context.Context, name string, config DisplayConfig) (DisplayConfig, error) {
	if !domainxml.ValidName(name) {
		return DisplayConfig{}, apierr.New(apierr.CodeInvalidArgument, "域名无效", nil)
	}
	if _, err := domainxml.BuildVideo(config.Model, config.Width, config.Height); err != nil {
		return DisplayConfig{}, err
	}
	state, err := c.DomainState(ctx, name)
	if err != nil {
		return DisplayConfig{}, err
	}
	if state != StateShutoff {
		return DisplayConfig{}, apierr.New(apierr.CodeConflict, "请先正常关闭虚拟机后修改显卡和启动显示尺寸", nil)
	}
	content, err := c.run(ctx, "dumpxml", name, "--inactive")
	if err != nil {
		return DisplayConfig{}, err
	}
	if strings.Contains(content, "<hostdev") {
		return DisplayConfig{}, apierr.New(apierr.CodeConflict, "含直通设备的虚拟机需人工核对显示配置", nil)
	}
	updated, err := replaceDisplay(content, config)
	if err != nil {
		return DisplayConfig{}, err
	}
	if err = c.DefineDomain(ctx, updated); err != nil {
		return DisplayConfig{}, err
	}
	actual, err := c.DomainDisplay(ctx, name)
	if err != nil {
		return DisplayConfig{}, err
	}
	if actual != config {
		return actual, apierr.New(apierr.CodeOperationFailed, "节点未确认保存目标显卡配置", nil)
	}
	return actual, nil
}
