<template>
  <div class="chat-view">
    <!-- 左侧会话列表 -->
    <div class="sidebar-left">
      <div class="sidebar-header">
        <button class="btn-new-chat" @click="createNewSession">
          ➕ 新对话
        </button>
      </div>

      <div class="user-info">
        <div class="user-avatar">{{ (userStore.nickname || userStore.username || 'U')[0].toUpperCase() }}</div>
        <div class="user-details">
          <div class="user-name">{{ userStore.nickname || userStore.username }}</div>
          <div class="user-status">在线</div>
        </div>
        <button class="btn-profile" @click="router.push('/profile')" title="个人信息">
          ⚙️
        </button>
      </div>

      <div class="session-list">
        <div
          v-for="session in chatStore.sessions"
          :key="session.session_id"
          class="session-item"
          :class="{ 'active': session.session_id === chatStore.currentSessionId }"
          @click="chatStore.switchSession(session.session_id)"
        >
          <div class="session-title">{{ session.title || '新会话' }}</div>
          <div class="session-time">{{ formatTime(session.last_active_at) }}</div>

          <!-- 只在活动会话显示删除按钮 -->
          <button
            v-if="session.session_id === chatStore.currentSessionId"
            class="btn-delete-session"
            @click.stop="confirmDeleteSession(session.session_id)"
            title="删除会话"
          >
            🗑️
          </button>
        </div>
        <div v-if="chatStore.sessions.length === 0" class="empty-sessions">
          暂无会话
        </div>
      </div>

      <div class="sidebar-footer">
        <button class="btn-logout" @click="handleLogout">
          🚪 退出登录
        </button>
      </div>
    </div>

    <!-- 中间聊天区域 -->
    <div class="main-chat">
      <canvas ref="bgCanvas" class="bg-canvas"></canvas>

      <div class="chat-container">
        <div ref="messagesContainer" class="messages-container">
          <template v-for="turn in turns" :key="turn.id">
            <div v-if="turn.type === 'divider'" class="divider">
              {{ turn.text }}
            </div>

            <div v-else-if="turn.type === 'turn'" class="turn">
              <!-- 用户消息 -->
              <div v-if="turn.userMessage" class="message user-message">
                <div class="message-content">
                  <div class="message-text">{{ turn.userMessage.text }}</div>
                </div>
              </div>

              <!-- Bot 消息 -->
              <div v-for="botMsg in turn.botMessages" :key="botMsg.id" class="message bot-message">
                <div class="message-avatar message-avatar-emoji">
                  {{ customerService.avatar }}
                </div>
                <div class="message-content">
                  <div class="bot-name">{{ customerService.name }}</div>
                  <div class="message-text" v-html="formatMessageText(botMsg.text)"></div>

                  <!-- 商品卡片 -->
                  <div v-if="botMsg.objects && botMsg.objects.length > 0" class="product-cards">
                    <div v-for="obj in botMsg.objects" :key="obj.product_id" class="product-card">
                      <img :src="transformImageUrl(obj.main_image_url)" :alt="obj.title" class="product-image" />
                      <div class="product-info">
                        <div class="product-title">{{ obj.title }}</div>
                        <div class="product-brand" v-if="obj.brand">{{ obj.brand }}</div>
                        <div class="product-price">
                          <span v-if="obj.selected_sku_price">¥{{ obj.selected_sku_price }}</span>
                          <span v-else-if="obj.min_price && obj.max_price">¥{{ obj.min_price }} - ¥{{ obj.max_price }}</span>
                          <span v-else-if="obj.min_price">¥{{ obj.min_price }}</span>
                        </div>
                        <div class="product-stock" v-if="obj.stock_status">{{ obj.stock_status }}</div>
                      </div>
                    </div>
                  </div>

                  <!-- 操作按钮 -->
                  <div class="message-actions">
                    <button @click="copyBotText(botMsg)" class="btn-action">
                      {{ copyState[botMsg.id] ? '✓' : '📋' }}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </template>

          <div v-if="isSending" class="loading">发送中...</div>
          <div v-if="errorMessage" class="error-message">{{ errorMessage }}</div>
        </div>

        <!-- 输入框 -->
        <div class="input-area">
          <textarea
            v-model="draftMessage"
            placeholder="输入消息... (Enter 发送)"
            @keydown.enter.exact.prevent="sendTextMessage"
            rows="2"
          ></textarea>
          <button @click="sendTextMessage" :disabled="isSending || !draftMessage.trim()" class="btn-send">
            发送
          </button>
        </div>
      </div>
    </div>

    <!-- 右侧订单列表 -->
    <div class="sidebar-right">
      <div class="tabs">
        <button class="active">我的订单</button>
      </div>

      <div class="tab-content">
        <!-- 订单列表（带展开/收起功能） -->
        <div class="orders-list">
          <div v-for="order in orders" :key="order.order_id" class="order-container">
            <!-- 订单头部（可点击展开/收起） -->
            <div class="order-header" @click="toggleOrderExpand(order.order_id)">
              <span class="expand-icon" :class="{ expanded: expandedOrders.includes(order.order_id) }">▶</span>
              <div class="order-summary">
                <div class="order-id">订单 #{{ order.order_id }}</div>
                <div class="order-meta">
                  <span class="order-status">{{ order.status }}</span>
                  <span class="order-total">¥{{ order.amount }}</span>
                </div>
              </div>
            </div>

            <!-- 订单商品明细（展开时显示） -->
            <div v-if="expandedOrders.includes(order.order_id)" class="order-items">
              <div v-for="item in order.items" :key="item.sku_id" class="order-product-item">
                <!-- 商品图片 -->
                <div class="product-thumb">
                  <img
                    v-if="item.main_image_url"
                    :src="transformImageUrl(item.main_image_url)"
                    :alt="item.product_name"
                    @error="handleImageError"
                  />
                </div>

                <div class="product-info">
                  <!-- 商品名称 - 2行省略 + Tooltip -->
                  <el-tooltip :content="`${item.brand || ''} ${item.product_name || ''}`.trim()" placement="top">
                    <div class="product-name">{{ item.brand }} {{ item.product_name }}</div>
                  </el-tooltip>
                  <div class="product-specs">
                    <span v-if="item.color">{{ item.color }}</span>
                    <span v-if="item.size">{{ item.size }}</span>
                  </div>
                  <div class="product-price-qty">
                    <span>¥{{ item.price }}</span>
                    <span>x{{ item.quantity }}</span>
                  </div>
                </div>
              </div>
              <div v-if="!order.items || order.items.length === 0" class="empty-items">该订单暂无商品信息</div>
            </div>
          </div>
          <div v-if="orders.length === 0 && !isLoadingSidebar" class="empty">暂无订单</div>
          <div v-if="isLoadingSidebar" class="loading">加载中...</div>
        </div>

        <div v-if="sidebarError" class="error-message">{{ sidebarError }}</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useUserStore } from '@/stores/user'
