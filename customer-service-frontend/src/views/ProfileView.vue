<template>
  <div class="profile-page">
    <div class="profile-container">
      <div class="profile-header">
        <h1>个人信息</h1>
        <p>管理您的账户信息</p>
      </div>

      <el-form :model="formData" label-width="100px" label-position="left" class="profile-form">
        <el-form-item label="用户名">
          <el-input v-model="formData.username" disabled />
        </el-form-item>

        <el-form-item label="昵称">
          <el-input v-model="formData.nickname" placeholder="请输入昵称" />
        </el-form-item>

        <el-form-item label="手机号">
          <el-input v-model="formData.phone_number" placeholder="请输入手机号" />
        </el-form-item>

        <el-form-item label="邮箱">
          <el-input v-model="formData.email" type="email" placeholder="请输入邮箱" />
        </el-form-item>

        <el-form-item label="会员等级">
          <el-select v-model="formData.level" placeholder="请选择会员等级">
            <el-option label="普通用户" value="普通用户" />
            <el-option label="PLUS用户" value="PLUS" />
          </el-select>
        </el-form-item>

        <el-form-item>
          <el-button type="primary" @click="handleSave" :loading="loading">保存</el-button>
          <el-button @click="handleCancel">取消</el-button>
        </el-form-item>
      </el-form>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { getUserProfile, updateUserProfile } from '@/api/auth'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const userStore = useUserStore()
const loading = ref(false)

const formData = ref({
  username: '',
  nickname: '',
  phone_number: '',
  email: '',
  level: '普通用户',
})

onMounted(async () => {
  try {
    const res = await getUserProfile()
    if (res.success && res.data) {
      formData.value = {
        username: res.data.username || '',
        nickname: res.data.nickname || '',
        phone_number: res.data.phone_number || '',
        email: res.data.email || '',
        level: res.data.level || '普通用户',
      }
    }
  } catch (error) {
    ElMessage.error('获取用户信息失败：' + (error.message || '未知错误'))
  }
})

async function handleSave() {
  loading.value = true
  try {
    const res = await updateUserProfile({
      nickname: formData.value.nickname,
      phone_number: formData.value.phone_number,
      email: formData.value.email,
      level: formData.value.level,
    })

    if (res.success) {
      // 更新 store 中的用户信息
      userStore.setUser(res.data)
      ElMessage.success('保存成功')
      router.push('/')
    } else {
      ElMessage.error(res.error?.message || '保存失败')
    }
  } catch (error) {
    ElMessage.error('保存失败：' + (error.message || '未知错误'))
  } finally {
    loading.value = false
  }
}

function handleCancel() {
  router.back()
}
</script>

<style scoped>
.profile-page {
  min-height: 100vh;
  background: linear-gradient(135deg, #0F172A 0%, #1E293B 100%);
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 40px 20px;
}

.profile-container {
  width: 100%;
  max-width: 600px;
  background: rgba(30, 41, 59, 0.95);
  backdrop-filter: blur(10px);
  border: 1px solid rgba(13, 148, 136, 0.3);
  border-radius: 12px;
  padding: 40px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
}

.profile-header {
  text-align: center;
  margin-bottom: 32px;
}

.profile-header h1 {
  color: white;
  font-size: 28px;
  margin-bottom: 8px;
}

.profile-header p {
  color: rgba(255, 255, 255, 0.6);
  font-size: 14px;
}

.profile-form {
  margin-top: 24px;
}

:deep(.el-form-item__label) {
  color: rgba(255, 255, 255, 0.9) !important;
  font-weight: 500;
}

:deep(.el-input__wrapper) {
  background-color: rgba(15, 23, 42, 0.6) !important;
  box-shadow: 0 0 0 1px rgba(13, 148, 136, 0.3) inset !important;
}

:deep(.el-input__wrapper:hover) {
  box-shadow: 0 0 0 1px rgba(13, 148, 136, 0.5) inset !important;
}

:deep(.el-input__wrapper.is-focus) {
  box-shadow: 0 0 0 1px #14B8A6 inset !important;
}

:deep(.el-input__inner) {
  color: white !important;
}

:deep(.el-input__inner::placeholder) {
  color: rgba(255, 255, 255, 0.4);
}

:deep(.el-input.is-disabled .el-input__wrapper) {
  background-color: rgba(15, 23, 42, 0.3) !important;
}

:deep(.el-input.is-disabled .el-input__inner) {
  color: rgba(255, 255, 255, 0.5) !important;
}

:deep(.el-select .el-input__wrapper) {
  background-color: rgba(15, 23, 42, 0.6) !important;
}

:deep(.el-button--primary) {
  background: linear-gradient(135deg, #0D9488, #14B8A6);
  border: none;
  font-weight: 500;
}

:deep(.el-button--primary:hover) {
  background: linear-gradient(135deg, #14B8A6, #0D9488);
}

:deep(.el-button--default) {
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.2);
  color: white;
}

:deep(.el-button--default:hover) {
  background: rgba(255, 255, 255, 0.15);
  border-color: rgba(255, 255, 255, 0.3);
}
</style>
