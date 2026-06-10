<template>
  <div class="register-page">
    <div class="register-card">
      <h2>用户注册</h2>
      <el-form :model="form" label-width="80px">
        <el-form-item label="用户名"><el-input v-model="form.username" /></el-form-item>
        <el-form-item label="密码"><el-input v-model="form.password" type="password" show-password /></el-form-item>
        <el-form-item label="姓名"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="工号"><el-input v-model="form.employee_id" /></el-form-item>
        <el-form-item label="所属班组"><el-input v-model="form.team" /></el-form-item>
        <el-form-item>
          <el-button type="primary" @click="handleRegister" :loading="loading" style="width:100%">注册</el-button>
        </el-form-item>
      </el-form>
      <p>已有账号？<router-link to="/login">去登录</router-link></p>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

const authStore = useAuthStore()
const router = useRouter()
const loading = ref(false)
const form = ref({ username: '', password: '', name: '', employee_id: '', team: '' })

async function handleRegister() {
  loading.value = true
  try {
    await authStore.register(form.value)
    ElMessage.success('注册成功，请等待管理员审核')
    router.push('/login')
  } catch { /* interceptor handles error */ }
  finally { loading.value = false }
}
</script>

<style scoped>
.register-page { display: flex; justify-content: center; align-items: center; min-height: 100vh; background: #f0f2f5; }
.register-card { width: 420px; padding: 40px; background: #fff; border-radius: 8px; box-shadow: 0 2px 12px rgba(0,0,0,0.08); }
.register-card h2 { text-align: center; margin-bottom: 24px; color: #1d4ed8; }
</style>
