declare module "@novnc/novnc" {
  export default class RFB {
    constructor(
      target: HTMLElement,
      url: string,
      options?: {
        credentials?: { username?: string; password?: string; target?: string };
        shared?: boolean;
        repeaterID?: string;
      },
    );
    scaleViewport: boolean;
    resizeSession: boolean;
    viewOnly: boolean;
    background: string;
    qualityLevel: number;
    compressionLevel: number;
    sendCredentials(credentials: { password: string }): void;
    focus(options?: FocusOptions): void;
    blur(): void;
    disconnect(): void;
    sendCtrlAltDel(): void;
    clipboardPasteFrom(text: string): void;
    addEventListener(type: string, listener: (event: Event) => void): void;
    removeEventListener(type: string, listener: (event: Event) => void): void;
  }
}