import { useChatStore } from '@/stores/chat'
import { useRouter } from 'vue-router'
import { sendMessage } from '@/api/chat'
import { logout } from '@/api/auth'
import { clearAuth } from '@/utils/auth'
import { getOrders, transformImageUrl as transformImageUrlUtil } from '@/api/commerce'

const userStore = useUserStore()
const chatStore = useChatStore()
const router = useRouter()

const draftMessage = ref('')
const isSending = ref(false)
const errorMessage = ref('')
// 使用 store 的 currentMessages 作为唯一数据源
const messages = computed(() => chatStore.currentMessages)
const messagesContainer = ref(null)

const orders = ref([])
const expandedOrders = ref([]) // 展开的订单ID列表
const isLoadingSidebar = ref(false)
const sidebarError = ref('')

// Copy state
const copyState = ref({})

// ── Canvas 粒子背景系统 ──────────────────────────────────────────────
const bgCanvas = ref(null)
let animFrameId = null
let bgParticles = []
const BG_PARTICLE_COUNT = 80
const BG_CONNECT_DIST = 150
const BG_MOUSE_RADIUS = 180
const bgMouse = { x: null, y: null }

function createBgParticles(w, h) {
  const palette = [
    [13, 148, 136], [20, 184, 166], [245, 158, 11],
    [217, 119, 6], [2, 132, 199], [56, 189, 248],
  ]
  bgParticles = Array.from({ length: BG_PARTICLE_COUNT }, () => {
    const color = palette[Math.floor(Math.random() * palette.length)]
    return {
      x: Math.random() * w, y: Math.random() * h,
      size: Math.random() * 2.5 + 1,
      vx: (Math.random() - 0.5) * 0.35,
      vy: (Math.random() - 0.5) * 0.35,
      color, opacity: Math.random() * 0.45 + 0.12,
      phase: Math.random() * Math.PI * 2,
      pulse: Math.random() * 0.015 + 0.005,
    }
  })
}

