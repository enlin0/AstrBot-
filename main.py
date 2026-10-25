import asyncio
import json
import logging
import math
import re
import time
from collections import OrderedDict
from urllib.parse import urlsplit

import aiohttp
from astrbot.api import AstrBotConfig
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import Image, Plain
from astrbot.api.star import Context, Star, register

logger = logging.getLogger(__name__)

API_BASE = "https://nekos.best/api/v2"
USER_AGENT = "AstrBotRandomIllustration/1.0 (https://github.com/AstrBotDevs/AstrBot)"
CATEGORIES = {
    "waifu": "动漫少女",
    "neko": "猫娘",
    "kitsune": "狐娘",
    "husbando": "动漫少年",
}
ALIASES = {
    "少女": "waifu", "动漫少女": "waifu",
    "猫娘": "neko", "狐娘": "kitsune",
    "少年": "husbando", "动漫少年": "husbando",
}
NUMBERS = dict(zip("一二三四五六七八九十", range(1, 11)))
HELP = (
    "全年龄随机插画\n"
    "/插画 —— 随机一张\n"
    "/插画 3 猫娘 —— 三张猫娘插画\n"
    "/插画 狐娘 二张 —— 两张狐娘插画\n"
    "分类：少女 / 猫娘 / 狐娘 / 少年\n"
    "英文分类：waifu / neko / kitsune / husbando\n"
    "也可以使用 /随机插画；分类与数量可交换顺序。\n"
    "分类筛选不支持任意角色或关键词搜索。"
)


class FetchError(Exception):
    pass


def bounded_int(config, key, default, lower, upper):
    try:
        value = int(config.get(key, default))
    except (TypeError, ValueError, OverflowError):
        value = default
    return max(lower, min(upper, value))


def parse_request(arguments, default_category, max_count):
    count = 1
    category = default_category
    has_count = False
    has_category = False
    for token in arguments:
        if not token:
            continue
        match = re.fullmatch(r"([0-9]+|[一二三四五六七八九十])(?:张|份)?", token)
        if match:
            if has_count:
                raise ValueError("数量只能填写一次。")
            number = match.group(1)
            count = NUMBERS[number] if number in NUMBERS else int(number)
            has_count = True
        else:
            resolved = ALIASES.get(token.lower(), token.lower())
            if resolved not in CATEGORIES:
                raise ValueError("不支持这个分类。发送 /插画 帮助 查看用法。")
            if has_category:
                raise ValueError("每次只能选择一个分类。")
            category = resolved
            has_category = True
    if not 1 <= count <= max_count:
        raise ValueError(f"每次可以获取 1～{max_count} 张插画。")
    return count, category


def validate_image_url(value, category):
    if not isinstance(value, str):
        return False
    try:
        parsed = urlsplit(value)
        return (
            parsed.scheme == "https"
            and parsed.netloc == "nekos.best"
            and parsed.query == ""
            and parsed.fragment == ""
            and re.fullmatch(
                rf"/api/v2/{re.escape(category)}/[a-zA-Z0-9-]+\.png",
                parsed.path,
            ) is not None
        )
    except ValueError:
        return False


