/**
 * localStorage 封装：集中管理 token / user 信息
 * 避免在业务代码里直接读写 localStorage，方便后续做加密 / cookie 切换
 */

const TOKEN_KEY = 'biz_token';
const USER_KEY = 'biz_user';

export interface UserInfo {
  id: string;
  username: string;
  role: 'submitter' | 'approver';
  displayName?: string;
}

/** 获取 access token */
export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

/** 保存 access token */
export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

/** 清除 access token */
export function removeToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

/** 获取当前登录用户信息 */
export function getUser(): UserInfo | null {
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as UserInfo;
  } catch {
    return null;
  }
}

/** 保存当前登录用户信息 */
export function setUser(user: UserInfo): void {
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

/** 清除当前登录用户信息 */
export function removeUser(): void {
  localStorage.removeItem(USER_KEY);
}

/** 登出：同时清除 token + user */
export function clearAuth(): void {
  removeToken();
  removeUser();
}
