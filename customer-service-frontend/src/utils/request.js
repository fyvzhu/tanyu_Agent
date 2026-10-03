import axios from 'axios'
import { getAccessToken, setAccessToken, removeAccessToken } from './auth'

// 创建 axios 实例
const request = axios.create({
  baseURL: '/',
  timeout: 30000,
})

// P0修复：单例模式的Token刷新Promise，避免并发请求重复刷新
let refreshPromise = null

// 请求拦截器
request.interceptors.request.use(
  (config) => {
    // 添加 access token
    const token = getAccessToken()
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// 响应拦截器
request.interceptors.response.use(
  (response) => {
    return response.data
  },
  async (error) => {
    const originalRequest = error.config

    // 不是401或已经重试过，直接拒绝
    if (
      error.response?.status !== 401 ||
      !originalRequest ||
      originalRequest._retry
    ) {
      return Promise.reject(error)
    }

    originalRequest._retry = true

    try {
      // P0修复：单例刷新，避免并发请求重复刷新Token
      if (!refreshPromise) {
        refreshPromise = axios
          .post('/commerce/api/v1/auth/refresh', {}, {
            withCredentials: true, // 携带 HttpOnly Cookie
          })
          .then(({ data }) => {
            if (!data.success || !data.data?.access_token) {
              throw new Error('Refresh token failed')
            }

            const token = data.data.access_token
            setAccessToken(token)
            return token
          })
          .finally(() => {
            refreshPromise = null
          })
      }

      const newToken = await refreshPromise

      originalRequest.headers.Authorization = `Bearer ${newToken}`

      // P0修复关键：必须重新走request实例，保证返回契约一致
      // 原来 return axios(originalRequest) 会导致返回AxiosResponse完整对象
      // 现在 return request(originalRequest) 会再次走response interceptor返回response.data
      // 这样无论首次200还是401->refresh->retry->200，调用方拿到的都是 {success, data} 结构
      return request(originalRequest)

    } catch (refreshError) {
      // 刷新失败，清除 token 并跳转登录
      removeAccessToken()
      window.location.href = '/login'
      return Promise.reject(refreshError)
    }
  }
)

export default request
