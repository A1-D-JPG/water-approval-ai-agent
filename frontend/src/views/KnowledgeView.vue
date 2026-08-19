<template>
  <section class="page-card">
    <div class="page-head">
      <div>
        <p class="eyebrow">RAG Evidence Search</p>
        <h1>法规知识检索</h1>
        <p class="muted">基于 BGE 向量检索返回涉水审批依据，每条证据均携带可追溯的文件与分块编号。</p>
      </div>
    </div>

    <form class="knowledge-form" @submit.prevent="search">
      <label>
        请输入涉水审批问题
        <textarea
          v-model.trim="query"
          maxlength="500"
          required
          placeholder="例如：申请取水许可证需要提交哪些材料？"
        />
      </label>
      <label>
        返回条数
        <select v-model.number="topK">
          <option :value="1">1</option>
          <option :value="3">3</option>
          <option :value="5">5</option>
        </select>
      </label>
      <button type="submit" :disabled="loading">{{ loading ? "检索中..." : "检索证据" }}</button>
    </form>

    <p v-if="error" class="error">{{ error }}</p>

    <div v-if="result" class="knowledge-results">
      <div class="knowledge-meta">
        <span class="status-pill">{{ decisionText(result.decision) }}</span>
        <span class="citation-tag">{{ result.retrieval_mode }}</span>
        <span class="muted">{{ result.message }}</span>
      </div>

      <article v-if="result.answer" class="answer-card">
        <header>
          <h2>基于证据的回答</h2>
          <span class="citation-tag">{{ result.answer_mode }}</span>
        </header>
        <p class="evidence-content">{{ result.answer }}</p>
      </article>

      <article v-for="(item, index) in result.items" :key="item.citation_id" class="evidence-card">
        <header>
          <strong>证据 {{ index + 1 }} · {{ item.source }}</strong>
          <span class="citation-tag">{{ item.citation_id }}</span>
        </header>
        <p class="evidence-content">{{ item.content }}</p>
        <p class="muted">分块：{{ item.chunk_index + 1 }} · 距离分数：{{ formatScore(item.score) }}</p>
      </article>

      <p v-if="result.items.length === 0" class="empty">没有返回可用证据。</p>
    </div>
  </section>
</template>

<script setup>
import { ref } from "vue";
import { queryKnowledge } from "../services/api";

const query = ref("申请取水许可证需要提交哪些材料");
const topK = ref(3);
const loading = ref(false);
const error = ref("");
const result = ref(null);

async function search() {
  loading.value = true;
  error.value = "";
  result.value = null;
  try {
    result.value = await queryKnowledge({ query: query.value, top_k: topK.value });
  } catch (e) {
    error.value = e.message;
  } finally {
    loading.value = false;
  }
}

function decisionText(decision) {
  return { ANSWERED: "已检索", REFUSED: "已拒答", DEGRADED: "需人工复核" }[decision] || decision;
}

function formatScore(score) {
  return typeof score === "number" && Number.isFinite(score) ? score.toFixed(4) : "-";
}
</script>
