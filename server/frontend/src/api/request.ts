import axios, { AxiosError, type AxiosInstance, type InternalAxiosRequestConfig } from 'axios';
import { getToken, clearAuth } from '@/utils/storage';

/**
 * axios 封装：
 *  - baseURL = /api/v1（由 vite proxy 转发到 http://localhost:8000）
 *  - 请求拦截：自动注入 Authorization: Bearer ${token}
 *  - 响应拦截：401 自动清除登录态并跳 /login
 */
export const BASE_URL = '/api/v1';

const service: AxiosInstance = axios.create({
  baseURL: BASE_URL,
  timeout: 15000,
});

// ===== 请求拦截器：注入 token =====
service.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = getToken();
    if (token) {
      // 确保 headers 对象存在
      config.headers = config.headers ?? ({} as any);
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error),
);

// ===== 响应拦截器：统一错误处理 + 401 跳登录 =====
service.interceptors.response.use(
  (resp) => resp,
  (error: AxiosError) => {
    if (error.response?.status === 401) {
      clearAuth();
      // 避免已经在登录页时重复跳转
      if (window.location.pathname !== '/login') {
        window.location.href = '/login';
      }
    }
    // 抛出带 message 的错误，供调用方 catch
    const msg =
      (error.response?.data as { detail?: string })?.detail ||
      error.message ||
      '请求失败';
    return Promise.reject(new Error(typeof msg === 'string' ? msg : '请求失败'));
  },
);

export default service;
