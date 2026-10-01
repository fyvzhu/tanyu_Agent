import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { getSessionList, getSessionMessages, createSession as createSessionApi, closeSession as closeSessionApi } from '@/api/chat'

export const useChatStore = defineStore('chat', () => {
  // 状态
  const sessions = ref([])
  const currentSessionId = ref(null)
  const messages = ref([])
  const loading = ref(false)
  const total = ref(0)

  // 计算属性
  const currentSession = computed(() => {
    return sessions.value.find(s => s.session_id === currentSessionId.value)
  })

  // 加载会话列表
  async function loadSessions(page = 1, pageSize = 20) {
    try {
      loading.value = true
      const res = await getSessionList({ page, page_size: pageSize })
      if (res.code === 0) {
        sessions.value = res.data.items
        total.value = res.data.total
      }
    } catch (error) {
      console.error('加载会话列表失败:', error)
      throw error
    } finally {
      loading.value = false
    }
  }

  // 创建新会话
  async function createSession() {
    try {
      loading.value = true
      const res = await createSessionApi({})
      if (res.code === 0) {
        const newSession = {
          session_id: res.data.session_id,
          title: '新会话',
          status: 'active',
          created_at: new Date().toISOString(),
          last_active_at: new Date().toISOString(),
        }
        sessions.value.unshift(newSession)
        currentSessionId.value = res.data.session_id
        messages.value = []
        return res.data.session_id
      }
    } catch (error) {
      console.error('创建会话失败:', error)
      throw error
    } finally {
      loading.value = false
    }
  }

  // 切换会话
  async function switchSession(sessionId) {
    if (currentSessionId.value === sessionId) return
    
    try {
      loading.value = true
      currentSessionId.value = sessionId
      
      // 加载会话消息
      const res = await getSessionMessages(sessionId, { limit: 50 })
      if (res.code === 0) {
        messages.value = res.data.messages || []
      }
    } catch (error) {
      console.error('切换会话失败:', error)
      throw error
    } finally {
      loading.value = false
    }
  }

  // 关闭会话
  async function closeSession(sessionId) {
    try {
      await closeSessionApi(sessionId)
      // 从列表中移除
      const index = sessions.value.findIndex(s => s.session_id === sessionId)
      if (index !== -1) {
        sessions.value.splice(index, 1)
      }
      // 如果关闭的是当前会话，清空消息
      if (currentSessionId.value === sessionId) {
        currentSessionId.value = null
        messages.value = []
      }
    } catch (error) {
      console.error('关闭会话失败:', error)
      throw error
    }
  }

  // 添加消息到当前会话
  function addMessage(message) {
    messages.value.push(message)

    // 更新会话的 last_active_at
    const session = sessions.value.find(s => s.session_id === currentSessionId.value)
    if (session) {
      session.last_active_at = new Date().toISOString()
    }
  }

  // 获取指定会话的历史消息
  function getSessionHistory(sessionId) {
    if (currentSessionId.value === sessionId) {
      return messages.value
    }
    // 如果不是当前会话，返回空数组（需要通过 switchSession 加载）
    return []
  }

  // 清空状态
  function clearAll() {
    sessions.value = []
    currentSessionId.value = null
    messages.value = []
    total.value = 0
  }

  return {
    sessions,
    currentSessionId,
    currentSession,
    messages,
    loading,
    total,
    loadSessions,
    createSession,
    switchSession,
    closeSession,
    addMessage,
    getSessionHistory,
    clearAll,
  }
})
