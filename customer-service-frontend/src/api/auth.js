import request from '@/utils/request'

/**
 * 用户登录
 */
export function login(data) {
  return request({
    url: '/commerce/api/v1/auth/login',
    method: 'post',
    data,
    withCredentials: true, // 携带 Cookie
  })
}

/**
 * 用户注册
 */
export function register(data) {
  return request({
    url: '/commerce/api/v1/auth/register',
    method: 'post',
    data,
    withCredentials: true,
  })
}

/**
 * 刷新 Token
 */
export function refreshToken() {
  return request({
    url: '/commerce/api/v1/auth/refresh',
    method: 'post',
    withCredentials: true,
  })
}

/**
 * 退出登录
 */
export function logout() {
  return request({
    url: '/commerce/api/v1/auth/logout',
    method: 'post',
    withCredentials: true,
  })
}

/**
 * 获取当前用户信息
 */
export function getCurrentUser() {
  return request({
    url: '/commerce/api/v1/auth/me',
    method: 'get',
  })
}
