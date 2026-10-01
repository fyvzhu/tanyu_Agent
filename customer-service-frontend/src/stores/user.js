import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getUserInfo, setUserInfo, removeUserInfo } from '@/utils/auth'

export const useUserStore = defineStore('user', () => {
  // 状态
  const userId = ref(null)
  const username = ref(null)
  const nickname = ref(null)
  const level = ref(null)

  // 初始化用户信息（从 localStorage 读取）
  function initUserInfo() {
    const user = getUserInfo()
    if (user) {
      userId.value = user.user_id
      username.value = user.username
      nickname.value = user.nickname
      level.value = user.level
    }
  }

  // 设置用户信息
  function setUser(user) {
    userId.value = user.user_id
    username.value = user.username
    nickname.value = user.nickname
    level.value = user.level
    
    // 持久化到 localStorage
    setUserInfo({
      user_id: user.user_id,
      username: user.username,
      nickname: user.nickname,
      level: user.level,
    })
  }

  // 清除用户信息
  function clearUser() {
    userId.value = null
    username.value = null
    nickname.value = null
    level.value = null
    removeUserInfo()
  }

  // 初始化
  initUserInfo()

  return {
    userId,
    username,
    nickname,
    level,
    setUser,
    clearUser,
  }
})
