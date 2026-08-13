<template>
  <section class="page-card">
    <div class="page-head">
      <div>
        <p class="eyebrow">管理员功能</p>
        <h1>系统管理看板</h1>
        <p class="muted">查看申请统计、服务健康状态、用户管理和操作日志。</p>
      </div>
      <button class="btn-inline" @click="load" :disabled="loading">{{ loading ? "刷新中..." : "刷新看板" }}</button>
    </div>

    <p v-if="error" class="error">{{ error }}</p>

    <div class="summary">
      <div class="metric"><h3>总申请</h3><p>{{ stats.total || 0 }}</p></div>
      <div class="metric"><h3>待审核</h3><p>{{ stats.pending || 0 }}</p></div>
      <div class="metric"><h3>通过</h3><p>{{ stats.approved || 0 }}</p></div>
      <div class="metric"><h3>不通过</h3><p>{{ stats.rejected || 0 }}</p></div>
    </div>

    <section class="result-panel">
      <h2>服务健康状态</h2>
      <div class="health-grid">
        <span>Java 后端：{{ health.java || "-" }}</span>
        <span>数据库：{{ health.database || "-" }}</span>
        <span>Python AI 服务：{{ health.python?.status || "-" }}</span>
      </div>
    </section>

    <section class="result-panel">
      <h2>最近操作日志</h2>
      <div class="table-wrap">
        <table>
          <thead><tr><th>时间</th><th>用户ID</th><th>动作</th><th>对象ID</th><th>说明</th></tr></thead>
          <tbody>
            <tr v-for="log in stats.auditLogs || []" :key="log.id">
              <td>{{ formatTime(log.createdAt) }}</td>
              <td>{{ log.userId || "-" }}</td>
              <td>{{ log.action }}</td>
              <td>{{ log.targetId || "-" }}</td>
              <td>{{ log.message || "-" }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section class="result-panel">
      <h2>用户管理</h2>
      <form class="admin-user-form" @submit.prevent="createUser">
        <select v-model="userForm.role">
          <option value="APPLICANT">申请人</option>
          <option value="REVIEWER">审核员</option>
          <option value="ADMIN">管理员</option>
        </select>
        <select v-model="userForm.userType">
          <option value="PERSONAL">个人</option>
          <option value="ENTERPRISE">企业</option>
        </select>
        <input v-model.trim="userForm.username" placeholder="用户名" required />
        <input v-model.trim="userForm.password" type="password" placeholder="强密码" required />
        <input v-model.trim="userForm.displayName" placeholder="真实姓名/企业名称" required />
        <input v-model.trim="userForm.identityNo" placeholder="身份证号" required />
        <input v-if="userForm.userType === 'ENTERPRISE'" v-model.trim="userForm.creditCode" placeholder="统一社会信用代码" required />
        <input v-model.trim="userForm.phone" placeholder="手机号" required />
        <input v-model.trim="userForm.email" type="email" placeholder="邮箱" required />
        <button :disabled="loading">创建用户</button>
      </form>

      <div class="table-wrap">
        <table>
          <thead><tr><th>ID</th><th>用户名</th><th>姓名/企业</th><th>角色</th><th>账号状态</th><th>操作</th></tr></thead>
          <tbody>
            <tr v-for="item in users" :key="item.id">
              <td>{{ item.id }}</td>
              <td>{{ item.username }}</td>
              <td>{{ item.displayName }}</td>
              <td>
                <select v-model="roleDrafts[item.id]" class="role-select">
                  <option value="APPLICANT">申请人</option>
                  <option value="REVIEWER">审核员</option>
                  <option value="ADMIN">管理员</option>
                </select>
              </td>
              <td>{{ item.accountStatus }}</td>
              <td>
                <button class="btn-small secondary" @click="saveRole(item)" :disabled="roleDrafts[item.id] === item.role">保存角色</button>
                <button v-if="item.accountStatus !== 'ACTIVE'" class="btn-small" @click="activate(item.id)">激活</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </section>
</template>

<script setup>
import { onMounted, reactive, ref } from "vue";
import { activateUser, createUserByAdmin, fetchHealth, fetchStats, fetchUsers, formatTime, updateUserRole } from "../services/api";

const loading = ref(false);
const error = ref("");
const stats = ref({});
const health = ref({});
const users = ref([]);
const roleDrafts = reactive({});
const userForm = reactive({ role: "REVIEWER", userType: "PERSONAL", username: "", password: "", displayName: "", identityNo: "", creditCode: "", phone: "", email: "" });

async function load() {
  loading.value = true;
  error.value = "";
  try {
    stats.value = await fetchStats();
    health.value = await fetchHealth();
    users.value = await fetchUsers();
    syncRoleDrafts();
  } catch (e) {
    error.value = e.message;
  } finally {
    loading.value = false;
  }
}

async function createUser() {
  loading.value = true;
  error.value = "";
  try {
    const formError = validateAdminUserForm();
    if (formError) {
      error.value = formError;
      return;
    }
    await createUserByAdmin(userForm);
    Object.assign(userForm, { role: "REVIEWER", userType: "PERSONAL", username: "", password: "", displayName: "", identityNo: "", creditCode: "", phone: "", email: "" });
    users.value = await fetchUsers();
    syncRoleDrafts();
  } catch (e) {
    error.value = e.message;
  } finally {
    loading.value = false;
  }
}

function syncRoleDrafts() {
  users.value.forEach((item) => { roleDrafts[item.id] = item.role; });
}

async function saveRole(item) {
  loading.value = true;
  error.value = "";
  try {
    await updateUserRole(item.id, roleDrafts[item.id]);
    users.value = await fetchUsers();
    syncRoleDrafts();
  } catch (e) {
    error.value = e.message;
  } finally {
    loading.value = false;
  }
}

async function activate(id) {
  loading.value = true;
  error.value = "";
  try {
    await activateUser(id);
    users.value = await fetchUsers();
    syncRoleDrafts();
  } catch (e) {
    error.value = e.message;
  } finally {
    loading.value = false;
  }
}

function validateAdminUserForm() {
  if (!isStrongPassword(userForm.password)) return "密码至少8位，并且需要包含大写字母、小写字母、数字、特殊字符中的三类。";
  if (!isValidIdCard(userForm.identityNo)) return "身份证号格式或校验码不正确。";
  if (!/^1[3-9]\d{9}$/.test(userForm.phone)) return "手机号格式不正确。";
  if (!/^[A-Za-z0-9+_.-]+@[A-Za-z0-9.-]+$/.test(userForm.email)) return "邮箱格式不正确。";
  if (userForm.userType === "ENTERPRISE" && !/^[0-9A-Z]{18}$/.test(userForm.creditCode.toUpperCase())) return "统一社会信用代码必须为18位大写字母或数字。";
  return "";
}

function isStrongPassword(password) {
  if (password.length < 8) return false;
  let count = 0;
  if (/[A-Z]/.test(password)) count += 1;
  if (/[a-z]/.test(password)) count += 1;
  if (/\d/.test(password)) count += 1;
  if (/[^A-Za-z0-9]/.test(password)) count += 1;
  return count >= 3;
}

function isValidIdCard(value) {
  const id = value.trim().toUpperCase();
  if (!/^[1-9]\d{5}(18|19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\d{3}[0-9X]$/.test(id)) return false;
  const year = Number(id.slice(6, 10));
  const month = Number(id.slice(10, 12));
  const day = Number(id.slice(12, 14));
  const date = new Date(year, month - 1, day);
  if (date.getFullYear() !== year || date.getMonth() !== month - 1 || date.getDate() !== day) return false;
  const weights = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2];
  const checkCodes = ["1", "0", "X", "9", "8", "7", "6", "5", "4", "3", "2"];
  const sum = weights.reduce((total, weight, index) => total + Number(id[index]) * weight, 0);
  return checkCodes[sum % 11] === id[17];
}

onMounted(load);
</script>
