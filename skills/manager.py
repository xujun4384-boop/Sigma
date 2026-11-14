"""
Skill 管理器：注册、调度、导出 Anthropic tools 格式

两级暴露机制 (用于主程序接入时的 LLM 交互):
  1. get_skill_headers() → 返回所有 skill 的 header (摘要+使用场景, 全量, 不截断)
     → LLM 了解有哪些 skill 可用, 选择需要的 skill
  2. get_skill_spec(name) → 返回选中 skill 的完整 skill.md (含所有参数详情)
     → LLM 知道如何精确填写参数, 避免调用报错
  3. dispatch(tool_name, **kwargs) → 执行具体工具
"""
from pathlib import Path
from typing import Any
from collections import OrderedDict
import hashlib
import inspect
import json
import os
import threading

from sigma_logger import log
from cancellation import current_cancel_token
from skills.base import BaseTool, ToolResult
from skills.canvas import CanvasDrawTool, CanvasReviewTool
from skills.file_operations import ReadTool, WriteTool, EditTool, BashTool
from skills.web_search import WebSearchTool
from skills.task_management import TodoWriteTool
from skills.docx_reader import ReadDocxTool
from skills.docx_writer import WriteDocxTool
from skills.docx_editor import EditDocxTool
from skills.docx_analyzer import SearchDocxTool
from skills.image_reader import ImageReaderTool
from skills.image_search import ImageSearchTool
from skills.image_generate import ImageGenerateTool
from skills.image_to_image import ImageToImageTool
from skills.sandbox import SandboxTool
from skills.sub_agent import SubAgentTool
from skills.custom_agent import CustomAgentTool
from skills.todo_manager import TodoManager, current_todo_manager
from skills.read_xlsx import ReadXlsxTool
from skills.edit_xlsx import EditXlsxTool
from skills.write_xlsx import WriteXlsxTool
from skills.pptx import ConvertPptxTool
from skills.get_time import GetCurrentTimeTool
from skills.deep_research import DeepResearchTool
from skills.search_document import SearchDocumentTool
from skills.search_code import SearchCodeTool
from skills.read_pdf import ReadPdfTool
from skills.read_pptx import ReadPptxTool
from skills.longread import LongreadTool
from skills.writing_polish import WritingPolishTool
from skills.ask_user import AskUserTool
from skills.network_bridge import NetworkBridgeTool
from skills.javis_bridge import JavisBridgeTool
from skills.wechat_publisher import WeChatPublisherTool
from skills.mail_163 import Mail163Tool
from skills.wecom_email import WecomEmailTool
from skills.gmail import GmailTool
from skills.project_memory import (
    ProjectScanTool, MemoryReadTool, MemoryRecordTool, MemoryUpdateTool,
)

from skills.batch_read import BatchReadTool
from skills.video_generate import VideoSceneTool, VideoComposeTool
from skills.video_auto import VideoAutoTool
from skills.video_custom import VideoCustomTool
from skills.video_overlay import VideoOverlayTool
from skills.video_card import VideoCardTool
from skills.video_cinematic import VideoCinematicStoryboardTool, VideoCinematicGenerateTool
from skills.footage_video import FootageVideoTool
from skills.map_video import MapVideoTool
from skills.opendesign import OpendesignVideoTool
from skills.webpage import WebpageVideoTool
from skills.doubao_tts import DoubaoTTS
from skills.narration import NarrationTool
from skills.music_generate import MusicGenerateTool
from skills.sfx import SfxTool
from skills.subtitle import SubtitleTool
from skills.director import DirectorTool
from skills.product_director import ProductDirectorTool
from skills.video_review import VideoReviewTool
from skills.title_overlay import TitleOverlayTool
from skills.video_produce import VideoProduceTool
from skills.compose_video import ComposeVideoTool
from skills.lyric_mv import LyricMvTool
from skills.character import CharacterSheetTool
from skills.styled_video import StyledVideoTool
from skills.remotion_hook import RemotionHookTool
from skills.manim import ManimVideoTool
from skills.blender import BlenderVideoTool
from skills.fengniao import (
    FengniaoFuzzySearch, FengniaoBasicInfo, FengniaoShareholders,
    FengniaoExecutives, FengniaoInvestments, FengniaoChanges,
    FengniaoExecuted, FengniaoDishonest, FengniaoLimitConsumption,
    FengniaoAbnormalOperation, FengniaoSeriousIllegal, FengniaoAdminPenalty,
)
from skills.flyai import (
    FlyAIKeywordSearch, FlyAIAISearch, FlyAISearchFlight, FlyAISearchTrain,
    FlyAISearchHotel, FlyAISearchPOI, FlyAISearchMarriottHotel, FlyAISearchMarriottPackage,
)
from skills.baidu_map import (
    BaiduMapPlaceTool, BaiduMapDirectionTool, BaiduMapGeocodingTool,
    BaiduMapReverseGeocodingTool, BaiduMapWeatherTool, BaiduMapRenderTool,
)
from computer_use.tool import ComputerUseTool

# 内部工具：仅供子 Agent / 编排流程使用，不对外暴露给 LLM
# （文本/文档类只读工具由 batch_read 统一入口；read_image 例外——图片需要直接看图，
#   已正式暴露给主 LLM，避免 batch_read 多套一层子 Agent 且模型对图片误用 read）。
# 画面引擎（opendesign/manim/cinematic/blender/remotion/footage/map）收为内部，只由 director 导演组调度；video_auto/custom/overlay
# 已并入 video_card；video_produce 已解耦为内部保留；doubao_tts 为旁白组内部引擎。
# blender_video（真 3D）同为"待完善引擎"，仅内部保留。
_INTERNAL_TOOLS = {
    "read", "read_docx", "read_pdf", "read_pptx",
    "video_scene", "video_compose",
    "video_auto", "video_custom", "video_overlay",
    "video_produce", "doubao_tts",
    "opendesign_video", "webpage_video", "manim_video", "blender_video", "styled_video",
    "video_cinematic_storyboard", "video_cinematic_generate",
    "footage_video",
    "map_video",
    "remotion_hook_generate",
    "title_overlay",
}

