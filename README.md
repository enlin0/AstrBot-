# AstrBot 全年龄随机插画插件

多数据源随机动漫插画插件。支持中文标签搜索、多标签组合、数量控制、用户冷却与失败重试。
调用了nekosapi的api，限制了18+内容
## 特性

- **多数据源可插拔**：Pixiv（Lolicon）/ nekosapi，可按指令临时切换
- **中文标签**：直接输入中文，自动映射到数据源标签
- **多标签组合**：`|` 表示任一命中，`&` 表示同时满足
- **webp 自动转码**：统一转 JPEG，避免部分 QQ 客户端无法显示
- **全年龄过滤**：Lolicon 强制 `r18=0`；nekosapi 双层过滤（接口 `rating=safe` + 本地敏感标签黑名单）

## 安装

需要 Python 3.10+ 和支持 `astrbot.api` 插件接口的 AstrBot 4.x。

将 `astrbot_plugin_random_illustration` 文件夹放入 AstrBot 的 `data/plugins/`，
结构如下：

```
data/plugins/astrbot_plugin_random_illustration/
├── main.py               插件主逻辑
├── providers.py          数据源实现
├── tags.py               Pixiv 标签词典（459 条）
├── tags_nekosapi.py      nekosapi 标签词典 + 图量统计
├── _conf_schema.json     配置面板定义
├── metadata.yaml         插件元信息
└── requirements.txt      依赖
```

在 **AstrBot 实际使用的 Python 环境**中安装依赖：

```sh
python -m pip install -r data/plugins/astrbot_plugin_random_illustration/requirements.txt
```

然后在管理面板重载插件或重启 AstrBot。

## 指令

| 指令 | 说明 |
| --- | --- |
| `/插画` | 随机一张（使用默认标签/数据源） |
| `/插画 女仆` | 一张女仆插画 |
| `/插画 3 猫娘` | 三张猫娘插画 |
| `/插画 巫女 二张` | 两张巫女插画 |
| `/插画 女仆\|和服` | 女仆 **或** 和服 |
| `/插画 &女仆 &猫耳` | 女仆 **且** 猫耳（命中率较低） |
| `/插画 #lolicon 女仆` | 临时切到 Pixiv 源 |
| `/插画 #nekosapi 猫娘` | 临时切到 nekosapi 源 |
| `/插画 帮助` | 显示用法 |
| `/插画标签` | 查看当前源全部标签 |
| `/插画标签 服装` | 只看某个分组 |
| `/插画标签 女仆` | 查询单个标签 |
| `/插画标签 #nekosapi` | 查看指定源的标签 |

别名：`/随机插画`、`/标签`、`/插画tags`。

数量支持阿拉伯数字或一至十，可加「张」「份」「枚」。数量与标签顺序可交换。

## 数据源

| 数据源 | 标签体系 | 特点 |
| --- | --- | --- |
| `lolicon` | 459 条中文标签 | Pixiv 图源，标签最丰富，强制 `r18=0` |
| `nekosapi` | 59 条中文映射（38 个实际标签） | 规模较小，双层内容过滤，webp 需转码 |

默认数据源在配置面板 `data_source` 中设置，也可用 `#数据源名` 在指令中临时切换。

### nekosapi 标签热度

实测图量（`rating=safe` 条件下）：

| 标签 | 图量 | 标签 | 图量 |
| --- | --- | --- | --- |
| 少女 | 14649 | 短裙 | 2965 |
| 黑发 | 2179 | 连衣裙 | 1958 |
| 花 | 1762 | 棕发 | 1657 |
| 金发 | 1526 | 手套 | 1488 |
| 制服 | 1402 | 兽耳 | 1282 |
| 粉发 | 1240 | 树 | 1003 |
| 夜晚 | 902 | 蓝发 | 786 |
| 泳装 | 733 | 海滩 | 660 |
| 少年 | 602 | 女仆 | 597 |
| 紫发 | 572 | 红发 | 571 |
| 武器 | 571 | 短裤 | 480 |
| 湿身 | 426 | 白发 | 404 |
| 山 | 400 | 植物 | 367 |
| 晴天 | 328 | 猫娘 | 321 |
| 剑 | 273 | 眼镜 | 258 |
| 雨 | 257 | 兔耳 | 163 |
| 百合 | 143 | 吉他 | 60 |
| 兔女郎 | 45 | 运动服 | 29 |
| 马娘 | 23 | 插画 | 16 |

