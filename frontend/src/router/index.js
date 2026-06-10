import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const routes = [
  // 用户端路由
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/Login.vue'),
    meta: { guest: true },
  },
  {
    path: '/register',
    name: 'Register',
    component: () => import('@/views/Register.vue'),
    meta: { guest: true },
  },
  {
    path: '/',
    component: () => import('@/layouts/UserLayout.vue'),
    meta: { requiresAuth: true, role: 'user' },
    children: [
      { path: '', name: 'Home', component: () => import('@/views/user/Home.vue') },
      { path: 'search', name: 'SearchResult', component: () => import('@/views/user/SearchResult.vue') },
      { path: 'knowledge/:id', name: 'KnowledgeDetail', component: () => import('@/views/user/KnowledgeDetail.vue') },
      { path: 'chat', name: 'Chat', component: () => import('@/views/user/Chat.vue') },
      { path: 'chat/:id', name: 'ChatDetail', component: () => import('@/views/user/Chat.vue') },
      { path: 'task', name: 'TaskList', component: () => import('@/views/user/TaskList.vue') },
      { path: 'task/:id', name: 'TaskExecute', component: () => import('@/views/user/TaskExecute.vue') },
      { path: 'upload', name: 'CaseUpload', component: () => import('@/views/user/CaseUpload.vue') },
      { path: 'tickets', name: 'MyTickets', component: () => import('@/views/user/TicketList.vue') },
      { path: 'tickets/:id', name: 'TicketDetail', component: () => import('@/views/user/TicketDetail.vue') },
      { path: 'workspace', name: 'Workspace', component: () => import('@/views/user/Workspace.vue') },
    ],
  },
  // 管理端路由
  {
    path: '/admin',
    component: () => import('@/layouts/AdminLayout.vue'),
    meta: { requiresAuth: true, role: 'admin' },
    children: [
      { path: '', name: 'Dashboard', component: () => import('@/views/admin/Dashboard.vue') },
      { path: 'knowledge', name: 'KnowledgeManage', component: () => import('@/views/admin/KnowledgeManage.vue') },
      { path: 'knowledge/new', name: 'KnowledgeNew', component: () => import('@/views/admin/KnowledgeEdit.vue') },
      { path: 'knowledge/:id/edit', name: 'KnowledgeEdit', component: () => import('@/views/admin/KnowledgeEdit.vue') },
      { path: 'knowledge/:id/versions', name: 'KnowledgeVersions', component: () => import('@/views/admin/KnowledgeVersions.vue') },
      { path: 'review', name: 'ReviewQueue', component: () => import('@/views/admin/ReviewQueue.vue') },
      { path: 'review/:id', name: 'ReviewDetail', component: () => import('@/views/admin/ReviewDetail.vue') },
      { path: 'tickets', name: 'TicketManage', component: () => import('@/views/admin/TicketManage.vue') },
      { path: 'tickets/:id', name: 'TicketManageDetail', component: () => import('@/views/admin/TicketManageDetail.vue') },
      { path: 'users', name: 'UserManage', component: () => import('@/views/admin/UserManage.vue') },
      { path: 'devices', name: 'DeviceManage', component: () => import('@/views/admin/DeviceManage.vue') },
      { path: 'templates', name: 'TemplateManage', component: () => import('@/views/admin/TemplateManage.vue') },
      { path: 'model-config', name: 'ModelConfig', component: () => import('@/views/admin/ModelConfig.vue') },
      { path: 'logs', name: 'AuditLogs', component: () => import('@/views/admin/AuditLogs.vue') },
      { path: 'settings', name: 'SystemSettings', component: () => import('@/views/admin/SystemSettings.vue') },
    ],
  },
  // 403 无权限
  { path: '/403', name: 'Forbidden', component: () => import('@/views/Forbidden.vue') },
  // 404
  { path: '/:pathMatch(.*)*', name: 'NotFound', component: () => import('@/views/NotFound.vue') },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to, from, next) => {
  const authStore = useAuthStore()
  if (to.meta.requiresAuth && !authStore.isLoggedIn) {
    next({ name: 'Login', query: { redirect: to.fullPath } })
  } else if (to.meta.role && authStore.user?.role !== to.meta.role && authStore.user?.role !== 'admin') {
    next({ name: 'Forbidden' })
  } else {
    next()
  }
})

export default router
