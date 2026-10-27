/** 后端角色名与界面称呼的映射。 */
export const ROLE_OPTIONS = [
  { value: "Admin", label: "管理员" },
  { value: "Operator", label: "学员" },
  { value: "Viewer", label: "一般用户" },
] as const;

const ROLE_LABELS: Record<string, string> = {
  Admin: "管理员",
  Operator: "学员",
  Viewer: "一般用户",
};

/** 返回角色的中文称呼；未知角色原样显示。 */
export function roleLabel(role: string): string {
  return ROLE_LABELS[role] ?? role;
}
