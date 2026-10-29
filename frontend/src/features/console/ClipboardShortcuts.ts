// Clipboard access is limited to an explicit shortcut in the focused console.
export class ClipboardShortcuts {
  private pendingCopy = false;
  private shiftedPaste = false;
  private timer: ReturnType<typeof setTimeout> | undefined;
  private intercepted = new Set<string>();
  constructor(
    private target: HTMLElement,
    private actions: {
      enabled: () => boolean;
      paste: (text: string) => void;
      shortcut: (key: "c" | "v" | "x", shift: boolean) => void;
      report: (message: string) => void;
    },
  ) {
    target.addEventListener("keydown", this.keydown, true);
    target.addEventListener("keyup", this.keyup, true);
    target.addEventListener("paste", this.paste, true);
  }
  private keydown = (event: KeyboardEvent) => {
    const key = event.key.toLowerCase();
    if (
      event.altKey ||
      !(event.ctrlKey || event.metaKey) ||
      !["c", "v", "x"].includes(key) ||
      !this.actions.enabled()
    )
      return;
    event.stopImmediatePropagation();
    this.intercepted.add(event.code);
    if (key === "v") {
      // Preserve native paste: clipboardData works without a read permission or polling.
      this.shiftedPaste = event.shiftKey;
      return;
    }
    event.preventDefault();
    this.pendingCopy = true;
    clearTimeout(this.timer);
    this.timer = setTimeout(() => {
      this.pendingCopy = false;
      this.actions.report(
        "未收到客体剪贴板数据，请确认已启用剪贴板通道并运行 spice-vdagent。",
      );
    }, 3000);
    this.actions.shortcut(key === "x" ? "x" : "c", event.shiftKey);
  };
  private keyup = (event: KeyboardEvent) => {
    if (this.intercepted.delete(event.code)) {
      event.stopImmediatePropagation();
    }
  };
  private paste = (event: ClipboardEvent) => {
    if (!this.actions.enabled()) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    const text = event.clipboardData?.getData("text/plain");
    if (text === undefined) {
      this.actions.report("浏览器未提供粘贴文本");
      return;
    }
    if (text.length > 65536) {
      this.actions.report("单次粘贴不能超过 64 KiB 文本字符");
      return;
    }
    if (!text) return;
    this.actions.paste(text);
    this.actions.shortcut("v", this.shiftedPaste);
    this.shiftedPaste = false;
  };
  receive(text: string) {
    if (!this.pendingCopy) return;
    this.pendingCopy = false;
    clearTimeout(this.timer);
    if (!navigator.clipboard?.writeText) {
      this.actions.report(
        "浏览器未开放剪贴板写入，请使用受信任 HTTPS 并允许剪贴板权限",
      );
      return;
    }
    void navigator.clipboard
      .writeText(text)
      .catch(() =>
        this.actions.report(
          "浏览器拒绝复制，请允许此站点写入剪贴板后重试快捷键",
        ),
      );
  }
  dispose() {
    clearTimeout(this.timer);
    this.pendingCopy = false;
    this.target.removeEventListener("keydown", this.keydown, true);
    this.target.removeEventListener("keyup", this.keyup, true);
    this.target.removeEventListener("paste", this.paste, true);
  }
}
