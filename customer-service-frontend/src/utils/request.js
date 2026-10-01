import axios from 'axios'
import { getAccessToken, setAccessToken, removeAccessToken } from './auth'

// 创建 axios 实例
const request = axios.create({
  baseURL: '/',
  timeout: 30000,
})

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

    // 401 错误且未重试过，尝试刷新 token
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true

      try {
        // 调用刷新接口
        const { data } = await axios.post('/commerce/api/v1/auth/refresh', {}, {
          withCredentials: true, // 携带 HttpOnly Cookie
        })

        if (data.code === 0) {
          // 更新 access token
          setAccessToken(data.data.access_token)
          
          // 重试原请求
          originalRequest.headers.Authorization = `Bearer ${data.data.access_token}`
          return axios(originalRequest)
        }
      } catch (refreshError) {
        // 刷新失败，清除 token 并跳转登录
        removeAccessToken()
        window.location.href = '/login'
        return Promise.reject(refreshError)
      }
    }

    return Promise.reject(error)
  }
)

export default request
