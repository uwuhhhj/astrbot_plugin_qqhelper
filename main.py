import asyncio
import re
from typing import Dict, List
from astrbot import logger
from astrbot.core import AstrBotConfig
from astrbot.api.event import filter
from astrbot.api.star import Context, Star, register
from astrbot.core.message.components import Reply
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)

@register(
    "astrbot_plugin_qqhelper",
    "Loliiiico",
    "[仅aiocqhttp] 群管助手",
    "v1.0.0",
    "https://github.com/uwuhhhj/astrbot_plugin_qqhelper",
)
class MyPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.simmc_group: List[str] = config.get(
            "simmc_group", []
        )  # 启用此插件的simmc群聊
        self.admin_group: List[str] = config.get(
            "admin_group", []
        )  # 管理员群聊
    async def initialize(self):
        """初始化插件"""
        pass
    @filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP)
    async def event_monitoring(self, event: AiocqhttpMessageEvent):
        """监听进群/退群事件"""
        raw = getattr(event.message_obj, "raw_message", None)
        if not isinstance(raw, dict):
            return
        client = event.bot
        # 进群申请事件
        if (
                event.get_group_id() in self.simmc_group
                and raw.get("post_type") == "request"
                and raw.get("request_type") == "group"
                and raw.get("sub_type") == "add"
        ):
            user_id = str(raw.get("user_id", ""))
            group_id = str(raw.get("group_id", ""))
            comment = raw.get("comment")
            flag = raw.get("flag", "")
            nickname = (await client.get_stranger_info(user_id=int(user_id)))[
                           "nickname"
                       ] or "未知昵称"
            reply = f"【收到{group_id}群的进群申请】同意进群吗：\n昵称：{nickname}\nQQ：{user_id}\nflag：{flag}\n raw:{raw}"
            await client.send_group_msg(group_id=int(self.admin_group[0]), message=reply)