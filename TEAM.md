# 团队分工文档

| 模块 | 负责人角色 | 主要职责 |
|---|---|---|
| Java 后端 | Java 后端负责人 | Spring Boot REST API、CORS、MySQL 数据库、文件上传、权限控制、调用 Python AI 服务 |
| Python AI 服务 | AI 服务负责人 | FastAPI、LangChain、ChromaDB、文档解析、向量检索、MCP 工具、Agent 初审逻辑 |
| 前端页面 | 前端负责人 | Vue3 + Vite 页面、登录注册、申请列表、新建申请、初审结果、管理员看板 |
| 测试与联调 | 测试负责人 | 节点验收、接口测试、真实格式测试用例、Java/Python/Vue 三端联调 |
| 文档与版本管理 | 文档负责人 | README、验收说明、Git 提交记录、答辩材料整理 |

## Git 版本控制说明

项目已使用 Git 管理，当前仓库包含 Java、Python、Vue 三个模块。答辩时可使用以下命令展示提交记录：

```powershell
git log --oneline --decorate -5
```

## 建议答辩账号

| 角色 | 用途 |
|---|---|
| 申请人 | 提交取水许可申请、上传附件、查看自己的初审结果 |
| 审核员 | 查看待审/已审申请，发起 AI 初审 |
| 管理员 | 查看全部数据、用户管理、角色调整、系统健康状态 |
