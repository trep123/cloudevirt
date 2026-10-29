package domainxml

import "github.com/tl2004/cloude-virt/services/virt-node-agent/internal/apierr"

type Video struct {
	Model VideoModel `xml:"model"`
}
type VideoModel struct {
	Type       string           `xml:"type,attr"`
	VRAM       int              `xml:"vram,attr,omitempty"`
	Heads      int              `xml:"heads,attr"`
	Primary    string           `xml:"primary,attr"`
	Resolution *VideoResolution `xml:"resolution,omitempty"`
}
type VideoResolution struct {
	X int `xml:"x,attr"`
	Y int `xml:"y,attr"`
}

// Resolution is a guest-visible minimum/preferred mode, not a desktop policy.
func BuildVideo(model string, width, height int) (*Video, error) {
	if model == "" {
		model = "vga"
	}
	if model != "vga" && model != "virtio" {
		return nil, apierr.New(apierr.CodeInvalidArgument, "仅支持 VGA 或 VirtIO 显卡", nil)
	}
	if (width != 0 || height != 0) && (width < 640 || width > 3840 || height < 480 || height > 2160) {
		return nil, apierr.New(apierr.CodeInvalidArgument, "显卡分辨率需为 640×480 至 3840×2160", nil)
	}
	v := &Video{Model: VideoModel{Type: model, Heads: 1, Primary: "yes"}}
	if model == "vga" {
		v.Model.VRAM = 65536
	}
	if width != 0 {
		v.Model.Resolution = &VideoResolution{X: width, Y: height}
	}
	return v, nil
}
