import { createRouter, createWebHistory } from "vue-router";
import { getSession } from "../services/api";
import ListView from "../views/ListView.vue";
import NewView from "../views/NewView.vue";
import ReviewView from "../views/ReviewView.vue";
import LoginView from "../views/LoginView.vue";
import AdminView from "../views/AdminView.vue";
import KnowledgeView from "../views/KnowledgeView.vue";

const routes = [
  { path: "/login", name: "login", component: LoginView, meta: { public: true } },
  { path: "/", name: "list", component: ListView, meta: { roles: ["APPLICANT", "REVIEWER", "ADMIN"] } },
  { path: "/new", name: "new", component: NewView, meta: { roles: ["APPLICANT"] } },
  { path: "/review", name: "review", component: ReviewView, meta: { roles: ["APPLICANT", "REVIEWER", "ADMIN"] } },
  { path: "/knowledge", name: "knowledge", component: KnowledgeView, meta: { roles: ["APPLICANT", "REVIEWER", "ADMIN"] } },
  { path: "/admin", name: "admin", component: AdminView, meta: { roles: ["ADMIN"] } }
];

const router = createRouter({
  history: createWebHistory(),
  routes
});

router.beforeEach((to) => {
  const user = getSession();
  if (to.meta.public) {
    return user ? "/" : true;
  }
  if (!user) {
    return "/login";
  }
  const roles = to.meta.roles || [];
  if (roles.length && !roles.includes(user.role)) {
    return "/";
  }
  return true;
});

export default router;