@register(
    "astrbot_plugin_random_illustration",
    "Local",
    "全年龄随机动漫插画，支持分类、数量和用户冷却",
    "1.0.0",
)
class RandomIllustrationPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self._session = None
        self._busy = set()
        self._cooldowns = OrderedDict()
        self._slots = asyncio.Semaphore(3)

    def _client(self):
        if self._session is None or self._session.closed:
            timeout = bounded_int(self.config, "timeout_seconds", 25, 5, 120)
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=timeout),
                headers={"User-Agent": USER_AGENT},
                connector=aiohttp.TCPConnector(limit=6),
                trust_env=True,
            )
        return self._session

    async def _get(self, url, limit, image=False):
        retries = bounded_int(self.config, "retries", 2, 0, 3)
        for attempt in range(retries + 1):
            delay = min(2 ** attempt, 5)
            try:
                async with self._client().get(url, allow_redirects=False) as response:
                    if response.status != 200:
                        retryable = response.status == 429 or response.status >= 500
                        if not retryable or attempt == retries:
                            raise FetchError(f"图片服务暂时不可用（HTTP {response.status}）。")
                        retry_after = response.headers.get("Retry-After", "")
                        if retry_after.isdigit():
                            delay = min(max(int(retry_after), delay), 10)
                    else:
                        content_type = response.headers.get("Content-Type", "").lower()
                        if image and not content_type.startswith("image/png"):
                            raise FetchError("图片服务返回的格式不正确。")
                        if response.content_length is not None and response.content_length > limit:
                            raise FetchError("图片或接口响应超过大小限制。")
                        buffer = bytearray()
                        async for chunk in response.content.iter_chunked(65536):
                            buffer.extend(chunk)
                            if len(buffer) > limit:
                                raise FetchError("图片或接口响应超过大小限制。")
                        if not buffer:
                            raise FetchError("图片服务返回了空内容。")
                        return bytes(buffer)
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                if attempt == retries:
                    raise FetchError("连接图片服务失败或超时，请稍后重试。") from exc
            await asyncio.sleep(delay)
        raise FetchError("图片获取失败。")

    async def _metadata(self, category, count):
        body = await self._get(f"{API_BASE}/{category}?amount={count}", 65536)
        try:
            payload = json.loads(body)
        except (ValueError, UnicodeDecodeError) as exc:
            raise FetchError("图片服务返回了无效数据。") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
            raise FetchError("图片服务返回了无效数据。")
        records = []
        seen = set()
        for record in payload["results"]:
            if not isinstance(record, dict):
                continue
            url = record.get("url")
            if validate_image_url(url, category) and url not in seen:
                records.append(record)
                seen.add(url)
            if len(records) == count:
                break
        if not records:
            raise FetchError("暂时没有找到这个分类的插画。")
        return records

    def _credit(self, record):
        artist = str(record.get("artist_name") or "未知")[:100]
        source = record.get("source_url")
        credit = f"\n画师：{artist} | 图片来源：nekos.best"
        if isinstance(source, str) and source.startswith("https://"):
            credit += f"\n原作：{source[:500]}"
        return credit

    @filter.command("插画", alias={"随机插画"})
    async def illustration(
        self, event: AstrMessageEvent, first: str = "", second: str = ""
    ):
        if first.lower() in {"帮助", "help", "?"}:
            yield event.plain_result(HELP)
            return
        max_count = bounded_int(self.config, "max_count", 3, 1, 5)
        default = str(self.config.get("default_category", "waifu"))
        if default not in CATEGORIES:
            default = "waifu"
        try:
            count, category = parse_request((first, second), default, max_count)
        except ValueError as exc:
            yield event.plain_result(str(exc))
            return

        key = (str(event.unified_msg_origin), str(event.get_sender_id()))
        now = time.monotonic()
        for expired_key, expiry in list(self._cooldowns.items()):
            if expiry <= now:
                self._cooldowns.pop(expired_key, None)
        if key in self._busy:
            yield event.plain_result("上一条插画请求还在处理中。")
            return
        remaining = self._cooldowns.get(key, 0) - now
        if remaining > 0:
            yield event.plain_result(f"请再等 {math.ceil(remaining)} 秒。")
            return
        if self._slots.locked():
            yield event.plain_result("当前请求较多，请稍后再试。")
            return

        self._busy.add(key)
        cooldown = bounded_int(self.config, "cooldown_seconds", 10, 0, 3600)
        self._cooldowns[key] = now + cooldown
        while len(self._cooldowns) > 4096:
            self._cooldowns.popitem(last=False)
        sent = 0
        failure = None
        try:
            async with self._slots:
                records = await self._metadata(category, count)
                limit = bounded_int(self.config, "max_image_mb", 10, 1, 20) * 1024 * 1024
                for record in records:
                    try:
                        data = await self._get(record["url"], limit, image=True)
                        if not data.startswith(b"\x89PNG\r\n\x1a\n"):
                            raise FetchError("图片文件格式校验失败。")
                        components = [Image.fromBytes(data)]
                        if self.config.get("show_credit", True):
                            components.append(Plain(text=self._credit(record)))
                        await event.send(event.chain_result(components))
                        sent += 1
                    except FetchError as exc:
                        logger.warning("Random illustration fetch failed: %s", exc)
                        failure = str(exc)
                    except Exception:
                        logger.exception("Random illustration send failed")
                        failure = "发送失败，请检查 Bot 平台连接和图片发送权限。"
        except FetchError as exc:
            logger.warning("Random illustration service failed: %s", exc)
            failure = str(exc)
        except Exception:
            logger.exception("Random illustration request failed")
            failure = "插画请求失败，请检查 AstrBot 日志。"
        finally:
            self._busy.discard(key)

        if sent < count:
            detail = failure or "图片服务本次返回的图片数量不足。"
            yield event.plain_result(f"已发送 {sent}/{count} 张。{detail}")

    async def terminate(self):
        if self._session is not None and not self._session.closed:
            await self._session.close()