# 所有工具类的注册表
ALL_TOOL_CLASSES: dict[str, type] = {
    "canvas_draw": CanvasDrawTool,
    "canvas_review": CanvasReviewTool,
    "edit": EditTool,
    "bash": BashTool,
    "web_search": WebSearchTool,
    "todo_write": TodoWriteTool,
    "edit_docx": EditDocxTool,
    "search_docx": SearchDocxTool,
    "read_image": ImageReaderTool,
    "search_image": ImageSearchTool,
    "generate_image": ImageGenerateTool,
    "generate_image_from_images": ImageToImageTool,
    "sandbox_run": SandboxTool,
    "sub_agent": SubAgentTool,
    "custom_agent": CustomAgentTool,
    "get_current_time": GetCurrentTimeTool,
    "edit_xlsx": EditXlsxTool,
    "deep_research": DeepResearchTool,
    "search_document": SearchDocumentTool,
    "search_code": SearchCodeTool,
    "longread": LongreadTool,
    "writing_polish": WritingPolishTool,
    "ask_user": AskUserTool,
    "network_bridge": NetworkBridgeTool,
    "javis_bridge": JavisBridgeTool,
    "project_scan": ProjectScanTool,
    "memory_read": MemoryReadTool,
    "memory_record": MemoryRecordTool,
    "memory_update": MemoryUpdateTool,
    "batch_read": BatchReadTool,
    "video_scene": VideoSceneTool,
    "video_compose": VideoComposeTool,
    "video_auto": VideoAutoTool,
    "video_custom": VideoCustomTool,
    "video_overlay": VideoOverlayTool,
    "video_card": VideoCardTool,
    "compose_video": ComposeVideoTool,
    "video_cinematic_storyboard": VideoCinematicStoryboardTool,
    "video_cinematic_generate": VideoCinematicGenerateTool,
    "footage_video": FootageVideoTool,
    "map_video": MapVideoTool,
    "opendesign_video": OpendesignVideoTool,
    "webpage_video": WebpageVideoTool,
    "manim_video": ManimVideoTool,
    "blender_video": BlenderVideoTool,
    "doubao_tts": DoubaoTTS,
    "narration": NarrationTool,
    "music_generate": MusicGenerateTool,
    "sfx": SfxTool,
    "subtitle": SubtitleTool,
    "director": DirectorTool,
    "product_director": ProductDirectorTool,
    "video_review": VideoReviewTool,
    "title_overlay": TitleOverlayTool,
    "video_produce": VideoProduceTool,
    "lyric_mv": LyricMvTool,
    "character_sheet": CharacterSheetTool,
    "styled_video": StyledVideoTool,
    "remotion_hook_generate": RemotionHookTool,
    "wechat_publish": WeChatPublisherTool,
    "mail_163": Mail163Tool,
    "wecom_email": WecomEmailTool,
    "gmail": GmailTool,
    "fengniao_search": FengniaoFuzzySearch,
    "fengniao_basic_info": FengniaoBasicInfo,
    "fengniao_shareholders": FengniaoShareholders,
    "fengniao_executives": FengniaoExecutives,
    "fengniao_investments": FengniaoInvestments,
    "fengniao_changes": FengniaoChanges,
    "fengniao_executed": FengniaoExecuted,
    "fengniao_dishonest": FengniaoDishonest,
    "fengniao_limit_consumption": FengniaoLimitConsumption,
    "fengniao_abnormal_operation": FengniaoAbnormalOperation,
    "fengniao_serious_illegal": FengniaoSeriousIllegal,
    "fengniao_admin_penalty": FengniaoAdminPenalty,
    "flyai_keyword_search": FlyAIKeywordSearch,
    "flyai_ai_search": FlyAIAISearch,
    "flyai_search_flight": FlyAISearchFlight,
    "flyai_search_train": FlyAISearchTrain,
    "flyai_search_hotel": FlyAISearchHotel,
    "flyai_search_poi": FlyAISearchPOI,
    "flyai_search_marriott_hotel": FlyAISearchMarriottHotel,
    "flyai_search_marriott_package": FlyAISearchMarriottPackage,
    "baidu_map_place": BaiduMapPlaceTool,
    "baidu_map_direction": BaiduMapDirectionTool,
    "baidu_map_geocoding": BaiduMapGeocodingTool,
    "baidu_map_reverse_geocoding": BaiduMapReverseGeocodingTool,
    "baidu_map_weather": BaiduMapWeatherTool,
    "baidu_map_render": BaiduMapRenderTool,
    # 以下为内部工具，仅供子 Agent 使用，不对外暴露
    "read": ReadTool,
    "read_docx": ReadDocxTool,
    "read_pdf": ReadPdfTool,
    "read_pptx": ReadPptxTool,
    "read_xlsx": ReadXlsxTool,
    "write": WriteTool,
    "write_docx": WriteDocxTool,
    "write_xlsx": WriteXlsxTool,
    "convert_pptx": ConvertPptxTool,
    "computer_use": ComputerUseTool,
}

