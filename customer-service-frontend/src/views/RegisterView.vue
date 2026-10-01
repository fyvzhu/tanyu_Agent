<template>
  <div class="register-page">
    <div class="register-container">
      <div class="register-card">
        <div class="register-header">
          <h1>用户注册</h1>
          <p>创建您的账户以开始使用服务</p>
        </div>

        <form @submit.prevent="handleRegister" class="register-form">
          <div class="form-group">
            <label for="username">用户名</label>
            <input
              id="username"
              v-model="formData.username"
              type="text"
              class="input"
              placeholder="4-20个字符，字母数字下划线"
              required
              minlength="4"
              maxlength="20"
              pattern="[a-zA-Z0-9_]+"
            />
          </div>

          <div class="form-group">
            <label for="nickname">昵称</label>
            <input
              id="nickname"
              v-model="formData.nickname"
              type="text"
              class="input"
              placeholder="请输入昵称"
              required
              minlength="2"
              maxlength="50"
            />
          </div>

          <div class="form-group">
            <label for="password">密码</label>
            <input
              id="password"
              v-model="formData.password"
              type="password"
              class="input"
              placeholder="8-16个字符"
              required
              minlength="8"
              maxlength="16"
            />
          </div>

          <div class="form-group">
            <label for="confirm_password">确认密码</label>
            <input
              id="confirm_password"
              v-model="formData.confirm_password"
              type="password"
              class="input"
              placeholder="请再次输入密码"
              required
              minlength="8"
              maxlength="16"
            />
          </div>

          <div class="form-error" v-if="errorMessage">
            {{ errorMessage }}
          </div>

          <button type="submit" class="btn btn-primary" :disabled="loading">
            {{ loading ? '注册中...' : '注册' }}
          </button>
        </form>

        <div class="register-footer">
          <span>已有账户？</span>
          <router-link to="/login" class="link">立即登录</router-link>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { register } from '@/api/auth'
import { setAccessToken } from '@/utils/auth'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const userStore = useUserStore()

const formData = ref({
  username: '',
  nickname: '',
  password: '',
  confirm_password: '',
})

const loading = ref(false)
const errorMessage = ref('')

async function handleRegister() {
  errorMessage.value = ''

  // 验证两次密码是否一致
  if (formData.value.password !== formData.value.confirm_password) {
    errorMessage.value = '两次输入的密码不一致'
    return
  }

  loading.value = true

  try {
    const res = await register({
      username: formData.value.username,
      nickname: formData.value.nickname,
      password: formData.value.password,
      confirm_password: formData.value.confirm_password,
    })

    if (res.code === 0) {
      // 注册成功，保存 token 和用户信息
      setAccessToken(res.data.access_token)
      userStore.setUser(res.data.user)

      // 跳转到主页
      router.push('/')
    } else {
      errorMessage.value = res.message || '注册失败'
    }
  } catch (error) {
    console.error('注册失败:', error)
    errorMessage.value = error.response?.data?.detail || '注册失败，请稍后重试'
  } finally {
    loading.value = false
  }
}

</script>

<style scoped>
.register-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--login-bg);
  padding: 1rem;
}

.register-container {
  width: 100%;
  max-width: 420px;
}

.register-card {
  background: var(--login-card-bg);
  border: 1px solid var(--login-card-border);
  border-radius: var(--radius-xl);
  padding: 2.5rem;
  box-shadow: var(--shadow-xl);
  backdrop-filter: blur(10px);
}

.register-header {
  text-align: center;
  margin-bottom: 2rem;
}

.register-header h1 {
  font-size: 1.75rem;
  font-weight: 600;
  color: var(--login-title-color);
  margin-bottom: 0.5rem;
}

.register-header p {
  color: var(--login-subtitle-color);
  font-size: 0.95rem;
}

.register-form {
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

.register-footer {
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
  .register-card {
    padding: 1.5rem;
  }

  .register-header h1 {
    font-size: 1.5rem;
  }
}
</style>



