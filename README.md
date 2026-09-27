# NoneBot2 SeaTalk 适配器

面向 SeaTalk 应用机器人的 NoneBot2 适配器，支持通过 WebSocket 接收事件、通过 HTTP 发送文本回复，并可选集成 Alconna。

支持 Python 3.10+、NoneBot 2.4+；使用 Alconna 扩展时需要 NoneBot 2.5+。**目前尚未完成真实 SeaTalk 环境的联调验证。**

项目以提供的 SDK 为协议参考，不打包 SDK 源码，运行时也不依赖该 SDK。已核实的协议见[协议依据](docs/references/seatalk-contracts.md)。

## 安装与配置

本项目尚未发布到 PyPI，请先在本地构建并安装：

```sh
uv build
python -m pip install dist/nonebot_adapter_seatalk-0.1.0-py3-none-any.whl 'nonebot2[httpx,websockets]>=2.4,<3'
```

将 `examples/.env.example` 复制为仓库根目录的 `.env`，填写应用配置，然后在仓库根目录运行：

```sh
python examples/bot.py
```

私聊发送 `/echo hello`，或在群聊中先 @ 机器人再发送命令，也可以在机器人已关注的话题中发送命令。示例插件会回复文本。请勿将 `.env` 提交到版本控制。

驱动必须同时支持 HTTP 和 WebSocket 客户端，无需提供公网回调服务器。示例配置：

```dotenv
DRIVER=~none+~httpx+~websockets
SEATALK_BOTS=[{"app_id":"your-app-id","app_secret":"your-app-secret","api_base":"https://matching-api-host.example","bot_seatalk_id":"your-bot-seatalk-id"}]
```

`SEATALK_BOTS` 是应用配置的 JSON 数组，可配置多个机器人：

| 配置项 | 说明 |
| --- | --- |
| `app_id` | 应用 ID，也是 NoneBot 中的机器人 ID；各应用之间不能重复 |
| `app_secret` | 应用密钥 |
| `ws_url` | WebSocket 地址，默认使用 SDK 地址 `wss://ws-openapi.haiserve.com/ws/bot` |
| `api_base` | 必填，应用所在环境对应的 HTTPS REST 地址；公开文档使用 `https://openapi.seatalk.io` |
| `bot_seatalk_id` | 可选，机器人账号的 SeaTalk ID，可在 App → Bot → SeaTalk ID 查看；与 `app_id` 不同 |

请确认 REST 与 WebSocket 地址对应同一应用环境。目前尚未验证公开 REST 地址与 SDK 的 haiserve WebSocket 地址能否配套使用；若部署环境提供其他地址，请显式配置。

在 SeaTalk 开放平台中完成以下设置：

1. 启用 Bot 能力，将应用设置为 Online。
2. 按需授予 **Send Message to Bot User**、**Send Message to Group Chat** 权限，并设置对应的服务范围。向群聊发送消息时，机器人必须已经加入该群。
3. 按需订阅私聊消息、群聊 @ 消息和话题消息等事件。
4. 启动机器人程序，在 Event Callback 中选择 WebSocket，并在连接保持在线时点击 Re-verify。

话题消息回调要求机器人已关注该话题，例如曾在话题中被 @。

## 消息与回复

以下代码用于异步处理函数，`bot` 和 `event` 由 NoneBot 提供：

```python
from nonebot.adapters.seatalk import Message, MessageSegment

# 回复当前事件所在的私聊、群聊或话题
result = await bot.send(event, "你好")

# 显式引用同一群聊或话题内的消息，仅支持群聊
await bot.send(event, "收到", quote_id=event.message_id)

# 主动发送消息
await bot.send_private_message("employee-code", "你好")
await bot.send_group_message("group-id", "你好", thread_id="root-message-id")

# 群聊 @ 使用数字形式的 SeaTalk ID，不能使用 employee_code
await bot.send_group_message(
    "group-id", Message("你好 ") + MessageSegment.at("12345", id_type="seatalk_id")
)
```

私聊和群聊均支持话题回复。消息引用仅支持群聊，私聊 API 文档未明确支持引用。被引用的消息、话题根消息须在七天内，引用消息还须属于当前会话流或话题。私聊发送目标必须提供 `employee_code`；事件缺少该字段时会报错，不会改发到其他会话。

| 内容类型 | 接收 | 发送 |
| --- | --- | --- |
| 文本 | 转换为原生文本消息段 | 单条正文 1–4096 个字符，默认使用纯文本格式 |
| @ 提及 | 根据唯一且不重叠的 `@用户名` 映射转换；歧义内容保留为文本 | 在群聊中 @ 指定数字 SeaTalk ID 的用户 |
| 引用回复 | 保留原生引用消息段及事件元数据 | 最多引用一条群聊消息 |
| 图片、文件、视频 | 保留类型及需要鉴权的媒体 URL | 暂不支持 |
| 卡片、合并转发、未知类型 | 保留原始载荷 | 暂不支持 |

官方文档未明确提及位置偏移量的单位，因此适配器仅使用无歧义的用户名文本映射，不猜测偏移量。命令预处理会移除开头可识别的机器人 @ 或昵称，并通过 `original_message` 保留原始消息。