function animateBg(ctx, w, h, time) {
  ctx.clearRect(0, 0, w, h)

  for (const p of bgParticles) {
    p.x += p.vx + Math.sin(time * 0.001 + p.phase) * 0.25
    p.y += p.vy + Math.cos(time * 0.001 + p.phase + 1) * 0.25

    if (bgMouse.x !== null) {
      const dx = p.x - bgMouse.x, dy = p.y - bgMouse.y
      const dist = Math.hypot(dx, dy)
      if (dist < BG_MOUSE_RADIUS) {
        const force = (BG_MOUSE_RADIUS - dist) / BG_MOUSE_RADIUS
        p.x += (dx / dist) * force * 0.7
        p.y += (dy / dist) * force * 0.7
      }
    }

    if (p.x < -20) p.x = w + 20; if (p.x > w + 20) p.x = -20
    if (p.y < -20) p.y = h + 20; if (p.y > h + 20) p.y = -20
  }

  // 连线
  ctx.lineWidth = 0.5
  for (let i = 0; i < bgParticles.length; i++) {
    for (let j = i + 1; j < bgParticles.length; j++) {
      const dx = bgParticles[i].x - bgParticles[j].x
      const dy = bgParticles[i].y - bgParticles[j].y
      const dist = Math.hypot(dx, dy)
      if (dist < BG_CONNECT_DIST) {
        const alpha = (1 - dist / BG_CONNECT_DIST) * 0.1
        ctx.strokeStyle = `rgba(13,148,136,${alpha})`
        ctx.beginPath()
        ctx.moveTo(bgParticles[i].x, bgParticles[i].y)
        ctx.lineTo(bgParticles[j].x, bgParticles[j].y)
        ctx.stroke()
      }
    }
  }

  // 粒子光晕
  for (const p of bgParticles) {
    const pulse = 1 + Math.sin(time * p.pulse + p.phase) * 0.25
    const r = p.size * pulse
    const [cr, cg, cb] = p.color

    ctx.beginPath()
    ctx.arc(p.x, p.y, r * 2.5, 0, Math.PI * 2)
    ctx.fillStyle = `rgba(${cr},${cg},${cb},${p.opacity * 0.08})`
    ctx.fill()

    ctx.beginPath()
    ctx.arc(p.x, p.y, r, 0, Math.PI * 2)
    ctx.fillStyle = `rgba(${cr},${cg},${cb},${p.opacity * 0.7})`
    ctx.fill()
  }
}

