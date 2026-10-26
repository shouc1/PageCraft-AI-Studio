"""应用配置，从环境变量 / .env 读取。"""

from pathlib import Path
from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    # 火山引擎 IAM（即梦 AI 签名用）
    volcengine_ak: str = ""
    volcengine_sk: str = ""

    # 豆包 ARK（OpenAI 兼容接口，用 ARK API Key）
    ark_api_key: str = ""
    doubao_model: str = ""

    # 语言模型厂商选择（doubao / qwen），设置页可切换
    llm_provider: str = "doubao"
    # 生图厂商选择（jimeng / qwen），设置页可切换
    image_provider: str = "jimeng"
    # 阿里云百炼 DashScope（千问文本/生图共用 API Key）
    dashscope_api_key: str = ""
    # 千问 LLM 走 OpenAI 兼容地址（业务空间专属域名可用 .../compatible-mode/v1）
    dashscope_llm_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    qwen_text_model: str = "qwen-plus"
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/api/v1"
    qwen_image_model: str = "qwen-image-3.0-pro"

    # 服务
    backend_host: str = "127.0.0.1"
    backend_port: int = 8000
    frontend_url: str = "http://localhost:3000"

    # 路径
    upload_dir: Path = BASE_DIR / "uploads"
    result_dir: Path = BASE_DIR / "results"
    db_path: Path = BASE_DIR / "data.db"

    # 即梦 API
    jimeng_api_base: str = "https://visual.volcengineapi.com"
    jimeng_region: str = "cn-north-1"
    jimeng_service: str = "cv"
    # 即梦模型 req_key（按 workflow 区分，可在 .env / 设置页覆盖）
    jimeng_t2i_model: str = "t2i_v40_jimeng"
    jimeng_i2i_model: str = "jimeng_i2i_v30"
    # 豆包 API
    doubao_api_base: str = "https://ark.cn-beijing.volces.com/api/v3"

    # 即梦生图并发上限（§9 决策4：按火山控制台实际配额填写，
    # 配额升级只改配置不改代码）
    jimeng_max_concurrency: int = 1
    # 主图一致性方案（§5）：i2i 重绘强度压低到 0.3~0.5，商品本体保真
    main_image_strength: float = 0.4
    # 主图尺寸（§6.5：主图 1:1）
    main_image_size: str = "1024x1024"
    # 详情页图片尺寸（§6.5：详情页宽 750/790px，竖版长图）
    detail_image_size: str = "750x1200"
    # 一致性校验阈值（§5：生成结果与原图视觉相似度低于此值标记"疑似失真"）
    consistency_threshold: float = 0.6

    @property
    def has_credentials(self) -> bool:
        return bool(self.volcengine_ak and self.volcengine_sk)

    @property
    def has_dashscope_credentials(self) -> bool:
        return bool(self.dashscope_api_key and self.qwen_image_model)

    @property
    def has_qwen_llm_credentials(self) -> bool:
        return bool(self.dashscope_api_key and self.qwen_text_model)

    @property
    def has_ark_credentials(self) -> bool:
        return bool(self.ark_api_key and self.doubao_model)

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()

# 确保目录存在
settings.upload_dir.mkdir(parents=True, exist_ok=True)
settings.result_dir.mkdir(parents=True, exist_ok=True)