# Skill → 包含的工具名映射
ALL_SKILLS: dict[str, dict] = {
    "canvas": {
        "label": "绘画画布",
        "tool_names": ["canvas_draw", "canvas_review"],
    },
    "file_operations": {
        "label": "文件操作",
        "tool_names": ["edit", "bash"],
    },
    "web_search": {
        "label": "网页搜索",
        "tool_names": ["web_search"],
    },
    "task_management": {
        "label": "任务管理",
        "tool_names": ["todo_write"],
    },
    "docx_editor": {
        "label": "Word 编辑",
        "tool_names": ["edit_docx"],
    },
    "docx_analyzer": {
        "label": "Word 分析",
        "tool_names": ["search_docx"],
    },
    "image_reader": {
        "label": "图片读取",
        "tool_names": ["read_image"],
    },
    "image_search": {
        "label": "图片搜索",
        "tool_names": ["search_image"],
    },
    "image_generate": {
        "label": "图片生成",
        "tool_names": ["generate_image"],
    },
    "image_to_image": {
        "label": "图生图",
        "tool_names": ["generate_image_from_images"],
    },
    "sandbox": {
        "label": "沙箱执行",
        "tool_names": ["sandbox_run"],
    },
    "sub_agent": {
        "label": "子智能体",
        "tool_names": ["sub_agent"],
    },
    "custom_agent": {
        "label": "自定义智能体",
        "tool_names": ["custom_agent"],
    },
    "read_xlsx": {
        "label": "Excel 读取",
        "tool_names": ["read_xlsx"],
    },
    "write_xlsx": {
        "label": "Excel 创建",
        "tool_names": ["write_xlsx"],
    },
    "edit_xlsx": {
        "label": "Excel 编辑",
        "tool_names": ["edit_xlsx"],
    },
    "get_time": {
        "label": "获取当前时间",
        "tool_names": ["get_current_time"],
    },
    "deep_research": {
        "label": "深度研究",
        "tool_names": ["deep_research"],
    },
    "search_document": {
        "label": "文档搜索",
        "tool_names": ["search_document"],
    },
    "search_code": {
        "label": "代码搜索",
        "tool_names": ["search_code"],
    },
    "longread": {
        "label": "长文阅读",
        "tool_names": ["longread"],
    },
    "writing_polish": {
        "label": "写作润色",
        "tool_names": ["writing_polish"],
    },
    "ask_user": {
        "label": "询问用户",
        "tool_names": ["ask_user"],
    },
    "network_bridge": {
        "label": "网络桥接",
        "tool_names": ["network_bridge"],
    },
    "javis_bridge": {
        "label": "Javis 跨机沟通",
        "tool_names": ["javis_bridge"],
    },
    "project_memory": {
        "label": "项目记忆",
        "tool_names": ["project_scan", "memory_read", "memory_record", "memory_update"],
    },
    "batch_read": {
        "label": "批量读取",
        "tool_names": ["batch_read"],
    },
    "video_card": {
        "label": "竖版卡片视频",
        "tool_names": ["video_card"],
    },
    "lyric_mv": {
        "label": "歌词 MV",
        "tool_names": ["lyric_mv"],
    },
    "character": {
        "label": "角色定妆",
        "tool_names": ["character_sheet"],
    },
    "compose_video": {
        "label": "视频合成",
        "tool_names": ["compose_video"],
    },
    "doubao_tts": {
        "label": "豆包语音生成",
        "tool_names": ["doubao_tts"],
    },
    "narration": {
        "label": "旁白生成",
        "tool_names": ["narration"],
    },
    "music_generate": {
        "label": "音乐生成",
        "tool_names": ["music_generate"],
    },
    "sfx": {
        "label": "音效组",
        "tool_names": ["sfx"],
    },
    "subtitle": {
        "label": "字幕生成",
        "tool_names": ["subtitle"],
    },
    "director": {
        "label": "导演组",
        "tool_names": ["director"],
    },
    "product_director": {
        "label": "产品演示导演",
        "tool_names": ["product_director"],
    },
    "video_review": {
        "label": "成片审查",
        "tool_names": ["video_review"],
    },
    "wechat_publisher": {
        "label": "公众号发布",
        "tool_names": ["wechat_publish"],
    },
    "mail_163": {
        "label": "163邮箱收发",
        "tool_names": ["mail_163"],
    },
    "wecom_email": {
        "label": "企业微信邮箱",
        "tool_names": ["wecom_email"],
    },
    "gmail": {
        "label": "Gmail",
        "tool_names": ["gmail"],
    },
    "fengniao": {
        "label": "风鸟企业查询",
        "tool_names": [
            "fengniao_search", "fengniao_basic_info", "fengniao_shareholders",
            "fengniao_executives", "fengniao_investments", "fengniao_changes",
            "fengniao_executed", "fengniao_dishonest", "fengniao_limit_consumption",
            "fengniao_abnormal_operation", "fengniao_serious_illegal", "fengniao_admin_penalty",
        ],
    },
    "flyai": {
        "label": "飞猪旅行搜索",
        "tool_names": [
            "flyai_keyword_search", "flyai_ai_search", "flyai_search_flight",
            "flyai_search_train", "flyai_search_hotel", "flyai_search_poi",
            "flyai_search_marriott_hotel", "flyai_search_marriott_package",
        ],
    },
    "baidu_map": {
        "label": "百度地图",
        "tool_names": [
            "baidu_map_place", "baidu_map_direction", "baidu_map_geocoding",
            "baidu_map_reverse_geocoding", "baidu_map_weather", "baidu_map_render",
        ],
    },
    "pptx": {
        "label": "PPT 生成",
        "tool_names": ["convert_pptx"],
    },
    "computer_use": {
        "label": "桌面自动化(Computer Use)",
        "tool_names": ["computer_use"],
    },
}


# ── 进程级共享缓存 ──
# skill.md 文本 / header 只随文件内容（mtime）变化，跨会话、跨请求复用，避免每条消息重复读盘与解析。
_SKILL_TEXT_CACHE: dict[tuple[str, int], str] = {}
_SKILL_HEADER_CACHE: dict[tuple[str, int], str] = {}
_SKILL_CACHE_LOCK = threading.Lock()

# Gmail 连通性探针结果：按「账号+授权码+服务器」缓存，进程内只真实探测一次。
_GMAIL_STATE: dict[str, dict] = {}
_GMAIL_LOCK = threading.Lock()

# SkillManager 实例池：同一会话 + 同一份配置复用同一实例（工具实例、脚本索引也随之复用）。
_MANAGER_POOL: dict[str, tuple[str, "SkillManager"]] = OrderedDict()
_MANAGER_POOL_LOCK = threading.Lock()
_MANAGER_POOL_MAX = 8


def _norm_path(p) -> str:
    """归一化脚本/命令路径用于比对：小写、统一斜杠、剥外层空白与包裹引号。"""
    return str(p).strip().strip('"').strip("'").replace("\\", "/").lower()


