<template>
  <section class="page-card">
    <div class="page-head">
      <div>
        <p class="eyebrow">{{ roleText(user?.role) }}工作台</p>
        <h1>{{ title }}</h1>
        <p class="muted">{{ description }}</p>
      </div>
      <RouterLink v-if="user?.role === 'APPLICANT'" to="/new" class="action-link">新建申请</RouterLink>
    </div>

    <div class="toolbar">
      <select v-model="filters.status" @change="load">
        <option value="">全部状态</option>
        <option value="DRAFT">草稿</option>
        <option value="PENDING">待审核</option>
        <option value="APPROVED">通过</option>
        <option value="REJECTED">不通过</option>
        <option value="NEED_MANUAL_REVIEW">人工复核</option>
        <option value="WITHDRAWN">已撤回</option>
      </select>
      <input v-model.trim="filters.keyword" placeholder="搜索申请人、证件号、项目名称" @keyup.enter="load" />
      <button class="btn-inline" @click="load" :disabled="loading">{{ loading ? "查询中..." : "刷新列表" }}</button>
    </div>

    <p v-if="error" class="error">{{ error }}</p>

    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>ID</th><th>申请人</th><th>项目名称</th><th>状态</th><th>提交时间</th><th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="!loading && list.length === 0"><td colspan="6">暂无申请记录</td></tr>
          <tr v-for="item in list" :key="item.id">
            <td>{{ item.id }}</td>
            <td><strong>{{ item.applicantName }}</strong><small>{{ item.idNumber }}</small></td>
            <td>{{ item.projectName || "-" }}</td>
            <td><span class="status-pill" :class="`status-${item.status}`">{{ statusText(item.status) }}</span></td>
            <td>{{ formatTime(item.submissionTime) }}</td>
            <td class="row-actions">
              <button v-if="canReview(item)" class="btn-small" @click="review(item)" :disabled="reviewingId === item.id">
                {{ reviewingId === item.id ? "初审中..." : "开始初审" }}
              </button>
              <button v-if="canWithdraw(item)" class="btn-small secondary" @click="withdraw(item)">撤回</button>
              <RouterLink class="text-link" to="/review">看结果</RouterLink>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <section v-if="selectedResult" class="result-panel">
      <h2>本次 AI 初审结果</h2>
      <p>申请 ID：{{ selectedResult.application_id }}；结论：<strong :class="`status-${selectedResult.ai_status}`">{{ statusText(selectedResult.ai_status) }}</strong></p>
      <div class="issue-grid">
        <article v-for="level in ['高', '中', '低']" :key="level" class="issue-card">
          <h3>{{ level }}风险问题</h3>
          <ul>
            <li v-for="(issue, index) in issuesBySeverity(level)" :key="index">
              <strong>{{ issue.type || "问题" }}</strong>：{{ issue.message }}
              <span v-if="issue.legal_basis">依据：{{ issue.legal_basis }}</span>
              <span v-if="issue.suggestion">建议：{{ issue.suggestion }}</span>
            </li>
            <li v-if="issuesBySeverity(level).length === 0">暂无</li>
          </ul>
        </article>
      </div>
    </section>
  </section>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import { RouterLink } from "vue-router";
import { fetchApplications, formatTime, getSession, reviewApplication, roleText, statusText, withdrawApplication } from "../services/api";

const user = getSession();
const list = ref([]);
const loading = ref(false);
const error = ref("");
const reviewingId = ref(null);
const selectedResult = ref(null);
const filters = reactive({ status: "", keyword: "" });

const title = computed(() => user?.role === "APPLICANT" ? "我的申请" : user?.role === "REVIEWER" ? "审核工作台" : "全部申请");
const description = computed(() => {
  if (user?.role === "APPLICANT") return "申请人只能查看自己创建的申请，可新建、保存草稿、提交或撤回审核前申请。";
  if (user?.role === "REVIEWER") return "审核员可查看所有待审/已审申请，并发起 AI 合规初审。";
  return "管理员可查看全部申请记录，用于系统验收与业务管理。";
});

function canReview(item) {
  return ["REVIEWER", "ADMIN"].includes(user?.role) && ["PENDING", "APPROVED", "REJECTED", "NEED_MANUAL_REVIEW"].includes(item.status);
}

function canWithdraw(item) {
  return user?.role === "APPLICANT" && ["DRAFT", "PENDING"].includes(item.status);
}

function issuesBySeverity(level) {
  return (selectedResult.value?.issues || []).filter((item) => (item.severity || "中") === level);
}

async function load() {
  loading.value = true;
  error.value = "";
  try {
    list.value = await fetchApplications(filters);
  } catch (e) {
    error.value = e.message;
  } finally {
    loading.value = false;
  }
}

async function review(item) {
  reviewingId.value = item.id;
  error.value = "";
  try {
    selectedResult.value = await reviewApplication(item.id);
    await load();
  } catch (e) {
    error.value = e.message;
  } finally {
    reviewingId.value = null;
  }
}

async function withdraw(item) {
  error.value = "";
  try {
    await withdrawApplication(item.id);
    await load();
  } catch (e) {
    error.value = e.message;
  }
}

onMounted(load);
</script>
