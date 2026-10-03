import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { getSessionList, getSessionMessages, createSession as createSessionApi, closeSession as closeSessionApi } from '@/api/chat'

// 用于防止过时请求覆盖
let lastSwitchRequestId = 0

export const useChatStore = defineStore('chat', () => {
  // 状态
  const sessions = ref([])
  const currentSessionId = ref(null)
  const sessionMessagesMap = ref(new Map()) // Map<sessionId, messages[]>
  const loading = ref(false)
  const total = ref(0)

  // P1修复：区分loading/error/truly-empty（参考修改建议1第三节）
  const sessionsLoading = ref(false)  // 会话列表加载中
  const sessionsLoaded = ref(false)   // 会话列表已加载（成功或失败）
  const sessionsLoadError = ref(null) // 会话列表加载错误信息

  // 计算属性
  const currentSession = computed(() => {
    return sessions.value.find(s => s.session_id === currentSessionId.value)
  })

  // 当前会话的消息（唯一数据源）
  const currentMessages = computed(() => {
    if (!currentSessionId.value) return []
    return sessionMessagesMap.value.get(currentSessionId.value) || []
  })

  // 转换后端历史消息格式为页面格式
  function transformHistoryMessage(backendMsg) {
    return {
      role: backendMsg.role === 'assistant' ? 'bot' : backendMsg.role,
      text: backendMsg.content || '',
      message_id: backendMsg.message_id,
      turn_id: backendMsg.turn_id,
      objects: backendMsg.objects || [],
      created_at: backendMsg.created_at,
    }
  }

  // 加载会话列表
  async function loadSessions(page = 1, pageSize = 20) {
    // P1修复：设置加载状态
    sessionsLoading.value = true
    sessionsLoadError.value = null

    try {
      loading.value = true
      const res = await getSessionList({ page, page_size: pageSize })

      // P1修复：验证响应格式
      if (!res?.success || !res?.data) {
        throw new Error('会话列表响应格式错误')
      }

      sessions.value = res.data.items || []
      total.value = res.data.total || 0

      // P1修复：标记加载成功
      sessionsLoaded.value = true

      // 修复问题2：如果没有当前会话且列表不为空，自动选择第一个
      if (!currentSessionId.value && sessions.value.length > 0) {
        const firstSessionId = sessions.value[0].session_id
        console.log(`[ChatStore] 自动选择第一个会话: ${firstSessionId}`)
        await switchSession(firstSessionId)
      }
    } catch (error) {
      // P1修复：记录错误信息
      sessionsLoadError.value = error?.message || '加载会话失败'
      console.error('加载会话列表失败:', error)
      throw error
    } finally {
      loading.value = false
      sessionsLoading.value = false
    }
  }

  // 创建新会话
  async function createSession() {
    try {
      loading.value = true
      const res = await createSessionApi({})
      if (res.success && res.data) {
        const newSession = {
          session_id: res.data.session_id,
          title: '新会话',
          status: 'active',
          created_at: new Date().toISOString(),
          last_active_at: new Date().toISOString(),
        }
        sessions.value.unshift(newSession)
        currentSessionId.value = res.data.session_id
        // 初始化空消息列表
        sessionMessagesMap.value.set(res.data.session_id, [])
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

    // 生成请求ID，防止过时请求覆盖
    const requestId = ++lastSwitchRequestId

    try {
      loading.value = true
      currentSessionId.value = sessionId

      // 检查缓存中是否已有消息
      if (sessionMessagesMap.value.has(sessionId)) {
        console.log(`[ChatStore] 使用缓存消息: session=${sessionId}`)
        return
      }

      // 从后端加载会话消息
      console.log(`[ChatStore] 从后端加载消息: session=${sessionId}`)
      const res = await getSessionMessages(sessionId, { limit: 50 })

      // 防止过时请求覆盖当前会话
      if (requestId !== lastSwitchRequestId) {
        console.log(`[ChatStore] 请求已过时，忽略: request=${requestId}, current=${lastSwitchRequestId}`)
        return
      }

      if (res.success && res.data) {
        const messages = (res.data.messages || []).map(transformHistoryMessage)
        sessionMessagesMap.value.set(sessionId, messages)
        console.log(`[ChatStore] 消息加载完成: session=${sessionId}, count=${messages.length}`)
      }
    } catch (error) {
      console.error('切换会话失败:', error)
      // 失败时初始化空数组，避免显示"加载中"
      if (!sessionMessagesMap.value.has(sessionId)) {
        sessionMessagesMap.value.set(sessionId, [])
      }
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
      // 从缓存中删除
      sessionMessagesMap.value.delete(sessionId)
      // 如果关闭的是当前会话，清空当前会话ID
      if (currentSessionId.value === sessionId) {
        currentSessionId.value = null
      }
    } catch (error) {
      console.error('关闭会话失败:', error)
      throw error
    }
  }

  // 添加消息到当前会话
  function addMessage(message) {
    if (!currentSessionId.value) return

    const messages = sessionMessagesMap.value.get(currentSessionId.value) || []
    messages.push(message)
    sessionMessagesMap.value.set(currentSessionId.value, messages)

    // 更新会话的 last_active_at
    const session = sessions.value.find(s => s.session_id === currentSessionId.value)
    if (session) {
      session.last_active_at = new Date().toISOString()
    }
  }

  // 获取指定会话的历史消息（已废弃，使用 currentMessages computed）
  function getSessionHistory(sessionId) {
    return sessionMessagesMap.value.get(sessionId) || []
  }

  // 清空状态
  function clearAll() {
    sessions.value = []
    currentSessionId.value = null
    sessionMessagesMap.value.clear()
    total.value = 0
  }

  return {
    sessions,
    currentSessionId,
    currentSession,
    currentMessages, // 导出 computed，替代旧的 messages
    loading,
    total,
    // P1修复：导出加载状态（参考修改建议1第三节）
    sessionsLoading,
    sessionsLoaded,
    sessionsLoadError,
    loadSessions,
    createSession,
    switchSession,
    closeSession,
    addMessage,
    getSessionHistory,
    clearAll,
  }
})
