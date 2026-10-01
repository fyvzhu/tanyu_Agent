const TOKEN_KEY = 'access_token'
const USER_KEY = 'user_info'

/**
 * 获取 Access Token
 */
export function getAccessToken() {
  return localStorage.getItem(TOKEN_KEY)
}

/**
 * 设置 Access Token
 */
export function setAccessToken(token) {
  localStorage.setItem(TOKEN_KEY, token)
}

/**
 * 移除 Access Token
 */
export function removeAccessToken() {
  localStorage.removeItem(TOKEN_KEY)
}

/**
 * 获取用户信息
 */
export function getUserInfo() {
  const userStr = localStorage.getItem(USER_KEY)
  if (userStr) {
    try {
      return JSON.parse(userStr)
    } catch (e) {
      return null
    }
  }
  return null
}

/**
 * 设置用户信息
 */
export function setUserInfo(user) {
  localStorage.setItem(USER_KEY, JSON.stringify(user))
}

/**
 * 移除用户信息
 */
export function removeUserInfo() {
  localStorage.removeItem(USER_KEY)
}

/**
 * 清除所有认证信息
 */
export function clearAuth() {
  removeAccessToken()
  removeUserInfo()
}
