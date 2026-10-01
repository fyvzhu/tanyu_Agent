import request from '@/utils/request'

/**
 * 创建会话
 */
export function createSession(data) {
  return request({
    url: '/api/v1/chat/sessions',
    method: 'post',
    data,
  })
}

/**
 * 获取会话列表
 */
export function getSessionList(params) {
  return request({
    url: '/api/v1/chat/sessions',
    method: 'get',
    params,
  })
}

/**
 * 获取会话历史消息
 */
export function getSessionMessages(sessionId, params) {
  return request({
    url: `/api/v1/chat/sessions/${sessionId}/messages`,
    method: 'get',
    params,
  })
}

/**
 * 发送消息
 */
export function sendMessage(data) {
  const { session_id, ...payload } = data
  return request({
    url: `/api/v1/chat/sessions/${session_id}/messages`,
    method: 'post',
    data: payload,
  })
}

/**
 * 关闭会话
 */
export function closeSession(sessionId) {
  return request({
    url: `/api/v1/chat/sessions/${sessionId}`,
    method: 'delete',
  })
}
