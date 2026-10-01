<template>
  <div class="login-page">
    <div class="login-container">
      <div class="login-card">
        <div class="login-header">
          <h1>用户登录</h1>
          <p>登录您的账户以继续使用服务</p>
        </div>

        <form @submit.prevent="handleLogin" class="login-form">
          <div class="form-group">
            <label for="username">用户名</label>
            <input
              id="username"
              v-model="formData.username"
              type="text"
              class="input"
              placeholder="请输入用户名"
              required
            />
          </div>

          <div class="form-group">
            <label for="password">密码</label>
            <input
              id="password"
              v-model="formData.password"
              type="password"
              class="input"
              placeholder="请输入密码"
              required
            />
          </div>

          <div class="form-error" v-if="errorMessage">
            {{ errorMessage }}
          </div>

          <button type="submit" class="btn btn-primary" :disabled="loading">
            {{ loading ? '登录中...' : '登录' }}
          </button>
        </form>

        <div class="login-footer">
          <span>还没有账户？</span>
          <router-link to="/register" class="link">立即注册</router-link>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { login } from '@/api/auth'
import { setAccessToken } from '@/utils/auth'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()

const formData = ref({
  username: '',
  password: '',
})

const loading = ref(false)
const errorMessage = ref('')

async function handleLogin() {
  errorMessage.value = ''
  loading.value = true

  try {
    const res = await login({
      username: formData.value.username,
      password: formData.value.password,
    })

    // 后端返回 { success: true, data: { access_token, user } }
    if (res.success && res.data) {
      setAccessToken(res.data.access_token)
      userStore.setUser(res.data.user)
      const redirect = route.query.redirect || '/'
      router.push(redirect)
    } else {
      errorMessage.value = res.error?.message || '登录失败'
    }
  } catch (error) {
    console.error('登录失败:', error)
    errorMessage.value = error.response?.data?.detail || '登录失败，请稍后重试'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--login-bg);
  padding: 1rem;
}

.login-container {
  width: 100%;
  max-width: 420px;
}

.login-card {
  background: var(--login-card-bg);
  border: 1px solid var(--login-card-border);
  border-radius: var(--radius-xl);
  padding: 2.5rem;
  box-shadow: var(--shadow-xl);
  backdrop-filter: blur(10px);
}

.login-header {
  text-align: center;
  margin-bottom: 2rem;
}

.login-header h1 {
  font-size: 1.75rem;
  font-weight: 600;
  color: var(--login-title-color);
  margin-bottom: 0.5rem;
}

.login-header p {
  color: var(--login-subtitle-color);
  font-size: 0.95rem;
}

.login-form {
  margin-bottom: 1.5rem;
}

.form-group {
  margin-bottom: 1.25rem;
}

.form-group label {
  display: block;
  margin-bottom: 0.5rem;
  color: var(--text-secondary);
  font-size: 0.9rem;
  font-weight: 500;
}

.form-error {
  color: var(--error-color);
  font-size: 0.875rem;
  margin-bottom: 1rem;
  padding: 0.75rem;
  background: rgba(239, 68, 68, 0.1);
  border-radius: var(--radius-md);
  border: 1px solid rgba(239, 68, 68, 0.3);
}

.login-footer {
  text-align: center;
  color: var(--login-text-color);
  font-size: 0.9rem;
}

.link {
  color: var(--login-link-color);
  text-decoration: none;
  margin-left: 0.5rem;
  font-weight: 500;
  transition: all 0.3s ease;
}

.link:hover {
  color: var(--primary-light);
  text-decoration: underline;
}

@media (max-width: 480px) {
  .login-card {
    padding: 1.5rem;
  }

  .login-header h1 {
    font-size: 1.5rem;
  }
}
</style>