`/插画标签` 会以 `🔥` `★` `·` `△` 标注热度等级。

## 配置项

| 键 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| `data_source` | string | `nekosapi` | 默认数据源 |
| `default_tag` | string | 空 | 不填标签时使用 |
| `max_count` | int | 3 | 单次最多张数（1～10） |
| `cooldown_seconds` | int | 10 | 每用户冷却（0～3600） |
| `timeout_seconds` | int | 30 | 单次请求超时（5～120） |
| `retries` | int | 2 | 重试次数（0～3） |
| `max_image_mb` | int | 10 | 单图大小上限（1～20） |
| `image_size` | string | `regular` | 尺寸档位（仅 lolicon） |
| `exclude_ai` | bool | true | 排除 AI 作品（仅 lolicon） |
| `show_credit` | bool | true | 显示画师与作品信息 |

## 行为与限制

- 同一用户同一会话的请求不重叠，全局最多同时处理 3 个请求
- 冷却从请求被接受时开始计时，失败也计入
- 单次 HTTP 请求超时默认 30 秒，遇到 429 / 5xx 按指数退避重试
- 超过大小上限的图片会跳过；PNG / JPEG / GIF / WEBP 均做格式校验
- **webp 图片会自动转换为 JPEG**（Pillow，白底，quality 88）
- 部分发送失败时报告实际发送数，已发送的图片不会重发
- 插件不缓存图片，无独立数据目录
- 插件卸载或重载时关闭 HTTP 会话

## 内容过滤

### Lolicon

接口层强制 `r18=0`，并在代码中二次校验 `record["r18"] is not True`。
配置中不提供 R18 开关。

### nekosapi

采用两层过滤：

1. **接口层**：请求参数 `rating=safe`
2. **本地层**：命中以下标签的图片直接跳过

```
exposed_girl_breasts  large_breasts   medium_breasts   small_breasts
breasts               exposed_breasts nipples          nude
naked                 pussy           dick             penis
anus                  exposed_anus    cum              sex
futanari              explicit        uncensored       spread_legs
underwear_only
```

**为什么需要本地层**：实测该源 `rating` 字段存在误标，`rating=safe` 的样本中约 26%
带有 `exposed_girl_breasts` 等标签。加入本地过滤后，50 张取样残留为 0。

图片版权属于原作者，使用应遵循原作授权。

## 拓展新数据源

在 `providers.py` 中实现一个类，提供：

```python
class MyProvider:
    name = "myprovider"
    label = "显示名"
    supports_and = False        # 是否支持 & 组合（客户端过滤）

    async def fetch(self, http_get, tags, count, options):
        # http_get(url, limit, image=False) -> bytes
        # 返回 list[dict]，每项需包含 image_url，可选 title/artist/pid/source_url/tags/source
        ...
```

然后注册到 `PROVIDERS` 字典即可。

## 排查问题

| 现象 | 排查方向 |
| --- | --- |
| 连接失败 / 超时 | 检查到数据源的网络、代理、证书 |
| 有回复但看不到图片 | webp 转码是否生效；查看日志中「webp 已转换为 jpeg」 |
| HTTP 403 / 429 | 上游限流或 UA 策略，加大冷却时间 |
| 已发送 0/N | 检查 Bot 适配器、平台图片权限、AstrBot 日志 |
| 标签搜不到 | 发送 `/插画标签` 确认该源是否支持 |

开启日志：`data/cmd_config.json` 中设 `log_file_enable: true`，重启后日志在
`data/logs/astrbot.log`。

## 相关链接

- Lolicon API：https://api.lolicon.app/
- nekosapi：https://api.nekosapi.com/v4/docs
- AstrBot：https://github.com/AstrBotDevs/AstrBot

## 变更记录

### v1.2.2

- 日志规范整改：`main.py` 与 `providers.py` 的 logger 统一改为 `from astrbot.api import logger`，移除内置 `logging` 模块依赖

### v1.2.0

- 数据源由 nekos.best 更换为可插拔架构（Lolicon / nekosapi）
- 标签体系：4 个分类 → 459 条中文标签
- 新增多标签语法（`|` / `&`）
- 新增 webp 自动转 JPEG
- nekosapi 加入本地敏感标签过滤
- 新增 `/插画标签` 分组查询与热度标注

### v1.0.0

- 初版，基于 nekos.best，支持 4 个分类