class SkillManager:
    @classmethod
    def acquire(cls, cache_key: str, **kwargs) -> "SkillManager":
        """获取会话级 SkillManager：同会话同配置复用，避免每条消息重复构建。

        cache_key 由「会话标识 + 用途」组成；配置指纹变化（换目录/换 key/换技能集）时自动重建。
        可变会话状态（todo_manager）不参与指纹，命中缓存时按本次请求覆盖。
        """
        fingerprint = cls._config_fingerprint(kwargs)
        with _MANAGER_POOL_LOCK:
            entry = _MANAGER_POOL.get(cache_key)
            if entry and entry[0] == fingerprint:
                _MANAGER_POOL.move_to_end(cache_key)
                manager = entry[1]
                if "todo_manager" in kwargs:
                    manager.todo_manager = kwargs["todo_manager"]
                manager._apply_gmail_state()
                return manager

        manager = cls(**kwargs)
        with _MANAGER_POOL_LOCK:
            _MANAGER_POOL[cache_key] = (fingerprint, manager)
            _MANAGER_POOL.move_to_end(cache_key)
            while len(_MANAGER_POOL) > _MANAGER_POOL_MAX:
                _MANAGER_POOL.popitem(last=False)
        return manager

    @staticmethod
    def _config_fingerprint(kwargs: dict) -> str:
        """把影响工具实例的构造参数压成稳定指纹，排除可变的会话状态。"""
        stable = {k: v for k, v in kwargs.items() if k != "todo_manager"}
        if isinstance(stable.get("enabled_skills"), (list, tuple, set)):
            stable["enabled_skills"] = sorted(stable["enabled_skills"])
        if stable.get("cwd"):
            stable["cwd"] = os.path.abspath(str(stable["cwd"]))
        blob = json.dumps(stable, sort_keys=True, default=str, ensure_ascii=False)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def __init__(self, cwd: str = ".", web_search_provider: str = "kimi",
                 web_search_api_key: str = "", web_search_base_url: str = "",
                 tavily_api_key: str = "", image_gen_api_key: str = "",
                 image_gen_base_url: str = "", image_gen_model: str = "",
                 image_gen_provider: str = "ark",
                 minimax_video_api_key: str = "",
                 cinematic_video_provider: str = "minimax",
                 video_ark_api_key: str = "",
                 video_ark_base_url: str = "",
                 video_ark_model: str = "",
                 doubao_voice_api_key: str = "",
                 doubao_voice_speaker: str = "",
                 music_gen_api_key: str = "",
                 music_gen_base_url: str = "",
                 music_gen_model: str = "",
                 music_gen_provider: str = "",
                 amap_js_key: str = "",
                 amap_security_code: str = "",
                 wechat_appid: str = "", wechat_appsecret: str = "",
                 wechat_relay_url: str = "", wechat_relay_key: str = "",
                 javis_bridge_url: str = "", javis_bridge_key: str = "",
                 javis_agent_id: str = "", javis_peer_id: str = "",
                 fengniao_api_key: str = "", flyai_api_key: str = "",
                 baidu_map_auth_token: str = "",
                 mail163_address: str = "", mail163_auth_code: str = "",
                 mail163_smtp_host: str = "", mail163_smtp_port: str = "",
                 mail163_imap_host: str = "", mail163_imap_port: str = "",
                 wecom_email_address: str = "", wecom_email_auth_code: str = "",
                 wecom_email_smtp_host: str = "", wecom_email_smtp_port: str = "",
                 wecom_email_imap_host: str = "", wecom_email_imap_port: str = "",
                 gmail_address: str = "", gmail_auth_code: str = "",
                 gmail_smtp_host: str = "", gmail_smtp_port: str = "",
                 gmail_imap_host: str = "", gmail_imap_port: str = "",
                 llm_config: dict | None = None,
                 todo_manager: TodoManager | None = None,
                 backup_enabled: bool = True,
                 skills_root: str | None = None,
                 enabled_skills: list[str] | None = None):
        self.cwd = Path(cwd)
        self.skills_root = Path(skills_root) if skills_root else Path(__file__).resolve().parent
        self.backup_enabled = backup_enabled
        self.web_search_provider = web_search_provider
        self.web_search_api_key = web_search_api_key
        self.web_search_base_url = web_search_base_url
        self.tavily_api_key = tavily_api_key
        self.image_gen_api_key = image_gen_api_key
        self.image_gen_base_url = image_gen_base_url
        self.image_gen_model = image_gen_model
        self.image_gen_provider = image_gen_provider
        self.minimax_video_api_key = minimax_video_api_key
        self.cinematic_video_provider = cinematic_video_provider
        self.video_ark_api_key = video_ark_api_key
        self.video_ark_base_url = video_ark_base_url
        self.video_ark_model = video_ark_model
        self.doubao_voice_api_key = doubao_voice_api_key
        self.doubao_voice_speaker = doubao_voice_speaker
        self.music_gen_api_key = music_gen_api_key
        self.music_gen_base_url = music_gen_base_url
        self.music_gen_model = music_gen_model
        self.music_gen_provider = music_gen_provider
        self.amap_js_key = amap_js_key
        self.amap_security_code = amap_security_code
        self.wechat_appid = wechat_appid
        self.wechat_appsecret = wechat_appsecret
        self.wechat_relay_url = wechat_relay_url
        self.wechat_relay_key = wechat_relay_key
        self.javis_bridge_url = javis_bridge_url
        self.javis_bridge_key = javis_bridge_key
        self.javis_agent_id = javis_agent_id
        self.javis_peer_id = javis_peer_id
        self.fengniao_api_key = fengniao_api_key
        self.flyai_api_key = flyai_api_key
        self.baidu_map_auth_token = baidu_map_auth_token
        self.mail163_address = mail163_address
        self.mail163_auth_code = mail163_auth_code
        self.mail163_smtp_host = mail163_smtp_host
        self.mail163_smtp_port = mail163_smtp_port
        self.mail163_imap_host = mail163_imap_host
        self.mail163_imap_port = mail163_imap_port
        self.wecom_email_address = wecom_email_address
        self.wecom_email_auth_code = wecom_email_auth_code
        self.wecom_email_smtp_host = wecom_email_smtp_host
        self.wecom_email_smtp_port = wecom_email_smtp_port
        self.wecom_email_imap_host = wecom_email_imap_host
        self.wecom_email_imap_port = wecom_email_imap_port
        self.gmail_address = gmail_address
        self.gmail_auth_code = gmail_auth_code
        self.gmail_smtp_host = gmail_smtp_host
        self.gmail_smtp_port = gmail_smtp_port
        self.gmail_imap_host = gmail_imap_host
        self.gmail_imap_port = gmail_imap_port
        self.llm_config = llm_config or {}
        self.todo_manager = todo_manager
        self.sub_agent_max_turns = 8  # 可被 server.py 动态设置
        self.cancel_token = None  # 会话级取消令牌，由 server.py 注入
        self._instances: dict[str, BaseTool] = {}

        # 根据 enabled_skills 过滤可用的 tools 和 skills
        if enabled_skills:
            enabled_set = set(enabled_skills)
            self._skills = {
                name: spec for name, spec in ALL_SKILLS.items()
                if name in enabled_set
            }
            enabled_tool_names = set()
            for spec in self._skills.values():
                enabled_tool_names.update(spec.get("tool_names", []))
            # 内部工具始终包含，不因 enabled_skills 过滤而丢失
            self._tool_classes = {
                name: cls for name, cls in ALL_TOOL_CLASSES.items()
                if name in enabled_tool_names or name in _INTERNAL_TOOLS
            }
        else:
            self._skills = dict(ALL_SKILLS)
            self._tool_classes = dict(ALL_TOOL_CLASSES)

        # 建立「技能 scripts 脚本」索引，供 tool_loop 拦截 bash/sandbox 直调。
        # 由 ALL_SKILLS 通用推导，不硬编码技能名，自动覆盖未来新技能。
        self._skill_scripts = {}  # 归一化路径 -> (label, tool_names)；含绝对与相对 key
        for name, spec in self._skills.items():
            scripts_dir = self.skills_root / name / "scripts"
            if scripts_dir.is_dir():
                label = spec.get("label", name)
                tool_names = spec.get("tool_names", [])
                for py in scripts_dir.rglob("*.py"):
                    abs_key = _norm_path(py)
                    rel_key = f"skills/{name}/scripts/{py.relative_to(scripts_dir)}"
                    self._skill_scripts[abs_key] = (label, tool_names)
                    self._skill_scripts[_norm_path(rel_key)] = (label, tool_names)

        # Gmail 需要外网连接：初始化时做连接测试，失败则对 LLM 隐藏
        self._maybe_disable_gmail()

    def _maybe_disable_gmail(self):
        """配置了 Gmail 凭据时，用后台探针校验连通性；请求线程不做任何网络等待。

        探针结果按「账号 + 授权码 + 邮件服务器」缓存，进程内只真实探测一次；
        探测进行中先乐观保留 gmail，探测失败后再对 LLM 隐藏。
        """
        if "gmail" not in self._skills:
            return
        if not self.gmail_address or not self.gmail_auth_code:
            log.info("[Gmail] 未配置凭据，gmail skill 对 LLM 不可见")
            self._remove_gmail_skill()
            return

        key = self._gmail_fingerprint()
        with _GMAIL_LOCK:
            state = _GMAIL_STATE.get(key)
            start_probe = state is None
            if start_probe:
                _GMAIL_STATE[key] = {"status": "pending", "reason": ""}
        if start_probe:
            threading.Thread(
                target=self._probe_gmail,
                args=(key,),
                name="gmail-probe",
                daemon=True,
            ).start()
            log.info("[Gmail] 已配置凭据，后台校验中（不阻塞对话）")
            return
        self._apply_gmail_state(key)

    def _gmail_fingerprint(self) -> str:
        raw = "|".join([
            self.gmail_address,
            self.gmail_auth_code,
            self.gmail_smtp_host or "smtp.gmail.com",
            self.gmail_smtp_port or "465",
            self.gmail_imap_host or "imap.gmail.com",
            self.gmail_imap_port or "993",
        ])
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _apply_gmail_state(self, key: str | None = None):
        """按缓存中的探针结果决定 gmail 是否对 LLM 可见（不触发网络请求）。"""
        if "gmail" not in self._skills:
            return
        key = key or self._gmail_fingerprint()
        with _GMAIL_LOCK:
            state = _GMAIL_STATE.get(key) or {}
        if state.get("status") == "fail":
            self._remove_gmail_skill()

    def _remove_gmail_skill(self):
        self._skills.pop("gmail", None)
        self._tool_classes.pop("gmail", None)

    def _probe_gmail(self, key: str):
        """后台线程：真实校验 SMTP / IMAP 连通性，结果写回进程级缓存。"""
        import imaplib
        import smtplib

        ok, reason = True, ""
        try:
            smtp_host = self.gmail_smtp_host or "smtp.gmail.com"
            smtp_port = int(self.gmail_smtp_port) if self.gmail_smtp_port else 465
            imap_host = self.gmail_imap_host or "imap.gmail.com"
            imap_port = int(self.gmail_imap_port) if self.gmail_imap_port else 993
            try:
                with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=10) as s:
                    s.login(self.gmail_address, self.gmail_auth_code)
            except Exception as e:
                ok, reason = False, f"SMTP: {e}"
            if ok:
                try:
                    imap = imaplib.IMAP4_SSL(imap_host, imap_port, timeout=10)
                    imap.login(self.gmail_address, self.gmail_auth_code)
                    imap.logout()
                except Exception as e:
                    ok, reason = False, f"IMAP: {e}"
        except Exception as e:
            ok, reason = False, str(e)
        finally:
            with _GMAIL_LOCK:
                _GMAIL_STATE[key] = {"status": "ok" if ok else "fail", "reason": reason}
        if ok:
            log.info("[Gmail] 连接测试通过，gmail skill 已启用")
        else:
            log.warning(f"[Gmail] 连接测试失败，gmail skill 对 LLM 不可见: {reason}")

    def clear_cache(self):
        """清除所有内部缓存，配合热重载使用。"""
        self._instances.clear()
        with _SKILL_CACHE_LOCK:
            _SKILL_TEXT_CACHE.clear()
            _SKILL_HEADER_CACHE.clear()

    # ─── 工具注册与实例化 ───

    def get_all_tool_names(self) -> list[str]:
        return list(self._tool_classes)

    def get_tool(self, tool_name: str) -> BaseTool:
        """公开获取（惰性实例化的）工具实例。

        供编排器查询工具自述的运行时资源（如渲染引擎路径与创作规范），
        让"引擎在哪/契约是什么"只有工具本身一个事实来源，调用方无需硬编码。
        """
        return self._get_instance(tool_name)

    def get_anthropic_tools(self) -> list[dict]:
        """导出所有工具为 Anthropic tool use 格式（排除内部工具）"""
        self._apply_gmail_state()
        tools = []
        for tool_name in self._tool_classes:
            if tool_name in _INTERNAL_TOOLS:
                continue
            inst = self._get_instance(tool_name)
            tools.append(inst.to_anthropic_tool())
        return tools

    def get_openai_tools(self) -> list[dict]:
        """导出所有工具为 OpenAI function calling 格式（排除内部工具）"""
        self._apply_gmail_state()
        tools = []
        for tool_name in self._tool_classes:
            if tool_name in _INTERNAL_TOOLS:
                continue
            inst = self._get_instance(tool_name)
            tools.append(inst.to_openai_tool())
        return tools

    def dispatch(self, tool_name: str, **kwargs) -> ToolResult:
        """调度执行工具。执行 todo_write 前自动设置 ContextVar。"""
        # 将本会话取消令牌注入 ContextVar，供工具线程读取（长循环检查 + 子进程登记）
        current_cancel_token.set(self.cancel_token)
        # 在执行前将 TodoManager 注入 ContextVar
        if tool_name == "todo_write" and self.todo_manager:
            current_todo_manager.set(self.todo_manager)
        try:
            inst = self._get_instance(tool_name)
            kwargs = self._normalize_tool_input(inst, kwargs)
            ok, msg = inst.validate_input(**kwargs)
            if not ok:
                return ToolResult.fail(f"参数校验失败: {msg}", error_kind="validation")
            ok, msg = inst.check_permission(**kwargs)
            if not ok:
                return ToolResult.fail(f"权限拒绝: {msg}", error_kind="permission")
            try:
                return inst.execute(**kwargs)
            except TypeError as e:
                return ToolResult.fail(
                    f"工具参数不兼容: {e}",
                    tool_name=tool_name,
                    accepted_parameters=[p.name for p in inst.parameters],
                    received_parameters=list(kwargs.keys()),
                    error_kind="signature",
                )
        finally:
            if tool_name == "todo_write":
                current_todo_manager.set(None)

    def _normalize_tool_input(self, inst: BaseTool, kwargs: dict[str, Any]) -> dict[str, Any]:
        """兼容旧 skill/LLM 常见别名，并过滤 execute 不接收的多余字段。"""
        data = dict(kwargs or {})
        param_names = [p.name for p in inst.parameters]
        param_set = set(param_names)

        alias_candidates = {
            "file_path": ["path", "filepath", "file", "filename", "input", "input_path", "output", "output_file"],
            "output_path": ["save_path", "save_as", "output", "target_path", "target"],
            "save_as": ["output_path", "save_path", "output", "target_path", "target"],
            "input_path": ["file_path", "path", "filepath", "file", "source_path"],
            "query": ["keyword", "keywords", "search_query", "q"],
            "keyword": ["query", "search_query", "q", "text"],
            "search_value": ["keyword", "query", "text", "search_query"],
            "topic": ["query", "question", "prompt", "subject"],
            "prompt": ["query", "text", "description"],
            "content": ["text", "body", "markdown"],
            "text": ["content", "input", "body"],
            "sheets": ["worksheets", "sheet_data", "data"],
            "sheet_name": ["sheet", "worksheet", "tab"],
            "modifications": ["operations", "edits", "changes", "actions"],
            "edit_instructions": ["instructions", "edits", "changes", "operations", "modifications"],
            "tasks": ["task", "prompts", "agents"],
            "todos": ["todo", "items", "tasks"],
            "page_range": ["pages", "range"],
            "extended_keywords": ["expanded_keywords", "synonyms", "related_keywords"],
            "max_results": ["limit", "count", "num_results", "max_images"],
            "max_images": ["max_results", "limit", "count", "num_results"],
            "save_dir": ["output_dir", "target_dir", "folder", "directory", "dir"],
            "output_dir": ["save_dir", "target_dir", "folder", "directory", "dir"],
            "target_project_folder": ["project_folder", "output_dir", "save_dir", "target_dir", "folder", "directory"],
            "resize_to": ["size", "target_size", "dimensions"],
            "quality": ["jpeg_quality", "image_quality"],
            "search_depth": ["depth"],
            "watermark": ["with_watermark"],
            "limit": ["max_results", "count", "num_results"],
        }
        for canonical, aliases in alias_candidates.items():
            if canonical in param_set and canonical not in data:
                for alias in aliases:
                    if alias in data:
                        data[canonical] = data[alias]
                        break

        for param in inst.parameters:
            if param.name not in data and param.default is not None:
                data[param.name] = param.default

        try:
            sig = inspect.signature(inst.execute)
            accepts_kwargs = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
            if accepts_kwargs:
                return data
            accepted = {name for name in sig.parameters if name != "self"}
            return {k: v for k, v in data.items() if k in accepted}
        except (TypeError, ValueError):
            return {k: v for k, v in data.items() if k in param_set}

    def _get_instance(self, tool_name: str) -> BaseTool:
        """惰性实例化工具"""
        if tool_name not in self._instances:
            cls = self._tool_classes.get(tool_name)
            if cls is None:
                raise ValueError(f"未知工具: {tool_name}")
            if tool_name == "web_search":
                self._instances[tool_name] = cls(
                    cwd=str(self.cwd),
                    provider=self.web_search_provider,
                    api_key=self.web_search_api_key,
                    custom_base_url=self.web_search_base_url,
                )
            elif tool_name == "search_image":
                self._instances[tool_name] = cls(cwd=str(self.cwd), tavily_api_key=self.tavily_api_key)
            elif tool_name == "generate_image":
                self._instances[tool_name] = cls(
                    cwd=str(self.cwd),
                    api_key=self.image_gen_api_key,
                    base_url=self.image_gen_base_url,
                    default_model=self.image_gen_model,
                    provider=self.image_gen_provider,
                )
            elif tool_name == "generate_image_from_images":
                # 图生图复用 image_gen 通道，按 provider 自动适配 payload
                self._instances[tool_name] = cls(
                    cwd=str(self.cwd),
                    api_key=self.image_gen_api_key,
                    base_url=self.image_gen_base_url,
                    default_model=self.image_gen_model,
                    provider=self.image_gen_provider,
                )
            elif tool_name == "sub_agent":
                self._instances[tool_name] = cls(
                    cwd=str(self.cwd),
                    llm_config=self.llm_config,
                    skill_manager=self,
                )
            elif tool_name == "custom_agent":
                from custom_agent_manager import custom_agent_manager
                self._instances[tool_name] = cls(
                    cwd=str(self.cwd),
                    skill_manager=self,
                    agent_manager=custom_agent_manager,
                )
            elif tool_name == "read_pdf":
                self._instances[tool_name] = cls(cwd=str(self.cwd))
            elif tool_name == "read_image":
                self._instances[tool_name] = cls(
                    cwd=str(self.cwd),
                    llm_config=self.llm_config,
                )
            elif tool_name == "canvas_review":
                # 画面审查走读图链路，需要 LLM 配置兜底（未配读图模型时用主 LLM）
                self._instances[tool_name] = cls(
                    cwd=str(self.cwd),
                    llm_config=self.llm_config,
                )
            elif tool_name == "lyric_mv":
                # 编导/画面由 LLM 现场创作，复用主 LLM 配置（框架注入，不去读前端存储）
                self._instances[tool_name] = cls(
                    cwd=str(self.cwd),
                    llm_config=self.llm_config,
                    image_config={
                        "provider": self.image_gen_provider,
                        "api_key": self.image_gen_api_key,
                        "base_url": self.image_gen_base_url,
                        "model": self.image_gen_model,
                    },
                )
            elif tool_name == "styled_video":
                # 导演组的风格动画引擎：写镜头代码也要 LLM；画面素材按需自己生图
                self._instances[tool_name] = cls(
                    cwd=str(self.cwd),
                    llm_config=self.llm_config,
                    skill_manager=self,
                )
            elif tool_name == "remotion_hook_generate":
                # Remotion 开场钩子：自由发挥要主 LLM 写 TSX，视觉闸门复用主 LLM 的多模态
                self._instances[tool_name] = cls(
                    cwd=str(self.cwd),
                    llm_config=self.llm_config,
                )
            elif tool_name == "edit_docx":
                self._instances[tool_name] = cls(
                    cwd=str(self.cwd),
                    backup_enabled=self.backup_enabled,
                )
            elif tool_name == "batch_read":
                self._instances[tool_name] = cls(
                    cwd=str(self.cwd),
                    llm_config=self.llm_config,
                    skill_manager=self,
                )
            elif tool_name == "write_docx":
                self._instances[tool_name] = cls(
                    cwd=str(self.cwd),
                    llm_config=self.llm_config,
                    skill_manager=self,
                )
            elif tool_name == "video_auto":
                self._instances[tool_name] = cls(
                    cwd=str(self.cwd),
                    llm_config=self.llm_config,
                    skill_manager=self,
                )
            elif tool_name == "video_card":
                self._instances[tool_name] = cls(
                    cwd=str(self.cwd),
                    skill_manager=self,
                )
            elif tool_name == "video_cinematic_storyboard":
                self._instances[tool_name] = cls(
                    cwd=str(self.cwd),
                    llm_config=self.llm_config,
                )
            elif tool_name == "video_cinematic_generate":
                self._instances[tool_name] = cls(
                    cwd=str(self.cwd),
                    llm_config=self.llm_config,
                    minimax_video_api_key=self.minimax_video_api_key,
                    video_provider=self.cinematic_video_provider,
                    ark_video_api_key=self.video_ark_api_key,
                    ark_video_base_url=self.video_ark_base_url,
                    ark_video_model=self.video_ark_model,
                )
            elif tool_name == "opendesign_video":
                self._instances[tool_name] = cls(
                    cwd=str(self.cwd),
                    llm_config=self.llm_config,
                    skill_manager=self,
                )
            elif tool_name == "webpage_video":
                # 真实网页取景：标注层仍由 LLM 现场写，复用主 LLM 配置
                self._instances[tool_name] = cls(
                    cwd=str(self.cwd),
                    llm_config=self.llm_config,
                )
            elif tool_name == "manim_video":
                self._instances[tool_name] = cls(
                    cwd=str(self.cwd),
                    llm_config=self.llm_config,
                )
            elif tool_name == "blender_video":
                self._instances[tool_name] = cls(
                    cwd=str(self.cwd),
                    llm_config=self.llm_config,
                )
            elif tool_name == "doubao_tts":
                self._instances[tool_name] = cls(
                    cwd=str(self.cwd),
                    api_key=self.doubao_voice_api_key,
                    default_speaker=self.doubao_voice_speaker,
                )
            elif tool_name == "narration":
                self._instances[tool_name] = cls(
                    cwd=str(self.cwd),
                    skill_manager=self,
                    default_speaker=self.doubao_voice_speaker,
                )
            elif tool_name == "music_generate":
                self._instances[tool_name] = cls(
                    cwd=str(self.cwd),
                    api_key=self.music_gen_api_key,
                    base_url=self.music_gen_base_url,
                    default_model=self.music_gen_model,
                    provider=self.music_gen_provider,
                )
            elif tool_name == "map_video":
                # 高德 Key 由前端「技能 API 配置」注入，不写进程序目录
                self._instances[tool_name] = cls(
                    cwd=str(self.cwd),
                    amap_js_key=self.amap_js_key,
                    amap_security_code=self.amap_security_code,
                )
            elif tool_name == "sfx":
                self._instances[tool_name] = cls(cwd=str(self.cwd))
            elif tool_name == "director":
                self._instances[tool_name] = cls(
                    cwd=str(self.cwd),
                    skill_manager=self,
                    llm_config=self.llm_config,
                    default_speaker=self.doubao_voice_speaker,
                    minimax_video_api_key=self.minimax_video_api_key,
                )
            elif tool_name == "product_director":
                self._instances[tool_name] = cls(
                    cwd=str(self.cwd),
                    skill_manager=self,
                    llm_config=self.llm_config,
                )
            elif tool_name == "video_produce":
                self._instances[tool_name] = cls(
                    cwd=str(self.cwd),
                    skill_manager=self,
                    llm_config=self.llm_config,
                    default_speaker=self.doubao_voice_speaker,
                )
            elif tool_name == "wechat_publish":
                self._instances[tool_name] = cls(
                    cwd=str(self.cwd),
                    appid=self.wechat_appid,
                    appsecret=self.wechat_appsecret,
                    relay_url=self.wechat_relay_url,
                    relay_key=self.wechat_relay_key,
                )
            elif tool_name == "javis_bridge":
                self._instances[tool_name] = cls(
                    cwd=str(self.cwd),
                    bridge_url=self.javis_bridge_url,
                    bridge_key=self.javis_bridge_key,
                    agent_id=self.javis_agent_id,
                    peer_id=self.javis_peer_id,
                    llm_config=self.llm_config,
                )
            elif tool_name == "mail_163":
                self._instances[tool_name] = cls(
                    cwd=str(self.cwd),
                    address=self.mail163_address,
                    auth_code=self.mail163_auth_code,
                    smtp_host=self.mail163_smtp_host,
                    smtp_port=self.mail163_smtp_port,
                    imap_host=self.mail163_imap_host,
                    imap_port=self.mail163_imap_port,
                )
            elif tool_name == "wecom_email":
                self._instances[tool_name] = cls(
                    cwd=str(self.cwd),
                    address=self.wecom_email_address,
                    auth_code=self.wecom_email_auth_code,
                    smtp_host=self.wecom_email_smtp_host,
                    smtp_port=self.wecom_email_smtp_port,
                    imap_host=self.wecom_email_imap_host,
                    imap_port=self.wecom_email_imap_port,
                )
            elif tool_name == "gmail":
                self._instances[tool_name] = cls(
                    cwd=str(self.cwd),
                    address=self.gmail_address,
                    auth_code=self.gmail_auth_code,
                    smtp_host=self.gmail_smtp_host,
                    smtp_port=self.gmail_smtp_port,
                    imap_host=self.gmail_imap_host,
                    imap_port=self.gmail_imap_port,
                )
            elif tool_name in (
                "fengniao_search", "fengniao_basic_info", "fengniao_shareholders",
                "fengniao_executives", "fengniao_investments", "fengniao_changes",
                "fengniao_executed", "fengniao_dishonest", "fengniao_limit_consumption",
                "fengniao_abnormal_operation", "fengniao_serious_illegal", "fengniao_admin_penalty",
            ):
                self._instances[tool_name] = cls(
                    cwd=str(self.cwd),
                    api_key=self.fengniao_api_key,
                )
            elif tool_name in (
                "flyai_keyword_search", "flyai_ai_search", "flyai_search_flight",
                "flyai_search_train", "flyai_search_hotel", "flyai_search_poi",
                "flyai_search_marriott_hotel", "flyai_search_marriott_package",
            ):
                self._instances[tool_name] = cls(
                    cwd=str(self.cwd),
                    api_key=self.flyai_api_key,
                )
            elif tool_name in (
                "baidu_map_place", "baidu_map_direction", "baidu_map_geocoding",
                "baidu_map_reverse_geocoding", "baidu_map_weather", "baidu_map_render",
            ):
                self._instances[tool_name] = cls(
                    cwd=str(self.cwd),
                    auth_token=self.baidu_map_auth_token,
                )
            else:
                self._instances[tool_name] = cls(cwd=str(self.cwd))
        return self._instances[tool_name]

    # ─── 两级暴露机制 ───

    def _skill_md_source(self, skill_name: str) -> tuple[Path, int] | None:
        """定位 skill.md 并返回 (路径, mtime)，mtime 作为缓存版本号。"""
        candidates = [
            self.skills_root / skill_name / "skill.md",
            self.skills_root / skill_name / "SKILL.md",
            self.cwd / "skills" / skill_name / "skill.md",
            self.cwd / "skills" / skill_name / "SKILL.md",
        ]
        for path in candidates:
            try:
                if path.exists():
                    return path, path.stat().st_mtime_ns
            except OSError:
                continue
        return None

    def _read_skill_md(self, skill_name: str) -> str | None:
        """读取 skill.md 文件内容（进程级缓存，文件变更后自动失效）。"""
        source = self._skill_md_source(skill_name)
        if source is None:
            return None
        path, mtime = source
        key = (str(path), mtime)
        with _SKILL_CACHE_LOCK:
            cached = _SKILL_TEXT_CACHE.get(key)
        if cached is not None:
            return cached
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return None
        with _SKILL_CACHE_LOCK:
            _SKILL_TEXT_CACHE[key] = text
        return text

    def _parse_header(self, text: str) -> str:
        """截取 skill.md 的 header 部分：标题 + 摘要 + 使用场景（到 ═══ 分隔线之前）。"""
        lines = text.split("\n")
        header_lines = []
        found_title = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("# ") and not found_title:
                found_title = True
                header_lines.append(line)
                continue
            if found_title:
                # 遇到 ## 二级标题或 ═══ 参数分隔线则停止
                if stripped.startswith("## ") or "\u2550" in stripped:
                    break
                header_lines.append(line)
        if not found_title:
            return "\n".join(lines[:20])
        return "\n".join(header_lines)

    def get_skill_headers(self) -> dict[str, str]:
        """一级暴露：返回所有 skill 的 header 摘要，供 LLM 选择（进程级缓存）。"""
        headers: dict[str, str] = {}
        for skill_name in self._skills:
            source = self._skill_md_source(skill_name)
            if source is None:
                continue
            path, mtime = source
            key = (str(path), mtime)
            with _SKILL_CACHE_LOCK:
                header = _SKILL_HEADER_CACHE.get(key)
            if header is None:
                text = self._read_skill_md(skill_name)
                if text is None:
                    continue
                header = self._parse_header(text)
                # 显式列出技能目录与工具名：目录名不一定等于工具名（如 pptx → convert_pptx），
                # 避免 LLM 按工具名去找目录、误判技能未安装，也避免把 skill 名当工具名调用
                tool_names = self._skills.get(skill_name, {}).get("tool_names", [])
                header = header.rstrip() + f"\n\n技能目录: `skills/{skill_name}/`"
                if tool_names:
                    header += f"\n工具名: `{'`, `'.join(tool_names)}`"
                with _SKILL_CACHE_LOCK:
                    _SKILL_HEADER_CACHE[key] = header
            headers[skill_name] = header
        return headers

    def get_skill_spec(self, skill_name: str) -> str | None:
        """二级暴露：返回指定 skill 的完整 skill.md 内容，含所有参数详情。"""
        if skill_name not in self._skills:
            return None
        return self._read_skill_md(skill_name)

    def get_skill_specs_for_tool(self, tool_name: str) -> str | None:
        """根据工具名找到所属 skill，返回完整 skill.md。"""
        for skill_name, spec in self._skills.items():
            if tool_name in spec["tool_names"]:
                return self._read_skill_md(skill_name)
        return None
