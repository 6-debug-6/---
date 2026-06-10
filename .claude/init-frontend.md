---
name: init-frontend
description: Initialize the Vue 3 + Vite frontend project structure
---

# Frontend 初始化技能

此技能用于初始化 Vue 3 + Vite 前端项目。

## 步骤

1. 使用 Vite 创建 Vue 3 项目：`npm create vite@latest frontend -- --template vue`
2. 安装依赖：
   - vue-router（路由）
   - pinia（状态管理）
   - axios（HTTP 请求）
   - element-plus 或 ant-design-vue（UI 组件库，适合工业场景）
3. 创建目录结构：`views/`, `components/`, `api/`, `router/`, `stores/`
4. 配置路由和全局布局
5. 配置 axios 拦截器（token 注入、错误处理）

## 注意

- 使用 Composition API + `<script setup>` 语法
- UI 组件库选型需考虑工业场景：字体大、对比度高、触摸友好
- 首页搜索入口需支持文本输入 + 图片拖拽上传
