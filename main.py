import asyncio
import io
import json
import logging
import math
import re
import time
from collections import OrderedDict
from urllib.parse import quote, urlsplit

import aiohttp
from astrbot.api import AstrBotConfig
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import Image, Plain
from astrbot.api.star import Context, Star, register

try:
    from .tags import ALIASES, GROUPS, TOTAL_TAGS
    from .providers import ProviderError, get_provider
    from . import tags_nekosapi
except ImportError:  # 兼容以脚本方式加载
    from tags import ALIASES, GROUPS, TOTAL_TAGS
    from providers import ProviderError, get_provider
    import tags_nekosapi

logger = logging.getLogger(__name__)

USER_AGENT = "AstrBotRandomIllustration/1.2 (https://github.com/AstrBotDevs/AstrBot)"




NUMBERS = dict(zip("一二三四五六七八九十", range(1, 11)))
HELP = (
    "全年龄随机插画（数据源 Pixiv / Lolicon，r18 强制关闭）\n"
    "━━━━━━━━━━━━━\n"
    "/插画 —— 随机一张\n"
    "/插画 女仆 —— 女仆插画\n"
    "/插画 3 猫耳 —— 三张猫耳插画\n"
    "/插画 巫女 二张 —— 两张巫女插画\n"
    "━━━━━━━━━━━━━\n"
    "多标签（任一命中）：\n"
    "/插画 女仆|和服\n"
    "多标签（同时满足，命中率较低）：\n"
    "/插画 &女仆 &猫耳\n"
    "━━━━━━━━━━━━━\n"
    f"/插画标签 —— 查看全部 {TOTAL_TAGS} 条标签\n"
    "/插画标签 服装 —— 只看某个分类\n"
    "/插画标签 女仆 —— 查询单个标签\n"
    "━━━━━━━━━━━━━\n"
    "标签与数量顺序可交换，也支持 /随机插画。"
)

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC = b"\xff\xd8\xff"
GIF_MAGIC = (b"GIF87a", b"GIF89a")
WEBP_MAGIC = b"RIFF"


class FetchError(Exception):
    pass


def bounded_int(config, key, default, lower, upper):
    try:
        value = int(config.get(key, default))
    except (TypeError, ValueError, OverflowError):
        value = default
    return max(lower, min(upper, value))


def resolve_tag(raw, aliases=None):
    """把用户输入解析成 Lolicon 可用的标签。"""
    table = aliases if aliases is not None else ALIASES
    token = raw.strip()
    if not token:
        return ""
    if token in table:
        return table[token]
    lowered = token.lower()
    for key, value in table.items():
        if key.lower() == lowered:
            return value
    # 原样返回（支持日文/英文原生标签）
    return token


def parse_request(arguments, default_tag, max_count, aliases=None):
    """解析参数：返回 (数量, 标签列表, 是否 AND 模式)。

    支持：
      /插画 女仆
      /插画 3 女仆
      /插画 女仆 二张
      /插画 女仆|和服      -> OR
      /插画 &女仆 &猫耳    -> AND
    """
    count = 1
    has_count = False
    tags = []
    and_mode = False

    for raw in arguments:
        if not raw:
            continue
        token = str(raw).strip()
        if not token:
            continue

        # 数量解析
        match = re.fullmatch(r"([0-9]+|[一二三四五六七八九十])(?:张|份|枚)?", token)
        if match:
            if has_count:
                raise ValueError("数量只能填写一次。")
            number = match.group(1)
            count = NUMBERS[number] if number in NUMBERS else int(number)
            has_count = True
            continue

        # AND 模式标记
        if token.startswith("&"):
            and_mode = True
            token = token[1:].strip()
            if not token:
                continue

        # 竖线分隔的多标签
        parts = [p for p in re.split(r"[|｜、,，]", token) if p.strip()]
        for part in parts:
            resolved = resolve_tag(part, aliases)
            if resolved and resolved not in tags:
                tags.append(resolved)

    if not 1 <= count <= max_count:
        raise ValueError(f"每次可以获取 1～{max_count} 张插画。")

    if not tags:
        tags = [default_tag] if default_tag else []

    return count, tags, and_mode


def looks_like_image(data):
    if not data:
        return False
    return (
        data.startswith(PNG_MAGIC)
        or data.startswith(JPEG_MAGIC)
        or data.startswith(GIF_MAGIC)
        or (data.startswith(WEBP_MAGIC) and len(data) > 12 and data[8:12] == b"WEBP")
    )

