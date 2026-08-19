import os
# 测试公共配置
# 测试不能因为知识库构建或外部API不可用而失败。
os.environ["SKIP_KB_STARTUP"] = "1"
os.environ["RAG_LLM_GENERATION_ENABLED"] = "0"
os.environ["API_KEY"] = ""
os.environ["OPENAI_API_KEY"] = ""