function initBg() {
  const canvas = bgCanvas.value
  if (!canvas) return
  const ctx = canvas.getContext('2d')

  const resize = () => {
    canvas.width = window.innerWidth
    canvas.height = window.innerHeight
    createBgParticles(canvas.width, canvas.height)
  }
  resize()
  window.addEventListener('resize', resize)

  const onMouseMove = (e) => { bgMouse.x = e.clientX; bgMouse.y = e.clientY }
  const onMouseLeave = () => { bgMouse.x = null; bgMouse.y = null }
  document.addEventListener('mousemove', onMouseMove)
  document.addEventListener('mouseleave', onMouseLeave)

  const loop = (time) => {
    animateBg(ctx, canvas.width, canvas.height, time)
    animFrameId = requestAnimationFrame(loop)
  }
  animFrameId = requestAnimationFrame(loop)

  canvas._cleanup = () => {
    cancelAnimationFrame(animFrameId)
    window.removeEventListener('resize', resize)
    document.removeEventListener('mousemove', onMouseMove)
    document.removeEventListener('mouseleave', onMouseLeave)
  }
}
// ── 粒子背景系统结束 ──────────────────────────────────────────────────

// 客服数字人配置
const customerService = {
  name: '探域智能体',
  title: 'AI助手',
  avatar: '🤖',  // 使用emoji，简单直接且兼容性好
  status: '在线'
}

// 将消息分组为 Turn 结构
const turns = computed(() => {
  const result = []
  let currentTurn = null
  let turnIndex = 0

  for (const message of messages.value) {
    if (message.type === 'divider') {
      if (currentTurn) {
        result.push(currentTurn)
        currentTurn = null
      }
      result.push({
        type: 'divider',
        text: message.text
      })
      continue
    }

    if (message.role === 'user') {
      if (currentTurn) {
        result.push(currentTurn)
      }
      turnIndex++
      currentTurn = {
        type: 'turn',
        id: `turn-${turnIndex}`,
        index: turnIndex,
        userMessage: message,
        botMessages: []
      }
    } else if (message.role === 'bot') {
      if (!currentTurn) {
        turnIndex++
        currentTurn = {
          type: 'turn',
          id: `turn-${turnIndex}`,
          index: turnIndex,
          userMessage: null,
          botMessages: []
        }
      }
      currentTurn.botMessages.push(message)
    }
  }

  if (currentTurn) {
    result.push(currentTurn)
  }

  return result
})

function createBaseMessage(role) {
  return {
    id: crypto.randomUUID(),
    role,
    buttons: [],
  }
}

function appendUserText(text) {
  messages.value.push({
    ...createBaseMessage('user'),
    type: 'text',
    text,
  })
}

function appendUserObject(objectType, payload) {
  messages.value.push({
    ...createBaseMessage('user'),
    type: 'object',
    objectType,
    payload,
  })
}

function appendBotMessages(botMessages) {
  for (const message of botMessages) {
    appendMessage('bot', message)
  }
}

function appendMessage(role, message) {
  const newMessage = {
    ...createBaseMessage(role),
    type: role === 'divider' ? 'divider' : 'text',
    text: message.text ?? (role === 'divider' ? '以上为历史消息' : ''),
    objects: message.objects ?? [],
    suggestions: message.suggestions ?? null,
    message_id: message.message_id,
    turn_id: message.turn_id,
  }

  // 通过 store 添加消息
  chatStore.addMessage(newMessage)
}

// 删除 setHistoryMessages 和 fetchChatHistory - store 已处理历史加载

async function scrollToBottom() {
  await nextTick()
  const container = messagesContainer.value
  if (!container) {
    return
  }
  container.scrollTop = container.scrollHeight
}

watch(
  () => messages.value.length,
  async () => {
    await scrollToBottom()
  }
)

async function fetchSidebarData() {
  orders.value = []
  sidebarError.value = ''

  if (!userStore.username) {
    return
  }

  isLoadingSidebar.value = true
  try {
    const ordersRes = await getOrders({ page: 1, page_size: 20 })
    orders.value = ordersRes.data?.items || []
  } catch (error) {
    sidebarError.value = error instanceof Error ? error.message : '加载订单列表失败。'
  } finally {
    isLoadingSidebar.value = false
  }
}

// 切换订单展开/收起
function toggleOrderExpand(orderId) {
  const index = expandedOrders.value.indexOf(orderId)
  if (index > -1) {
    // 收起
    expandedOrders.value.splice(index, 1)
  } else {
    // 展开
    expandedOrders.value.push(orderId)
  }
}