def convert_webp_to_jpeg(data, quality=88):
    """把 webp 转成 jpeg。QQ 对 webp 兼容性差，转码后才能稳定显示。

    失败时返回 None，由调用方决定是否原文发送。
    """
    try:
        from PIL import Image as PILImage
    except ImportError:
        logger.warning("未安装 Pillow，无法转换 webp")
        return None
    try:
        with PILImage.open(io.BytesIO(data)) as img:
            if img.mode in ("RGBA", "LA", "P"):
                background = PILImage.new("RGB", img.size, (255, 255, 255))
                rgba = img.convert("RGBA")
                background.paste(rgba, mask=rgba.split()[-1])
                img = background
            else:
                img = img.convert("RGB")
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=quality, optimize=True)
            return buffer.getvalue()
    except Exception:
        logger.exception("webp 转换失败")
        return None



@register(
    "astrbot_plugin_random_illustration",
    "Local",
    "全年龄随机动漫插画（Pixiv 数据源），支持标签、数量、冷却",
    "1.1.0",
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
            timeout = bounded_int(self.config, "timeout_seconds", 30, 5, 120)
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=timeout),
                headers={"User-Agent": USER_AGENT},
                connector=aiohttp.TCPConnector(limit=8),
                trust_env=True,
            )
        return self._session

    async def _get(self, url, limit, image=False):
        retries = bounded_int(self.config, "retries", 2, 0, 3)
        for attempt in range(retries + 1):
            delay = min(2 ** attempt, 5)
            try:
                headers = {"Referer": "https://www.pixiv.net/"} if image else {}
                async with self._client().get(
                    url, allow_redirects=True, headers=headers
                ) as response:
                    if response.status != 200:
                        retryable = response.status == 429 or response.status >= 500
                        if not retryable or attempt == retries:
                            raise FetchError(
                                f"图片服务暂时不可用（HTTP {response.status}）。"
                            )
                        retry_after = response.headers.get("Retry-After", "")
                        if retry_after.isdigit():
                            delay = min(max(int(retry_after), delay), 10)
                    else:
                        content_type = response.headers.get("Content-Type", "").lower()
                        if image and content_type and not content_type.startswith("image/"):
                            raise FetchError("图片服务返回的格式不正确。")
                        if (
                            response.content_length is not None
                            and response.content_length > limit
                        ):
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

    def _active_tags(self, source):
        """按数据源返回对应的标签词典。"""
        if source == "nekosapi":
            return tags_nekosapi.ALIASES, tags_nekosapi.GROUPS, tags_nekosapi.TOTAL_TAGS
        return ALIASES, GROUPS, TOTAL_TAGS

    async def _metadata(self, tags, count, and_mode, source):
        """通过 provider 拉取元数据。"""
        provider = get_provider(source)
        options = {
            "image_size": str(self.config.get("image_size", "regular")),
            "exclude_ai": bool(self.config.get("exclude_ai", True)),
        }

        # AND 模式只有支持的数据源才做客户端二次过滤
        is_and = and_mode and provider.supports_and and len(tags) > 1
        fetch_count = min(count * 5, 50) if is_and else count

        logger.info(
            "插图请求 source=%s tags=%s num=%s and=%s",
            provider.name, tags, fetch_count, is_and,
        )

        records = await provider.fetch(self._get, tags, fetch_count, options)

        if is_and:
            filtered = []
            for record in records:
                joined = " ".join(str(t) for t in record.get("tags") or []).lower()
                if all(str(t).lower() in joined for t in tags):
                    filtered.append(record)
            records = filtered

        if not records:
            raise ProviderError("暂时没有找到符合条件的插画，换个标签试试。")
        return records[:count]

    def _credit(self, record):
        artist = str(record.get("artist") or "未知")[:60]
        pid = record.get("pid")
        title = str(record.get("title") or "").strip()[:60]
        source = record.get("source_url")
        source_name = record.get("source") or "unknown"

        parts = [f"\n画师：{artist}"]
        if title:
            parts.append(f"标题：{title}")
        if pid:
            parts.append(f"ID：{pid}")
        parts.append(
            "来源：Pixiv" if source_name == "lolicon" else "来源：nekosapi"
        )
        credit = " | ".join(parts)
        if isinstance(source, str) and source.startswith("https://"):
            credit += f"\n原作：{source[:300]}"
        return credit

    @filter.command("插画", alias={"随机插画"})
    async def illustration(
        self, event: AstrMessageEvent, first: str = "", second: str = ""
    ):
        if str(first).lower() in {"帮助", "help", "?"}:
            yield event.plain_result(HELP)
            return

        max_count = bounded_int(self.config, "max_count", 3, 1, 10)

        # 数据源：配置默认，可用 #源名 前缀临时切换
        source = str(self.config.get("data_source", "lolicon")).strip().lower()
        raw_args = [str(first or ""), str(second or "")]
        for idx, arg in enumerate(raw_args):
            token = arg.strip()
            if token.startswith("#"):
                candidate = token[1:].strip().lower()
                if candidate in {"lolicon", "pixiv"}:
                    source = "lolicon"
                    raw_args[idx] = ""
                elif candidate in {"nekosapi", "nekos"}:
                    source = "nekosapi"
                    raw_args[idx] = ""
                else:
                    yield event.plain_result(
                        "未知数据源。可用：#lolicon（Pixiv）、#nekosapi"
                    )
                    return

        tag_map, _groups, _total = self._active_tags(source)
        default_tag = str(self.config.get("default_tag", "") or "").strip()
        if default_tag:
            default_tag = resolve_tag(default_tag, tag_map)

        try:
            count, tags, and_mode = parse_request(
                tuple(raw_args), default_tag, max_count, tag_map
            )
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
                records = await self._metadata(tags, count, and_mode, source)
                limit = bounded_int(self.config, "max_image_mb", 10, 1, 20) * 1024 * 1024
                for record in records:
                    try:
                        data = await self._get(record["image_url"], limit, image=True)
                        if not looks_like_image(data):
                            raise FetchError("图片文件格式校验失败。")

                        # webp 在部分 QQ 客户端无法显示，统一转成 jpeg
                        if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
                            converted = convert_webp_to_jpeg(data)
                            if converted:
                                data = converted
                                logger.info("webp 已转换为 jpeg（%s 字节）", len(data))
                            else:
                                logger.warning("webp 转换失败，按原格式发送")

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

    @filter.command("插画标签", alias={"标签", "插画tags", "随机插画标签"})
    async def illustration_tags(self, event: AstrMessageEvent, query: str = ""):
        source = str(self.config.get("data_source", "lolicon")).strip().lower()

        query = str(query or "").strip()
        # 支持 /插画标签 #nekosapi 切换查看
        if query.startswith("#"):
            candidate = query[1:].strip().lower()
            if candidate in {"nekosapi", "nekos"}:
                source = "nekosapi"
            elif candidate in {"lolicon", "pixiv"}:
                source = "lolicon"
            else:
                yield event.plain_result("未知数据源。可用：#lolicon、#nekosapi")
                return
            query = ""

        tag_map, groups, total = self._active_tags(source)
        label = "nekosapi" if source == "nekosapi" else "Pixiv / Lolicon"
        COUNTS = tags_nekosapi.TAG_COUNTS if source == "nekosapi" else {}
        heat_label = tags_nekosapi.heat if source == "nekosapi" else (lambda c: "")

        # 无参数：按分组列出全部标签（带图量标注）
        if not query:
            lines = [f"可用标签 — {label}（共 {total} 条）"]
            if source == "nekosapi":
                lines.append("🔥≥1000  ★≥300  ·≥100  △<100")
            lines.append("")
            for name, group in groups:
                items = []
                for en, cn in sorted(group.items(), key=lambda kv: -(COUNTS.get(kv[0]) or 0)):
                    count = COUNTS.get(en)
                    mark = heat_label(count)
                    suffix = f"{count}" if count else "?"
                    items.append(f"{cn}{mark}{suffix}")
                lines.append(f"【{name}】{len(group)} 条")
                lines.append("、".join(items))
                lines.append("")
            lines.append("用法：/插画 标签名   或   /插画 3 标签名")
            lines.append("多标签：/插画 女仆|和服")
            lines.append("查详情：/插画标签 女仆")
            yield event.plain_result("\n".join(lines).strip())
            return

        # 分组名查询
        for name, group in groups:
            if query in name or name in query:
                keys = "、".join(sorted(group.keys()))
                yield event.plain_result(
                    f"【{name}】共 {len(group)} 条 — {label}\n{keys}\n\n"
                    f"用法：/插画 {sorted(group.keys())[0]}"
                )
                return

        # 精确命中
        if query in tag_map:
            en = tag_map[query]
            count = COUNTS.get(en)
            count_line = f"\n可用图片约 {count} 张" if count else ""
            yield event.plain_result(
                f"「{query}」→ {label} 标签：{en}{count_line}\n"
                f"用法：/插画 {query}"
            )
            return

        # 模糊搜索
        lowered = query.lower()
        fuzzy = [
            f"{k}（{v}）"
            for k, v in tag_map.items()
            if lowered in k.lower() or lowered in str(v).lower()
        ]
        if fuzzy:
            yield event.plain_result(
                f"包含「{query}」的标签（{len(fuzzy)} 条）：\n"
                + "、".join(fuzzy[:60])
            )
            return

        # nekosapi 支持直接输入英文标签
        if source == "nekosapi" and re.fullmatch(r"[a-z_]+", lowered):
            yield event.plain_result(
                f"「{query}」不在中文别名表中。\n"
                f"如果这是 nekosapi 的英文标签，可以直接使用：/插画 {query}\n"
                f"发送 /插画标签 查看已知标签。"
            )
            return

        yield event.plain_result(
            f"没有找到「{query}」。\n发送 /插画标签 查看全部 {total} 条。"
        )

    async def terminate(self):
        if self._session is not None and not self._session.closed:
            await self._session.close()
