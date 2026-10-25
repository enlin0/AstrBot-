"""可插拔数据源：Lolicon(Pixiv) 与 nekosapi。

每个 provider 暴露统一接口：
    name            数据源标识
    fetch(tags, count, options) -> list[dict]
    每个 dict 至少包含：image_url, title, artist, pid, source, tags(list)

设计目标是让主插件只关心「拿到图片列表」，不关心数据源细节。
"""

import json
import logging
from urllib.parse import quote

logger = logging.getLogger(__name__)


class ProviderError(Exception):
    """数据源返回错误。"""


def _build_url(base, params):
    return base + "?" + "&".join(
        f"{k}={quote(str(v), safe='')}" for k, v in params if v is not None
    )


class LoliconProvider:
    """Pixiv 图源，标签体系丰富，官方支持 r18=0。"""

    name = "lolicon"
    label = "Pixiv / Lolicon"
    base = "https://api.lolicon.app/setu/v2"
    supports_and = True

    async def fetch(self, http_get, tags, count, options):
        size = options.get("image_size", "regular")
        if size not in {"original", "regular", "small"}:
            size = "regular"

        params = [("r18", "0"), ("num", str(min(count, 20))), ("size", size)]
        if options.get("exclude_ai", True):
            params.append(("excludeAI", "true"))
        if tags:
            params.append(("tag", "|".join(tags)))

        url = _build_url(self.base, params)
        body = await http_get(url, 262144)
        try:
            payload = json.loads(body)
        except (ValueError, UnicodeDecodeError) as exc:
            raise ProviderError("数据源返回了无效数据。") from exc

        if not isinstance(payload, dict):
            raise ProviderError("数据源返回了无效数据。")
        if payload.get("error"):
            raise ProviderError(f"数据源错误：{str(payload['error'])[:80]}")

        records = []
        for record in payload.get("data") or []:
            if not isinstance(record, dict):
                continue
            if record.get("r18") is True:
                continue
            urls = record.get("urls")
            if not isinstance(urls, dict):
                continue
            order = (
                ["original", "regular", "small"]
                if size == "original"
                else ["regular", "original", "small"]
            )
            image = next(
                (urls[k] for k in order if isinstance(urls.get(k), str)), None
            )
            if not image:
                continue
            records.append(
                {
                    "image_url": image,
                    "title": str(record.get("title") or ""),
                    "artist": record.get("author"),
                    "pid": record.get("pid"),
                    "source_url": None,
                    "tags": list(record.get("tags") or []),
                    "source": self.name,
                }
            )
        return records


class NekosApiProvider:
    """nekosapi 图源，英文标签，规模较小。

    rating=safe 由接口过滤；额外做一次本地敏感标签检查，
    因为实测该源 rating 字段存在误标（safe 但含暴露标签）。
    """

    name = "nekosapi"
    label = "nekosapi"
    base = "https://api.nekosapi.com/v4/images"
    supports_and = False

    # 敏感标签，命中即跳过该图
    SENSITIVE = {
        "exposed_girl_breasts", "large_breasts", "medium_breasts",
        "small_breasts", "breasts", "exposed_breasts", "nipples",
        "nude", "naked", "pussy", "dick", "penis", "anus",
        "exposed_anus", "cum", "sex", "futanari", "explicit",
        "uncensored", "spread_legs", "underwear_only",
    }

    async def fetch(self, http_get, tags, count, options):
        # 多取一些，因为本地过滤会丢弃部分结果
        limit = min(max(count * 4, 12), 100)
        params = [("rating", "safe"), ("limit", str(limit))]
        if tags:
            params.append(("tags", ",".join(tags)))

        url = _build_url(self.base, params)
        body = await http_get(url, 524288)
        try:
            payload = json.loads(body)
        except (ValueError, UnicodeDecodeError) as exc:
            raise ProviderError("数据源返回了无效数据。") from exc

        items = payload.get("items") if isinstance(payload, dict) else None
        if not isinstance(items, list):
            raise ProviderError("数据源返回了无效数据。")

        records = []
        dropped = 0
        for item in items:
            if not isinstance(item, dict):
                continue
            if item.get("rating") not in (None, "safe"):
                dropped += 1
                continue
            item_tags = item.get("tags")
            if not isinstance(item_tags, list):
                item_tags = []
            lowered = {str(t).lower() for t in item_tags}
            if lowered & self.SENSITIVE:
                dropped += 1
                continue

            image = item.get("url")
            if not isinstance(image, str) or not image.startswith("https://"):
                continue

            artist = item.get("artist_name")
            source = item.get("source_url")
            records.append(
                {
                    "image_url": image,
                    "title": "",
                    "artist": artist if isinstance(artist, str) else None,
                    "pid": item.get("id"),
                    "source_url": source if isinstance(source, str) else None,
                    "tags": [str(t) for t in item_tags],
                    "source": self.name,
                }
            )
            if len(records) >= count:
                break

        if dropped:
            logger.info("nekosapi 本地过滤跳过 %s 张", dropped)
        return records


PROVIDERS = {
    "lolicon": LoliconProvider,
    "nekosapi": NekosApiProvider,
}


def get_provider(name):
    cls = PROVIDERS.get(str(name).strip().lower())
    if cls is None:
        cls = LoliconProvider
    return cls()