// 图片加载错误处理
function handleImageError(event) {
  // 图片加载失败时隐藏图片
  event.target.style.display = 'none'
}

async function sendPayload(payload) {
  if (isSending.value) {
    return
  }

  errorMessage.value = ''
  isSending.value = true

  try {
    const response = await sendMessage({
      session_id: chatStore.currentSessionId,
      ...payload,
    })

    // 后端返回 {success: true, data: ChatTurnResponse}
    if (response.data && (response.data.text || response.data.objects)) {
      appendMessage('bot', {
        text: response.data.text,
        objects: response.data.objects || [],
        message_id: response.data.message_id,
        turn_id: response.data.turn_id,
      })
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '请求失败。'
  } finally {
    isSending.value = false
  }
}

async function sendTextMessage() {
  const text = draftMessage.value.trim()

  if (!text) {
    return
  }

  if (!chatStore.currentSessionId) {
    await chatStore.createSession()
  }

  draftMessage.value = ''
  appendUserText(text)
  await sendPayload({ message: text })
}

async function sendOrder(order) {
  if (!chatStore.currentSessionId) {
    await chatStore.createSession()
  }

  appendUserObject('order', { ...order })
  await sendPayload({
    message: `我想查询订单 #${order.order_id}`,
    client_context: {
      type: 'order',
      order_id: order.order_id,
      status: order.status,
      amount: order.amount,
      created_at: order.created_at,
    },
  })
}

async function sendProduct(product) {
  if (!chatStore.currentSessionId) {
    await chatStore.createSession()
  }

  appendUserObject('product', { ...product })
  await sendPayload({
    message: `我想了解商品 ${product.brand || ''} ${product.product_display_name}`.trim(),
    client_context: {
      type: 'product',
      product_id: product.product_id,
      brand: product.brand,
      product_name: product.product_display_name,
      category: product.category,
      min_price: product.min_price,
      max_price: product.max_price,
      main_image_url: product.main_image_url,
      has_stock: product.has_stock,
    },
  })
}

async function createNewSession() {
  await chatStore.createSession()
  messages.value = []
  errorMessage.value = ''
}

async function handleLogout() {
  try {
    await logout()
    clearAuth()
    router.push('/login')
  } catch (error) {
    console.error('Logout failed:', error)
  }
}
// 删除旧的 watch - store 的 switchSession 已处理历史加载

onMounted(async () => {
  initBg()

  // 加载会话列表
  try {
    await chatStore.loadSessions()
  } catch (error) {
    console.error('加载会话列表失败:', error)
  }

  await fetchSidebarData()
})

onUnmounted(() => {
  if (bgCanvas.value?._cleanup) bgCanvas.value._cleanup()
})

async function confirmDeleteSession(sessionId) {
  if (confirm('确定要删除这个会话吗？')) {
    try {
      await chatStore.closeSession(sessionId)
    } catch (error) {
      console.error('删除会话失败:', error)
      alert('删除会话失败')
    }
  }
}

async function copyBotText(botMsg) {
  const msgId = botMsg.id
  try {
    await navigator.clipboard.writeText(botMsg.text)
    copyState.value[msgId] = true
    setTimeout(() => { copyState.value[msgId] = false }, 1800)
  } catch (error) {
    console.error('Copy failed:', error)
  }
}

function formatTime(timestamp) {
  if (!timestamp) return ''
  const date = new Date(timestamp)
  const now = new Date()
  const diff = now - date

  if (diff < 60000) return '刚刚'
  if (diff < 3600000) return `${Math.floor(diff / 60000)}分钟前`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}小时前`

  return date.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' })
}

function formatMessageText(text) {
  if (!text) return ''
  return text.replace(/\n/g, '<br>')
}

const transformImageUrl = transformImageUrlUtil
</script>

<style scoped>
.chat-view {
  display: flex;
  height: 100vh;
  overflow: hidden;
}

/* 左侧会话列表 */
.sidebar-left {
  width: 260px;
  background: rgba(15, 23, 42, 0.95);
  border-right: 1px solid rgba(13, 148, 136, 0.3);
  display: flex;
  flex-direction: column;
  backdrop-filter: blur(10px);
}

.sidebar-header {
  padding: 16px;
  border-bottom: 1px solid rgba(13, 148, 136, 0.2);
}

.btn-new-chat {
  width: 100%;
  padding: 12px;
  background: linear-gradient(135deg, #0D9488, #14B8A6);
  color: white;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  transition: all 0.3s;
}

.btn-new-chat:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(13, 148, 136, 0.4);
}

.user-info {
  padding: 16px;
  display: flex;
  align-items: center;
  gap: 12px;
  border-bottom: 1px solid rgba(13, 148, 136, 0.2);
}

.user-avatar {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: linear-gradient(135deg, #0D9488, #14B8A6);
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  font-weight: bold;
  font-size: 18px;
}

.user-details {
  flex: 1;
}

.user-name {
  color: white;
  font-weight: 500;
  font-size: 14px;
}

.user-status {
  color: rgba(255, 255, 255, 0.6);
  font-size: 12px;
}

.btn-profile {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: rgba(13, 148, 136, 0.2);
  border: 1px solid rgba(13, 148, 136, 0.3);
  color: white;
  cursor: pointer;
  transition: all 0.3s;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
}

.btn-profile:hover {
  background: rgba(13, 148, 136, 0.4);
  transform: scale(1.1);
}

.session-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.session-item {
  padding: 12px;
  margin-bottom: 8px;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.3s;
  background: rgba(255, 255, 255, 0.05);
  position: relative;
}

.session-item:hover {
  background: rgba(13, 148, 136, 0.2);
}

.session-item.active {
  background: rgba(13, 148, 136, 0.3);
  border-left: 3px solid #14B8A6;
}

.session-title {
  color: white;
  font-size: 14px;
  margin-bottom: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  padding-right: 32px;
}

.session-time {
  color: rgba(255, 255, 255, 0.5);
  font-size: 12px;
}

.btn-delete-session {
  position: absolute;
  right: 8px;
  top: 50%;
  transform: translateY(-50%);
  background: none;
  border: none;
  font-size: 16px;
  cursor: pointer;
  opacity: 0.7;
  transition: opacity 0.2s;
  padding: 4px;
}

.btn-delete-session:hover {
  opacity: 1;
  color: #ef4444;
}

.empty-sessions {
  text-align: center;
  color: rgba(255, 255, 255, 0.5);
  padding: 32px 16px;
  font-size: 14px;
}

.sidebar-footer {
  padding: 16px;
  border-top: 1px solid rgba(13, 148, 136, 0.2);
}

.btn-logout {
  width: 100%;
  padding: 12px;
  background: rgba(239, 68, 68, 0.1);
  color: #EF4444;
  border: 1px solid rgba(239, 68, 68, 0.3);
  border-radius: 8px;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.3s;
}

.btn-logout:hover {
  background: rgba(239, 68, 68, 0.2);
}

/* 中间聊天区域 */
.main-chat {
  flex: 1;
  position: relative;
  display: flex;
  flex-direction: column;
  background: #0F172A;
}

.bg-canvas {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
  z-index: 0;
}

.chat-container {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  height: 100%;
}

.messages-container {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
  scroll-behavior: smooth;
}

.turn {
  margin-bottom: 32px;
}

.divider {
  text-align: center;
  color: rgba(255, 255, 255, 0.4);
  font-size: 12px;
  margin: 24px 0;
  padding: 8px;
}

.message {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
}

.user-message {
  justify-content: flex-end;
}

.user-message .message-content {
  background: linear-gradient(135deg, #0D9488, #14B8A6);
  color: white;
  padding: 12px 16px;
  border-radius: 16px 16px 4px 16px;
  max-width: 70%;
}

.bot-message {
  justify-content: flex-start;
}

.message-avatar {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  overflow: hidden;
  flex-shrink: 0;
}

.message-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

/* Emoji头像样式 */
.message-avatar-emoji {
  background: linear-gradient(135deg, #0d9488, #14b8a6);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
}

.bot-message .message-content {
  background: rgba(255, 255, 255, 0.05);
  backdrop-filter: blur(10px);
  padding: 12px 16px;
  border-radius: 4px 16px 16px 16px;
  max-width: 70%;
  border: 1px solid rgba(13, 148, 136, 0.2);
}

.bot-name {
  color: #14B8A6;
  font-size: 12px;
  font-weight: 500;
  margin-bottom: 8px;
}

.message-text {
  color: white;
  line-height: 1.6;
  font-size: 14px;
}

.product-cards {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-top: 12px;
}

.product-card {
  display: flex;
  gap: 12px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(13, 148, 136, 0.3);
  border-radius: 8px;
  padding: 12px;
  transition: all 0.3s;
}

.product-card:hover {
  background: rgba(13, 148, 136, 0.1);
  transform: translateY(-2px);
}

.product-image {
  width: 80px;
  height: 80px;
  object-fit: cover;
  border-radius: 6px;
}

.product-info {
  flex: 1;
}

.product-title {
  color: white;
  font-weight: 500;
  margin-bottom: 4px;
  font-size: 14px;
}

.product-brand {
  color: rgba(255, 255, 255, 0.6);
  font-size: 12px;
  margin-bottom: 8px;
}

.product-price {
  color: #14B8A6;
  font-weight: bold;
  font-size: 16px;
}

.product-stock {
  color: rgba(255, 255, 255, 0.5);
  font-size: 12px;
  margin-top: 4px;
}

.message-actions {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}

.btn-action {
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.2);
  color: white;
  padding: 6px 12px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 12px;
  transition: all 0.3s;
}

.btn-action:hover {
  background: rgba(13, 148, 136, 0.2);
}

.input-area {
  padding: 16px 24px;
  background: rgba(15, 23, 42, 0.95);
  border-top: 1px solid rgba(13, 148, 136, 0.3);
  display: flex;
  gap: 12px;
  align-items: flex-end;
}

.input-area textarea {
  flex: 1;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(13, 148, 136, 0.3);
  border-radius: 8px;
  padding: 12px;
  color: white;
  font-size: 14px;
  resize: none;
  font-family: inherit;
}

.input-area textarea:focus {
  outline: none;
  border-color: #14B8A6;
}

.btn-send {
  padding: 12px 24px;
  background: linear-gradient(135deg, #0D9488, #14B8A6);
  color: white;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  transition: all 0.3s;
}

.btn-send:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(13, 148, 136, 0.4);
}

.btn-send:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.loading, .error-message {
  text-align: center;
  padding: 16px;
  color: rgba(255, 255, 255, 0.6);
  font-size: 14px;
}

.error-message {
  color: #EF4444;
}

/* 右侧栏 */
.sidebar-right {
  width: 340px;
  background: rgba(15, 23, 42, 0.95);
  border-left: 1px solid rgba(13, 148, 136, 0.3);
  display: flex;
  flex-direction: column;
  backdrop-filter: blur(10px);
}

.tabs {
  display: flex;
  border-bottom: 1px solid rgba(13, 148, 136, 0.2);
}

.tabs button {
  flex: 1;
  padding: 16px;
  background: transparent;
  color: rgba(255, 255, 255, 0.6);
  border: none;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.3s;
}

.tabs button.active {
  color: #14B8A6;
  border-bottom: 2px solid #14B8A6;
}

.tab-content {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

/* 订单容器（带展开/收起） */
.order-container {
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(13, 148, 136, 0.2);
  border-radius: 8px;
  margin-bottom: 12px;
  overflow: hidden;
  transition: all 0.3s;
}

.order-container:hover {
  background: rgba(13, 148, 136, 0.1);
  border-color: rgba(13, 148, 136, 0.4);
}

.order-header {
  display: flex;
  align-items: center;
  padding: 12px;
  cursor: pointer;
  gap: 12px;
  user-select: none;
}

.expand-icon {
  color: #14B8A6;
  font-size: 12px;
  transition: transform 0.3s;
  flex-shrink: 0;
}

.expand-icon.expanded {
  transform: rotate(90deg);
}

.order-summary {
  flex: 1;
  min-width: 0;
}

.order-id {
  color: white;
  font-weight: 500;
  margin-bottom: 6px;
  font-size: 14px;
}

.order-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}

.order-status {
  color: rgba(255, 255, 255, 0.6);
  font-size: 12px;
  padding: 2px 8px;
  background: rgba(255, 255, 255, 0.1);
  border-radius: 4px;
}

.order-total {
  color: #14B8A6;
  font-weight: bold;
  font-size: 16px;
}

/* 订单商品明细 */
.order-items {
  border-top: 1px solid rgba(13, 148, 136, 0.2);
  padding: 12px;
  background: rgba(0, 0, 0, 0.2);
}

.order-product-item {
  display: flex;
  gap: 12px;
  padding: 8px;
  background: rgba(255, 255, 255, 0.03);
  border-radius: 6px;
  margin-bottom: 8px;
}

.order-product-item:last-child {
  margin-bottom: 0;
}

.product-thumb {
  width: 60px;
  height: 60px;
  border-radius: 4px;
  flex-shrink: 0;
  overflow: hidden;
  background: rgba(255, 255, 255, 0.05);
  display: flex;
  align-items: center;
  justify-content: center;
}

.product-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.product-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.product-name {
  color: white;
  font-size: 13px;
  font-weight: 500;
  /* 2行省略显示 */
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  text-overflow: ellipsis;
  line-height: 1.4;
  word-break: break-word;
  cursor: help;
}

.product-specs {
  color: rgba(255, 255, 255, 0.5);
  font-size: 11px;
  display: flex;
  gap: 8px;
}

.product-specs span {
  padding: 2px 6px;
  background: rgba(255, 255, 255, 0.1);
  border-radius: 3px;
}

.product-price-qty {
  display: flex;
  justify-content: space-between;
  align-items: center;
  color: #14B8A6;
  font-size: 12px;
  font-weight: 500;
}

.empty-items {
  text-align: center;
  color: rgba(255, 255, 255, 0.4);
  font-size: 12px;
  padding: 16px;
}

/* 保留旧的 product-item 样式（用于其他地方） */
.product-item {
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(13, 148, 136, 0.2);
  border-radius: 8px;
  padding: 12px;
  margin-bottom: 12px;
  cursor: pointer;
  transition: all 0.3s;
  display: flex;
  gap: 12px;
}

.product-item:hover {
  background: rgba(13, 148, 136, 0.1);
  transform: translateX(-4px);
}

.product-item img {
  width: 60px;
  height: 60px;
  object-fit: cover;
  border-radius: 6px;
}

.product-details {
  flex: 1;
}

.product-name {
  color: white;
  font-size: 14px;
  margin-bottom: 4px;
}

.product-price {
  color: #14B8A6;
  font-weight: bold;
  font-size: 14px;
}

.empty {
  text-align: center;
  color: rgba(255, 255, 255, 0.5);
  padding: 32px 16px;
  font-size: 14px;
}

/* 响应式设计 */
@media (max-width: 1024px) {
  .sidebar-right {
    width: 280px;
  }
}

@media (max-width: 768px) {
  .sidebar-left {
    position: absolute;
    left: 0;
    top: 0;
    height: 100%;
    z-index: 100;
    transform: translateX(-100%);
  }

  .sidebar-left.show {
    transform: translateX(0);
  }

  .sidebar-right {
    position: absolute;
    right: 0;
    top: 0;
    height: 100%;
    z-index: 100;
    transform: translateX(100%);
  }

  .sidebar-right.show {
    transform: translateX(0);
  }
}
</style>