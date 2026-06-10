<template>
  <div class="admin-layout">
    <aside class="admin-sidebar">
      <div class="sidebar-logo">管理后台</div>
      <el-menu router :default-active="$route.path" class="sidebar-menu">
        <el-menu-item index="/admin">
          <span>仪表盘</span>
        </el-menu-item>
        <el-menu-item index="/admin/knowledge">
          <span>知识库管理</span>
        </el-menu-item>
        <el-menu-item index="/admin/review">
          <span>审核队列</span>
        </el-menu-item>
        <el-menu-item index="/admin/tickets">
          <span>客服工单</span>
        </el-menu-item>
        <el-menu-item index="/admin/users">
          <span>用户管理</span>
        </el-menu-item>
        <el-menu-item index="/admin/devices">
          <span>设备/模板管理</span>
        </el-menu-item>
        <el-menu-item index="/admin/model-config">
          <span>模型配置</span>
        </el-menu-item>
        <el-menu-item index="/admin/logs">
          <span>操作日志</span>
        </el-menu-item>
        <el-menu-item index="/admin/settings">
          <span>系统设置</span>
        </el-menu-item>
      </el-menu>
    </aside>
    <div class="admin-main">
      <header class="admin-header">
        <span>欢迎，{{ authStore.user?.name }}</span>
        <button class="btn-back" @click="$router.push('/')">返回用户端</button>
        <button class="btn-logout" @click="handleLogout">退出</button>
      </header>
      <div class="admin-content">
        <router-view />
      </div>
    </div>
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
.admin-layout { display: flex; min-height: 100vh; }
.admin-sidebar { width: 220px; background: #1e293b; color: #fff; flex-shrink: 0; }
.sidebar-logo { padding: 20px; font-size: 16px; font-weight: 700; border-bottom: 1px solid #334155; }
.sidebar-menu { border-right: none; }
.admin-main { flex: 1; display: flex; flex-direction: column; }
.admin-header { display: flex; justify-content: flex-end; align-items: center; gap: 16px; padding: 0 24px; height: 56px; background: #fff; box-shadow: 0 1px 4px rgba(0,0,0,0.08); font-size: 14px; }
.btn-back, .btn-logout { padding: 4px 12px; border: 1px solid #ddd; border-radius: 4px; background: #fff; cursor: pointer; font-size: 13px; }
.admin-content { padding: 24px; flex: 1; overflow-y: auto; }
</style>
