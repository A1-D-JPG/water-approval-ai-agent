<template>
  <section class="page-card">
    <div class="page-head">
      <div>
        <p class="eyebrow">初审结果</p>
        <h1>{{ user?.role === "APPLICANT" ? "我的初审结果" : "申请初审结果" }}</h1>
        <p class="muted">按角色展示可访问的审查记录；申请人只看到自己的结果，审核员可查看待审/已审范围。</p>
      </div>
      <button class="btn-inline" @click="load" :disabled="loading">{{ loading ? "加载中..." : "刷新结果" }}</button>
    </div>

    <p v-if="error" class="error">{{ error }}</p>

    <div class="review-list">
      <article v-for="item in reviewedList" :key="item.id" class="review-item">
        <header>
          <div>
            <strong>#{{ item.id }} {{ item.projectName || item.applicantName }}</strong>
            <span>{{ item.applicantName }} · {{ formatTime(item.reviewTime || item.submissionTime) }}</span>
          </div>
          <span class="status-pill" :class="`status-${item.status}`">{{ statusText(item.status) }}</span>
        </header>

        <template v-if="parseReviewResult(item.reviewResult)">
          <div v-if="parseReviewResult(item.reviewResult).risk_summary" class="summary mini-summary">
            <div class="metric">
              <h3>问题总数</h3>
              <p>{{ parseReviewResult(item.reviewResult).risk_summary.total }}</p>
            </div>
            <div class="metric">
              <h3>高风险</h3>
              <p>{{ parseReviewResult(item.reviewResult).risk_summary.by_severity?.高 || 0 }}</p>
            </div>
            <div class="metric">
              <h3>中风险</h3>
              <p>{{ parseReviewResult(item.reviewResult).risk_summary.by_severity?.中 || 0 }}</p>
            </div>
            <div class="metric">
              <h3>低风险</h3>
              <p>{{ parseReviewResult(item.reviewResult).risk_summary.by_severity?.低 || 0 }}</p>
            </div>
          </div>
          <div class="issue-grid">
            <article v-for="level in ['高', '中', '低']" :key="level" class="issue-card">
              <h3>{{ level }}风险</h3>
              <ul>
                <li v-for="(issue, index) in issuesBySeverity(parseReviewResult(item.reviewResult), level)" :key="index">
                  <strong>{{ issue.type || "问题" }}</strong>：{{ issue.message }}
                  <span v-if="issue.location">位置：{{ issue.location }}</span>
                  <span v-if="issue.legal_basis">依据：{{ issue.legal_basis }}</span>
                  <span v-if="issue.suggestion">建议：{{ issue.suggestion }}</span>
                </li>
                <li v-if="issuesBySeverity(parseReviewResult(item.reviewResult), level).length === 0">暂无</li>
              </ul>
            </article>
          </div>
        </template>
        <p v-else class="muted">该申请尚未生成 AI 初审报告。</p>
      </article>

      <p v-if="!loading && reviewedList.length === 0" class="empty">暂无初审结果。</p>
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { fetchApplications, formatTime, getSession, parseReviewResult, statusText } from "../services/api";

const user = getSession();
const loading = ref(false);
const error = ref("");
const list = ref([]);

const reviewedList = computed(() => list.value.filter((item) => item.reviewResult || ["APPROVED", "REJECTED", "NEED_MANUAL_REVIEW"].includes(item.status)));

function issuesBySeverity(result, level) {
  return (result?.issues || []).filter((item) => (item.severity || "中") === level);
}

async function load() {
  loading.value = true;
  error.value = "";
  try {
    list.value = await fetchApplications();
  } catch (e) {
    error.value = e.message;
  } finally {
    loading.value = false;
  }
}

onMounted(load);
</script>
