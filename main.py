
import re
from astrbot.core import AstrBotConfig
from astrbot.core.message.components import Reply
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)
import asyncio
import datetime
import json
import os
import random
from typing import Dict, List, Union

# 导入AstrBot核心API
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
import astrbot.api.message_components as Comp


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
        # 缓存群成员列表（减少API调用）
        self.member_cache: Dict[str, List] = {}
        self.cache_time: Dict[str, datetime.datetime] = {}

        self.auto_black: bool = config.get("auto_black", True)
        self.reject_ids_list: List[dict[str, list[str]]] = config.get(
            "reject_ids_list", [{}]
        )
        self.reject_ids: dict[str, list[str]] = (
            self.reject_ids_list[0] if self.reject_ids_list else {}
        )
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
            comment = raw.get("comment", "")
            flag = raw.get("flag", "")
            nickname = (await client.get_stranger_info(user_id=int(user_id)))[
                           "nickname"
                       ] or "未知昵称"

            # 根据群号在simmc_group列表中的索引确定群名
            group_name = "未知群"
            try:
                group_index = self.simmc_group.index(group_id)
                group_name = f"{group_index + 1}群"
            except ValueError:
                # 如果群号不在列表中，使用群号作为群名
                group_name = f"群{group_id}"

            # 构造美化的消息
            reply_lines = [
                f"🔔 收到 {group_name} 的进群申请",
                "━━━━━━━━━━━━━━━━━━━━",
                f"👤 申请人：{nickname}",
                f"🆔 QQ号：{user_id}",
            ]

            # 如果有申请理由，添加到消息中
            if comment and comment.strip():
                reply_lines.append(f"💬 申请理由：{comment}")

            reply_lines.extend([
                f"🏷️ Flag：{flag}",
                "━━━━━━━━━━━━━━━━━━━━",
                "请管理员决定是否同意该申请 ✅❌"
            ])

            reply = "\n".join(reply_lines)
            await client.send_group_msg(group_id=int(self.admin_group[0]), message=reply)


            # —— 新增：在其他 simmc_group 里查重 ——
            check_lines: List[str] = []
            for other_gid in self.simmc_group:
                # 跳过申请发生的那个群
                if str(other_gid) == group_id:
                    continue

                # 拉取缓存／实时成员列表
                members = await self._get_group_members(event, int(other_gid))
                # members 是一 list[dict]，每个 dict 里有 "user_id"
                if any(str(m.get("user_id")) == user_id for m in members):
                    try:
                        idx = self.simmc_group.index(str(other_gid))
                        name = f"{idx+1}群"
                    except ValueError:
                        name = f"群{other_gid}"
                    check_lines.append(f"⚠️ 已在 {name}（{other_gid}）中")

            # —— 全局黑名单检测 ——
            # 遍历所有群的黑名单，看 user_id 出现在哪些群里
            bl_hits: List[str] = []
            for gid, uids in self.reject_ids.items():
                if user_id in uids:
                    try:
                        idx = self.simmc_group.index(gid)
                        grp_name = f"{idx+1}群"
                    except ValueError:
                        grp_name = f"群{gid}"
                    bl_hits.append(f"{grp_name}（{gid}）")

            if bl_hits:
                # 如果有命中，把哪些群列出来
                check_lines.append(
                    f"🚫 黑名单检测：用户 {nickname}（{user_id}）"
                    f" 曾在以下群主动退出并被拉黑：{','.join(bl_hits)}"
                )
            else:
                check_lines.append(
                    f"✅ 黑名单检测：用户 {nickname}（{user_id}）未在任何 simmc 群主动退过。"
                )

            # —— 拼最终结果并发送 ——
            check_info = "检测结果：\n" + "\n".join(check_lines)
            await client.send_group_msg(
                group_id=int(self.admin_group[0]),
                message=check_info
            )

            # 主动退群事件
        elif (
                self.auto_black
                and raw.get("post_type") == "notice"
                and raw.get("notice_type") == "group_decrease"
                and raw.get("sub_type") == "leave"
        ):
            user_id = str(raw.get("user_id", ""))
            group_id = str(raw.get("group_id", ""))
            nickname = (await client.get_stranger_info(user_id=int(user_id)))[
                           "nickname"
                       ] or "未知昵称"
            # 确保列表存在
            ids = self.reject_ids.setdefault(group_id, [])
            # 只有不在才追加
            if user_id not in ids:
                ids.append(user_id)
                # 持久化
                self.config["reject_ids_list"] = [self.reject_ids]
                self.config.save_config()
                leave_info = f"{nickname}({user_id}) 主动退群，已拉进黑名单"
            else:
                leave_info = f"{nickname}({user_id}) 再次退群，已在黑名单中，无需重复添加"

            await client.send_group_msg(
                group_id=int(self.admin_group[0]),
                message=leave_info
            )
    async def _get_group_members(self, event: AstrMessageEvent, group_id: int):
        """获取群成员列表（带缓存）"""
        group_id_str = str(group_id)

        # 检查缓存是否有效（50分钟有效期）
        if group_id_str in self.member_cache:
            last_update = self.cache_time.get(group_id_str)
            if last_update and (datetime.datetime.now() - last_update).total_seconds() < 3000:
                return self.member_cache[group_id_str]

        members = []
        platform = event.get_platform_name()

        # OneBot (aiocqhttp) 平台实现
        if platform == "aiocqhttp" and AiocqhttpMessageEvent:
            client = event.bot
            payloads = {"group_id": group_id, "no_cache": True}
            try:
                ret = await client.api.call_action('get_group_member_list', **payloads)
                members = ret
            except Exception as e:
                logger.error(f"获取群成员失败: {e}")

        # 其他平台可以在此扩展
        # elif platform == "other_platform":
        #   ...

        # 更新缓存
        if members:
            self.member_cache[group_id_str] = members
            self.cache_time[group_id_str] = datetime.datetime.now()

        return members

    @filter.command("更新群成员缓存")
    async def update_group_member(self, event: AstrMessageEvent, group_id: int):
        """指令更新群成员列表"""
        # 提示开始
        yield event.plain_result("🔄 正在尝试更新群成员列表…")

        # 调用缓存／拉取方法
        members = await self._get_group_members(event, group_id)

        # 如果拉取失败（返回空列表），给出失败提示
        if not members:
            yield event.plain_result("❌ 获取群成员列表失败，检查一下群号是否正确或机器人权限是否足够。")
            return

        # 计算数量并返回成功信息
        count = len(members)
        yield event.plain_result(f"✅ 群【{group_id}】成员缓存已更新，共有 {count} 位成员。")

