<template>
  <div class="app-shell">
    <aside v-if="user" class="sidebar">
      <div class="brand">
        <span class="brand-mark">水</span>
        <div>
          <strong>涉水审批 AI 初审</strong>
          <small>{{ roleText(user.role) }}</small>
        </div>
      </div>

      <nav class="nav">
        <RouterLink v-for="item in navItems" :key="item.path" :to="item.path" class="nav-link">
          {{ item.label }}
        </RouterLink>
      </nav>

      <div class="user-card">
        <strong>{{ user.displayName || user.username }}</strong>
        <span>{{ user.username }}</span>
        <button class="btn-small secondary" @click="logout">退出登录</button>
      </div>
    </aside>

    <main :class="user ? 'main-content' : 'login-content'">
      <RouterView />
    </main>
  </div>
</template>

<script setup>
import { computed } from "vue";
import { RouterLink, RouterView, useRoute, useRouter } from "vue-router";
import { clearSession, getSession, roleText } from "./services/api";

const route = useRoute();
const router = useRouter();
const user = computed(() => {
  route.fullPath;
  return getSession();
});

const navItems = computed(() => {
  const role = user.value?.role;
  if (role === "APPLICANT") {
    return [
      { path: "/", label: "我的申请" },
      { path: "/new", label: "新建申请" },
      { path: "/review", label: "初审结果" },
      { path: "/knowledge", label: "法规知识检索" }
    ];
  }
  if (role === "REVIEWER") {
    return [
      { path: "/", label: "审核工作台" },
      { path: "/review", label: "初审结果" },
      { path: "/knowledge", label: "法规知识检索" }
    ];
  }
  if (role === "ADMIN") {
    return [
      { path: "/", label: "全部申请" },
      { path: "/admin", label: "管理看板" },
      { path: "/review", label: "初审结果" },
      { path: "/knowledge", label: "法规知识检索" }
    ];
  }
  return [];
});

function logout() {
  clearSession();
  router.push("/login");
}
</script>
