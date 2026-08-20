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

          <section v-if="parseReviewResult(item.reviewResult).agent_result" class="agent-trace-panel">
            <div class="agent-trace-head">
              <div>
                <p class="eyebrow">Agent observability</p>
                <h3>Agent 执行轨迹</h3>
              </div>
              <div class="agent-trace-badges">
                <span class="trace-badge">{{ agentModeText(parseReviewResult(item.reviewResult).agent_result.mode) }}</span>
                <span class="trace-badge">{{ statusText(parseReviewResult(item.reviewResult).agent_result.decision) }}</span>
              </div>
            </div>

            <details v-if="parseReviewResult(item.reviewResult).agent_result.analysis" class="agent-analysis">
              <summary>查看 Agent 审查说明</summary>
              <pre>{{ parseReviewResult(item.reviewResult).agent_result.analysis }}</pre>
            </details>

            <ol v-if="agentToolTrace(parseReviewResult(item.reviewResult)).length" class="agent-trace-list">
              <li v-for="(step, index) in agentToolTrace(parseReviewResult(item.reviewResult))" :key="`${step.tool_name}-${index}`">
                <div class="agent-step-head">
                  <strong>{{ index + 1 }}. {{ toolNameText(step.tool_name) }}</strong>
                  <span class="trace-status" :class="step.status === 'SUCCESS' ? 'trace-success' : 'trace-error'">
                    {{ step.status === "SUCCESS" ? "成功" : "失败" }} · {{ formatLatency(step.latency_ms) }} ms
                  </span>
                </div>
                <p>{{ step.input_summary }}</p>
                <p class="muted">{{ step.output_summary }}</p>
                <div v-if="step.citation_ids?.length" class="trace-citations">
                  <span v-for="citation in step.citation_ids" :key="citation">{{ citation }}</span>
                </div>
              </li>
            </ol>
            <p v-else class="muted">本次审核未调用外部工具，或该记录生成于轨迹功能上线之前。</p>
          </section>
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

function agentToolTrace(result) {
  return result?.agent_result?.tool_trace || [];
}

function agentModeText(mode) {
  const labels = {
    langchain_agent: "LangChain Agent",
    langchain_agent_error_fallback: "Agent 异常降级",
    deterministic_rule_agent: "确定性规则降级",
  };
  return labels[mode] || mode || "未知模式";
}

function toolNameText(name) {
  const labels = {
    knowledge_search: "法规知识检索",
    check_completeness: "材料完整性检查",
    industry_category_check: "行业类别检查",
    risk_summary: "风险汇总",
  };
  return labels[name] || name;
}

function formatLatency(value) {
  const latency = Number(value);
  return Number.isFinite(latency) ? latency.toFixed(2) : "0.00";
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
