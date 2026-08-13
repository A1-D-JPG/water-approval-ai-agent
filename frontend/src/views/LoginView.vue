<template>
  <div class="login-page">
    <section class="login-hero">
      <h1>涉水审批材料 AI 合规初审系统</h1>
    </section>

    <section class="login-card">
      <div class="tabs">
        <button :class="{ active: mode === 'login' }" @click="switchMode('login')">登录</button>
        <button :class="{ active: mode === 'register' }" @click="switchMode('register')">注册</button>
      </div>

      <form @submit.prevent="submit">
        <label>
          用户名
          <input v-model.trim="form.username" required placeholder="请输入用户名" />
        </label>
        <label>
          密码
          <input v-model.trim="form.password" type="password" required placeholder="请输入密码" />
        </label>

        <template v-if="mode === 'register'">
          <label>
            账号类型
            <select v-model="form.userType">
              <option value="PERSONAL">个人申请</option>
              <option value="ENTERPRISE">企业申请</option>
            </select>
          </label>
          <label>
            真实姓名/企业名称
            <input v-model.trim="form.displayName" required placeholder="请输入真实姓名或企业名称" />
          </label>
          <label>
            身份证号
            <input v-model.trim="form.identityNo" required placeholder="请输入身份证号" />
          </label>
          <label v-if="form.userType === 'ENTERPRISE'">
            统一社会信用代码
            <input v-model.trim="form.creditCode" required placeholder="请输入18位统一社会信用代码" />
          </label>
          <label>
            手机号
            <input v-model.trim="form.phone" required placeholder="请输入手机号" />
          </label>
          <label>
            邮箱
            <input v-model.trim="form.email" type="email" required placeholder="请输入邮箱" />
          </label>
        </template>

        <button :disabled="loading">{{ loading ? "处理中..." : mode === "login" ? "进入系统" : "提交注册" }}</button>
      </form>

      <p v-if="message" class="toast success">{{ message }}</p>
      <p v-if="error" class="error">{{ error }}</p>
    </section>
  </div>
</template>

<script setup>
import { reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { loginUser, registerUser, saveSession } from "../services/api";

const router = useRouter();
const mode = ref("login");
const loading = ref(false);
const error = ref("");
const message = ref("");
const form = reactive({
  username: "",
  password: "",
  role: "APPLICANT",
  userType: "PERSONAL",
  displayName: "",
  identityNo: "",
  creditCode: "",
  phone: "",
  email: ""
});

function switchMode(nextMode) {
  mode.value = nextMode;
  error.value = "";
  message.value = "";
}

async function submit() {
  loading.value = true;
  error.value = "";
  message.value = "";
  try {
    if (mode.value === "login") {
      const user = await loginUser(form);
      saveSession(user);
      router.push("/");
      return;
    }
    const registerError = validateRegisterForm();
    if (registerError) {
      error.value = registerError;
      return;
    }
    await registerUser(form);
    message.value = "注册申请已提交，请等待管理员激活后登录。";
    mode.value = "login";
  } catch (e) {
    error.value = e.message;
  } finally {
    loading.value = false;
  }
}

function validateRegisterForm() {
  if (!isStrongPassword(form.password)) return "密码至少8位，并且需要包含大写字母、小写字母、数字、特殊字符中的三类。";
  if (!isValidIdCard(form.identityNo)) return "身份证号格式或校验码不正确，请重新输入。";
  if (!/^1[3-9]\d{9}$/.test(form.phone)) return "手机号格式不正确。";
  if (!/^[A-Za-z0-9+_.-]+@[A-Za-z0-9.-]+$/.test(form.email)) return "邮箱格式不正确。";
  if (form.userType === "ENTERPRISE" && !/^[0-9A-Z]{18}$/.test(form.creditCode.toUpperCase())) return "统一社会信用代码必须为18位大写字母或数字。";
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
</script>
