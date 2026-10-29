package domainxml

type ClipboardChannel struct {
	Type   string `xml:"type,attr"`
	Source struct {
		Clipboard struct {
			CopyPaste string `xml:"copypaste,attr"`
		} `xml:"clipboard"`
	} `xml:"source"`
	Target struct {
		Type string `xml:"type,attr"`
		Name string `xml:"name,attr"`
	} `xml:"target"`
}

func NewClipboardChannel() ClipboardChannel {
	c := ClipboardChannel{Type: "qemu-vdagent"}
	c.Source.Clipboard.CopyPaste = "yes"
	c.Target.Type = "virtio"
	c.Target.Name = "com.redhat.spice.0"
	return c
}
