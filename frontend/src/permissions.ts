import type { CurrentUser } from "./types";

/** 判断当前用户是否具备指定权限码；前端隐藏不作为权限边界。 */
export function can(user: CurrentUser, code: string): boolean {
  return user.permissions.includes(code);
}
