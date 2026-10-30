import type { Task } from "../types";
export function taskPresentation(status: string) {
  return { terminal: ["SUCCEEDED", "FAILED", "CANCELLED"].includes(status),
    failed: ["FAILED", "CANCELLED"].includes(status), succeeded: status === "SUCCEEDED" };
}
export function monitorTask(options: {
  load: () => Promise<Task>; update: (task: Task) => void; error: (error: unknown) => void;
  hidden: () => boolean; schedule: (callback: () => void, ms: number) => number;
  cancel: (timer: number) => void;
}) {
  let stopped = false, terminal = false, pending = false, timer: number | undefined, failures = 0, polls = 0;
  const refresh = async () => {
    if (stopped || terminal || pending || options.hidden()) return;
    if (timer !== undefined) options.cancel(timer);
    pending = true;
    try {
      const task = await options.load();
      if (stopped) return;
      terminal = taskPresentation(task.status).terminal;
      failures = 0;
      options.update(task);
    } catch (error) {
      if (!stopped) { failures++; options.error(error); }
    } finally {
      pending = false;
      if (!stopped && !terminal) {
        polls++;
        const delay = failures ? Math.min(15000, 2000 * 2 ** Math.min(failures - 1, 3)) : polls < 10 ? 1500 : 4000;
        timer = options.schedule(() => { void refresh(); }, delay);
      }
    }
  };
  void refresh();
  return { refresh, stop() { stopped = true; if (timer !== undefined) options.cancel(timer); } };
}
