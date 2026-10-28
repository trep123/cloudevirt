/**
 * 控制台统一图标集（内联 SVG，24 网格，1.75 描边，继承 currentColor）。
 * 新增图标只需在 PATHS 中登记，避免各页面混用字符图标。
 */
import type { CSSProperties } from "react";

const PATHS: Record<string, string> = {
  dashboard: "M4 13h6V4H4zM14 20h6v-9h-6zM14 4v4h6V4zM4 20h6v-3H4z",
  cluster:
    "M12 3 4 7.5v9L12 21l8-4.5v-9zM12 12 4 7.5M12 12l8-4.5M12 12v9",
  server:
    "M4 5h16v6H4zM4 13h16v6H4zM8 8h.01M8 16h.01M12 8h4M12 16h4",
  vm: "M3 5h18v11H3zM8 20h8M12 16v4M7 9l2.5 2L7 13M12 13h4",
  pool: "M4 7c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3zM4 7v5c0 1.7 3.6 3 8 3s8-1.3 8-3V7M4 12v5c0 1.7 3.6 3 8 3s8-1.3 8-3v-5",
  template: "M5 4h10l4 4v12H5zM14 4v5h5M8 13h8M8 17h5",
  volume: "M6 3h12v18H6zM9 7h6M9 11h6M12 17h.01",
  image: "M4 5h16v14H4zM4 15l4.5-4.5 4 4L15 12l5 5M15.5 8.5h.01",
  storage:
    "M3 7h18v4H3zM3 13h18v4H3zM7 9h.01M7 15h.01",
  snapshot:
    "M4 8h3l2-3h6l2 3h3v11H4zM12 17a4 4 0 1 0 0-8 4 4 0 0 0 0 8z",
  network:
    "M12 3v5M12 16v5M5 12H3M21 12h-2M7 7l-2-2M19 19l-2-2M7 17l-2 2M19 5l-2 2M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z",
  users:
    "M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM2 21c0-3.9 3.1-7 7-7s7 3.1 7 7M16 3.5a4 4 0 0 1 0 7.5M22 21c0-3-1.8-5.6-4.5-6.6",
  task: "M9 6h11M9 12h11M9 18h11M4 6l1 1 2-2M4 12l1 1 2-2M4 18l1 1 2-2",
  monitor: "M3 12h4l3-8 4 16 3-8h4",
  audit:
    "M12 3 4 6v6c0 4.5 3.4 8.3 8 9 4.6-.7 8-4.5 8-9V6zM9 12l2 2 4-4",
  settings:
    "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z",
  console: "M3 5h18v14H3zM7 10l3 2-3 2M12 14h5",
  plus: "M12 5v14M5 12h14",
  refresh: "M20 11a8 8 0 0 0-14.9-3M4 5v3h3M4 13a8 8 0 0 0 14.9 3M20 19v-3h-3",
  search: "M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14zM20 20l-4-4",
  bell: "M6 16V11a6 6 0 1 1 12 0v5l2 2H4zM10 21h4",
  help: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM9.5 9a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6V14M12 17h.01",
  menu: "M4 6h16M4 12h16M4 18h16",
  collapse: "M4 5h16v14H4zM9 5v14M15 10l-2 2 2 2",
  expand: "M4 5h16v14H4zM9 5v14M13 10l2 2-2 2",
  chevronDown: "M6 9l6 6 6-6",
  chevronRight: "M9 6l6 6-6 6",
  chevronLeft: "M15 6l-6 6 6 6",
  arrowLeft: "M19 12H5M11 6l-6 6 6 6",
  more: "M5 12h.01M12 12h.01M19 12h.01",
  close: "M6 6l12 12M18 6 6 18",
  logout: "M15 4h4v16h-4M10 8l-4 4 4 4M6 12h10",
  user: "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 21c0-4 3.6-7 8-7s8 3 8 7",
  key: "M15 9a4 4 0 1 1-3.5 6L9 17.5V20H6.5v-2.5L10.5 13.5A4 4 0 0 1 15 9zM16.5 10.5h.01",
  play: "M7 4v16l13-8z",
  stop: "M6 6h12v12H6z",
  power: "M12 3v8M6.3 6.3a8 8 0 1 0 11.4 0",
  cpu: "M7 7h10v10H7zM10 10h4v4h-4zM9 3v4M15 3v4M9 17v4M15 17v4M3 9h4M3 15h4M17 9h4M17 15h4",
  memory: "M3 8h18v8H3zM7 8v8M11 8v8M15 8v8M5 19v-3M19 19v-3",
  disk: "M4 6c0-1.1 3.6-2 8-2s8 .9 8 2v12c0 1.1-3.6 2-8 2s-8-.9-8-2zM4 6c0 1.1 3.6 2 8 2s8-.9 8-2",
  alert: "M12 4 2.5 20h19zM12 10v4M12 17h.01",
  check: "M5 12.5l4.5 4.5L19 7.5",
  info: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 11v6M12 7.5h.01",
  clock: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 7v5l3 2",
  filter: "M4 5h16l-6 8v6l-4-2v-4z",
  copy: "M8 8h12v12H8zM4 16V4h12",
  external: "M14 4h6v6M20 4l-9 9M18 14v6H4V6h6",
  inbox: "M3 13l3-8h12l3 8v6H3zM3 13h5l1.5 2h5L16 13h5",
  trend: "M3 17l6-6 4 4 8-8M15 7h6v6",
};

export type IconName = keyof typeof PATHS;

export function Icon({
  name,
  size = 16,
  className,
  style,
  strokeWidth = 1.75,
}: {
  name: string;
  size?: number;
  className?: string;
  style?: CSSProperties;
  strokeWidth?: number;
}) {
  const d = PATHS[name] || PATHS.info;
  return (
    <svg
      className={"icon" + (className ? " " + className : "")}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      style={style}
    >
      <path d={d} />
    </svg>
  );
}
