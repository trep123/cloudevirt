export type RolePermission = {
  code: string;
  name: string;
  module: string;
  assignable: boolean;
  dependencies: string[];
  restriction?: string;
};

/** Adding operations includes prerequisites; removing prerequisites drops dependents. */
export function selectPermissions(
  selected: string[], codes: string[], enabled: boolean, catalog: RolePermission[],
): string[] {
  const available = new Map(catalog.filter(p => p.assignable).map(p => [p.code, p]));
  const next = new Set(selected.filter(code => available.has(code)));
  if (enabled) {
    const include = (code: string) => {
      if (!available.has(code) || next.has(code)) return;
      next.add(code);
      for (const dependency of available.get(code)!.dependencies) include(dependency);
    };
    codes.forEach(include);
  } else {
    codes.forEach(code => next.delete(code));
    let changed = true;
    while (changed) {
      changed = false;
      for (const code of next) {
        if (available.get(code)!.dependencies.some(dependency => !next.has(dependency))) {
          next.delete(code);
          changed = true;
        }
      }
    }
  }
  return [...next].sort();
}
