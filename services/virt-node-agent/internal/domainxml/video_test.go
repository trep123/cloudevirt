package domainxml

import (
	"encoding/xml"
	"testing"
)

func TestVideoConfiguration(t *testing.T) {
	for _, model := range []string{"vga", "virtio"} {
		spec := validSpec()
		spec.Hardware = Hardware{VideoModel: model, VideoWidth: 3840, VideoHeight: 2160}
		content, err := Build(spec)
		if err != nil {
			t.Fatal(err)
		}
		var actual domain
		if err = xml.Unmarshal([]byte(content), &actual); err != nil {
			t.Fatal(err)
		}
		if actual.Devices.Video.Model.Type != model || actual.Devices.Video.Model.Resolution.X != 3840 {
			t.Fatal("missing guest video configuration")
		}
	}
	for _, h := range []Hardware{{VideoModel: "cirrus", VideoWidth: 1920, VideoHeight: 1080}, {VideoWidth: 1920}, {VideoWidth: 3841, VideoHeight: 2160}, {VideoWidth: 640, VideoHeight: 479}} {
		spec := validSpec()
		spec.Hardware = h
		if _, err := Build(spec); err == nil {
			t.Fatalf("accepted invalid video %+v", h)
		}
	}
	spec := validSpec()
	content, err := Build(spec)
	if err != nil {
		t.Fatal(err)
	}
	var actual domain
	_ = xml.Unmarshal([]byte(content), &actual)
	if actual.Devices.Video.Model.Type != "vga" || actual.Devices.Video.Model.VRAM != 65536 {
		t.Fatal("default must not fall back to Cirrus")
	}
}