媒体 URL 需要鉴权，七天后过期；适配器不会自动下载。消息编辑、撤回、成员变更和交互卡片点击作为通知事件处理，不会重新触发普通消息命令。

包含不支持内容或混合媒体的发送请求会在任何 HTTP 请求之前抛出 `UnsupportedMessage`。适配器不会自动拆分消息或重试发送。`SendResult.message_id` 可能为 `None`，尤其是私聊文本消息；不会生成虚假的消息 ID。

令牌被拒绝后，缓存会失效，下一次调用重新获取令牌，但不会重放本次失败的发送。`ActionFailed` 提供错误码、API 路径，以及服务端返回时的请求 ID、`Retry-After`。常见错误码：

| 错误码 | 含义 |
| --- | --- |
| `100` | 令牌无效或已过期 |
| `101` | 请求触发限流 |
| `103` | 应用缺少权限 |

可通过 `bot.request_api(method, path, ...)` 调用原始 JSON API。`path` 必须是以 `/` 开头、相对于已配置服务地址的路径，不允许指定其他主机或覆盖鉴权请求头。

## 可选 Alconna 集成

安装扩展依赖：

```sh
python -m pip install 'dist/nonebot_adapter_seatalk-0.1.0-py3-none-any.whl[alconna]'
```

先注册适配器，再加载 Alconna：

```python
import nonebot
from nonebot.adapters.seatalk import Adapter

nonebot.init()
nonebot.get_driver().register_adapter(Adapter)
nonebot.require("nonebot_plugin_alconna")
```

Alconna 会通过 `n-p-alc.uniseg.adapters` 入口自动加载 SeaTalk 支持。已测试版本为 Alconna 0.62.1，依赖范围为 `>=0.62.1,<0.63`。

```python
from nonebot_plugin_alconna import UniMessage
from nonebot_plugin_alconna.uniseg import Target

# 群聊话题目标通过 extra 指定 thread_id
await UniMessage.text("你好").send(
    target=Target("group-id", adapter="SeaTalk", extra={"thread_id": "root-id"}),
    bot=bot,
)

# 私聊 Target 的 ID 为 employee_code
await UniMessage.text("你好").send(
    target=Target("employee-code", private=True, adapter="SeaTalk"), bot=bot
)
```

接收的文本、用户提及、引用和媒体会转换为通用消息段；无法进一步解析的内容保留为 `Other`。发送支持文本、`At("user", "seatalk:12345")` 和群聊 `Reply`。文本样式按纯文本发送。

`employee_code` 无法直接用于发送 @，因此 `at_sender=True` 在部分事件中不可用。即使启用了 fallback，不支持的媒体或提及仍会抛出适配器的 `UnsupportedMessage`，不会静默转换成文本。发送回执缺少消息 ID 时，尝试从回执获取引用会抛出 `SerializeFailed`。

暂不支持撤回、编辑、目标枚举、作用域，以及通过 `Target.dump` → `Target.load` 恢复持久化目标。基础适配器和入口加载器可以在未安装 Alconna 的环境中导入。

## 事件投递与故障排查

适配器发出确认表示事件已被当前进程接收处理，不代表所有插件都执行成功。每个机器人最多同时处理 128 个未完成事件；处理期间持续去重，处理完成后在最多 4,096 条记录的缓存中保留十分钟。

缓存会跨 WebSocket 重连保留，但进程重启后失效。确认后进程崩溃可能导致未完成事件丢失，插件执行失败不会自动重放。处理容量耗尽时，适配器会关闭连接且不确认新事件；不保证服务端重投或消息恰好处理一次。

网络故障会触发重连，等待时间从一秒逐步增加至三十秒。注册被拒绝或连接被踢出时，该机器人停止重连，需要修正配置后重启进程。适配器日志包含应用 ID、事件 ID 和异常类别；NoneBot 与插件各自控制自己的日志内容。

## 开发与验证

```sh
uv sync --group dev --extra alconna
uv run --extra alconna pytest -q
uv run ruff check nonebot tests examples
uv run ruff format --check nonebot tests examples
uv build
SEATALK_TEST_WHEEL=dist/nonebot_adapter_seatalk-0.1.0-py3-none-any.whl uv run pytest tests/test_distribution.py -q
```

CI 会在源码目录之外安装构建好的 wheel，并检查以下组合：

| Python | NoneBot | Pydantic | Alconna |
| --- | --- | --- | --- |
| 3.10 | 2.4 | 1.x | 不安装 |
| 3.14 | 2.5 | 2.x | 不安装 |
| 3.12 | 2.5 | 2.x | 0.62.1 |

源码测试会扩展 NoneBot 的适配器搜索路径；安装包测试设置 `SEATALK_TEST_INSTALLED=1`，禁用这一辅助行为。

目前自动化测试已覆盖协议处理、命令回复、消息转换、HTTP 发送及 Alconna 集成。真实环境仍需验证私聊回复、群聊 @ 回复、话题回复和重连，以及 REST/WebSocket 环境配对和服务端重投行为。
