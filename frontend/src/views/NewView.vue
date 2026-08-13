<template>
  <section class="page-card">
    <div class="page-head">
      <div>
        <p class="eyebrow">申请人功能</p>
        <h1>新建取水许可申请</h1>
        <p class="muted">填写结构化申请信息并上传 PDF、Word、图片等附件。提交后进入待审核状态。</p>
      </div>
    </div>

    <form @submit.prevent="submitForm('SUBMITTED')">
      <div class="form-grid">
        <label>申请人姓名/企业名称<input v-model.trim="form.applicantName" required /></label>
        <label>身份证号/统一社会信用代码<input v-model.trim="form.idNumber" required /></label>
        <label>项目名称<input v-model.trim="form.projectName" placeholder="例如 XX 农业灌溉取水项目" /></label>
        <label>取水地点<input v-model.trim="form.waterLocation" placeholder="填写行政区划或具体坐标描述" /></label>
        <label>取水用途<input v-model.trim="form.waterUse" placeholder="生活、工业、农业灌溉或其他" /></label>
        <label>行业类别<input v-model.trim="form.industryCategory" placeholder="例如 011 谷物种植" /></label>
        <label>联系方式<input v-model.trim="form.contactPhone" placeholder="请输入手机号或联系电话" /></label>
      </div>

      <div class="drop-zone" @dragover.prevent @drop.prevent="onDrop">
        <label for="files">上传附件</label>
        <input id="files" type="file" accept=".pdf,.doc,.docx,image/*" multiple @change="onFileChange" required />
        <p class="hint">支持多文件上传，可拖拽 PDF、Word、身份证/营业执照图片等材料到此区域。</p>
      </div>

      <div v-if="form.files.length" class="file-list">
        <span v-for="file in form.files" :key="file.name">{{ file.name }}</span>
      </div>

      <div class="actions">
        <button type="button" class="secondary" @click="submitForm('DRAFT')" :disabled="submitting || !form.files.length">保存草稿</button>
        <button type="submit" :disabled="submitting || !form.files.length">{{ submitting ? "提交中..." : "提交申请" }}</button>
      </div>
    </form>

    <p v-if="toast" class="toast" :class="toastType">{{ toast }}</p>
  </section>
</template>

<script setup>
import { reactive, ref } from "vue";
import { getSession, submitApplication } from "../services/api";

const user = getSession();
const form = reactive({
  applicantName: user?.displayName || "",
  idNumber: user?.identityNo || "",
  projectName: "",
  waterLocation: "",
  waterUse: "",
  industryCategory: "",
  contactPhone: user?.phone || "",
  submitMode: "SUBMITTED",
  files: []
});

const submitting = ref(false);
const toast = ref("");
const toastType = ref("success");

function onFileChange(event) {
  form.files = Array.from(event.target.files || []);
}

function onDrop(event) {
  form.files = Array.from(event.dataTransfer.files || []);
}

async function submitForm(mode) {
  submitting.value = true;
  toast.value = "";
  form.submitMode = mode;
  try {
    const result = await submitApplication(form);
    toastType.value = "success";
    toast.value = mode === "DRAFT" ? `草稿保存成功，申请 ID：${result.id}` : `申请提交成功，申请 ID：${result.id}`;
    form.projectName = "";
    form.waterLocation = "";
    form.waterUse = "";
    form.industryCategory = "";
    form.contactPhone = user?.phone || "";
    form.files = [];
    const fileInput = document.getElementById("files");
    if (fileInput) fileInput.value = "";
  } catch (e) {
    toastType.value = "error";
    toast.value = e.message;
  } finally {
    submitting.value = false;
  }
}
</script>
