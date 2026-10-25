# AstrBot 全年龄随机插画插件

使用 nekos.best 的全年龄插画接口，通过 AstrBot 指令发送图片。不需要 API Key。
参考所提供代码的 AstrBot 插件结构重新实现；图片来源采用 nekos.best。
分类选择并非任意标签搜索，不抓取原链接页面。

## 安装

需要 Python 3.10+ 和支持 `astrbot.api` 插件接口的 AstrBot 4.x。
将整个 `astrbot_plugin_random_illustration` 文件夹复制到 AstrBot 的
`data/plugins/`，确保 `main.py` 位于
`data/plugins/astrbot_plugin_random_illustration/main.py`。

在 **AstrBot 实际使用的 Python 环境** 中运行：

```sh
python -m pip install -r data/plugins/astrbot_plugin_random_illustration/requirements.txt
```

然后在 AstrBot 管理面板重载插件或重启 AstrBot。
插件面板可设置数量、默认分类、用户冷却、超时、重试、大小上限和来源显示。

## 指令

| 指令 | 行为 |
| --- | --- |
| `/插画` | 默认分类的一张图片 |
| `/随机插画` | 同上 |
| `/插画 3 猫娘` | 三张猫娘插画 |
| `/插画 狐娘 二张` | 两张狐娘插画 |
| `/插画 少年` | 一张少年插画 |
| `/插画 帮助` | 显示用法 |

分类：少女（waifu）、猫娘（neko）、狐娘（kitsune）、少年（husbando）。
数量可用阿拉伯数字或一至十，允许加“张”或“份”，实际受单次上限约束。
数量与分类之间使用空格，顺序可交换；一次最多选择一个分类。
若修改了 AstrBot 的指令前缀，请使用对应前缀；群聊触发条件遵循 AstrBot 配置。

## 行为与限制

- 默认每次最多 3 张，可配置为 1～5 张。
- 同一会话内每位用户默认冷却 10 秒，从接受请求开始计时，失败也计入冷却。
- 同一用户同一会话的请求不重叠，全局最多同时处理 3 个请求。
- 单次 HTTP 请求默认超时 25 秒，网络错误或 HTTP 429 / 5xx 默认再试 2 次。
- 默认拒绝超过 10 MiB 的图片，可配置为 1～20 MiB。
- 下载图片字节后交给 AstrBot 图片组件发送，无插件图片缓存目录。
- 默认显示画师和原作链接；图片版权属于原作者，使用应遵循原作授权。
- 全年龄分类来自上游服务的内容政策，本插件不做独立视觉内容审核。
- 运行 AstrBot 的机器需要能通过 HTTPS 访问 nekos.best。支持标准
  `HTTPS_PROXY` 环境变量；设置后重启 AstrBot 生效。
- 插件卸载或重载时关闭 HTTP 会话。

接口文档：https://docs.nekos.best/
AstrBot：https://github.com/AstrBotDevs/AstrBot

## 排查问题

提示连接失败或超时：检查部署机器到 nekos.best 的网络、代理和证书。
HTTP 403：检查上游是否调整了 User-Agent 要求或访问策略。
已发送 0/N 且提示发送失败：检查 Bot 适配器、平台图片权限及 AstrBot 日志。
HTTP 429：上游限流，可增加冷却时间，稍后重试。
数量不足或单图失败会报告实际发送数，已发送图片不会因后续失败而重新发送。

已在线检查 API 分类与响应格式，并核对 AstrBot 图片字节组件接口。
44 项模拟检查通过，涵盖指令解析、输入限制、冷却、并发限制、部分发送失败、
HTTP 重试、响应大小限制、来源地址校验和配置默认值。
这些检查使用替代的框架与 HTTP 对象；本机未安装 AstrBot 和 aiohttp，
真实 Bot 平台的插件加载与发图仍需部署后验证。
