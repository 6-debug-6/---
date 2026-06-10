<template>
  <div class="user-layout">
    <header class="user-header">
      <div class="header-left">
        <router-link to="/" class="logo">设备检修知识系统</router-link>
        <nav class="header-nav">
          <router-link to="/">首页</router-link>
          <router-link to="/chat">AI 助手</router-link>
          <router-link to="/task">作业指引</router-link>
          <router-link to="/tickets">客服工单</router-link>
        </nav>
      </div>
      <div class="header-right">
        <router-link to="/workspace" class="btn-workspace">个人工作台</router-link>
        <span class="user-name">{{ authStore.user?.name }}</span>
        <button class="btn-logout" @click="handleLogout">退出</button>
      </div>
    </header>
    <main class="user-main">
      <router-view />
    </main>
  </div>
</template>

<script setup>
import { useAuthStore } from '@/stores/auth'
import { useRouter } from 'vue-router'

const authStore = useAuthStore()
const router = useRouter()

function handleLogout() {
  authStore.logout()
  router.push('/login')
}
</script>

<style scoped>
.user-layout { min-height: 100vh; background: #f5f7fa; }
.user-header { display: flex; justify-content: space-between; align-items: center; padding: 0 24px; height: 56px; background: #fff; box-shadow: 0 1px 4px rgba(0,0,0,0.08); }
.header-left { display: flex; align-items: center; gap: 32px; }
.logo { font-size: 18px; font-weight: 700; color: #1d4ed8; text-decoration: none; }
.header-nav { display: flex; gap: 20px; }
.header-nav a { color: #555; text-decoration: none; font-size: 14px; }
.header-nav a:hover, .header-nav a.router-link-active { color: #1d4ed8; }
.header-right { display: flex; align-items: center; gap: 16px; }
.btn-workspace { color: #1d4ed8; text-decoration: none; font-size: 14px; }
.user-name { color: #333; font-size: 14px; }
.btn-logout { padding: 4px 12px; border: 1px solid #ddd; border-radius: 4px; background: #fff; cursor: pointer; font-size: 13px; }
.user-main { padding: 24px; max-width: 1400px; margin: 0 auto; }
</style>
