# NoneBot2 SeaTalk 适配器

面向 SeaTalk 应用机器人的 NoneBot2 适配器，支持通过 WebSocket 接收事件、通过 HTTP 发送文本和图片回复，并可选集成 Alconna。

本项目由 **GPT-6-Astra** 编写，采用 [MIT 许可证](LICENSE)。

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
SEATALK_BOTS=[{"app_id":"your-app-id","app_secret":"your-app-secret","reply_mode":"thread"}]
```

`SEATALK_BOTS` 是应用配置的 JSON 数组，可配置多个机器人：

| 配置项 | 说明 |
| --- | --- |
| `app_id` | 应用 ID，也是 NoneBot 中的机器人 ID；各应用之间不能重复 |
| `app_secret` | 应用密钥 |
| `ws_url` | WebSocket 地址，默认使用 SDK 地址 `wss://ws-openapi.haiserve.com/ws/bot` |
| `api_base` | 可选，HTTPS REST 地址，默认 `https://openapi.seatalk.io` |
| `reply_mode` | 可选，默认 `thread`：群聊消息在以原消息为根的分支中回复；设为 `quote` 则在当前群聊引用回复。原消息已在分支中时，两种模式均在原分支内引用回复 |
| `bot_seatalk_id` | 可选，机器人账号的 SeaTalk ID，可在 App → Bot → SeaTalk ID 查看；与 `app_id` 不同 |

请确认 REST 与 WebSocket 地址对应同一应用环境。目前尚未验证公开 REST 地址与 SDK 的 haiserve WebSocket 地址能否配套使用；若部署环境提供其他地址，请显式配置。

在 SeaTalk 开放平台中完成以下设置：

1. 启用 Bot 能力，将应用设置为 Online。
2. 按需授予 **Send Message to Bot User**、**Send Message to Group Chat** 权限，并设置对应的服务范围。向群聊发送消息时，机器人必须已经加入该群。
3. 按需订阅私聊消息、群聊 @ 消息和话题消息等事件。
4. 启动机器人程序，在 Event Callback 中选择 WebSocket，并在连接保持在线时点击 Re-verify。

话题消息回调要求机器人已关注该话题，例如曾在话题中被 @。

群聊“机器人被 @”事件中，若提及列表只包含一个可明确映射的对象，适配器会自动
识别并移除开头的机器人 @，因此通常的 `@Bot 命令` 无需配置 `bot_seatalk_id`。
推断只作用于当前事件，不保存为机器人身份。多人提及、缺失或无法明确映射的提及
不会猜测；这些情况可配置 `bot_seatalk_id`。显式配置始终优先，原始消息保持不变。

## 消息与回复

以下代码用于异步处理函数，`bot` 和 `event` 由 NoneBot 提供：

```python
from nonebot.adapters.seatalk import Message, MessageSegment

# 按 reply_mode 回复群消息；已有话题内引用回复；私聊保留原会话
result = await bot.send(event, "你好")

# 显式引用同一群聊或话题内的消息，仅支持群聊
await bot.send(event, "收到", quote_id=event.message_id)

# 主动发送消息
await bot.send_private_message("employee-code", "你好")
await bot.send_group_message("group-id", "你好", thread_id="root-message-id")

# 支持图片字节、本地路径、file URI、base64:// 和公开 HTTP(S) 图片 URL
await bot.send(event, MessageSegment.image(image_bytes))
# 自动按顺序拆成文字、图片、文字三个请求
await bot.send(event, Message("说明") + MessageSegment.image(image_bytes) + "结束")

# 群聊 @ 使用数字形式的 SeaTalk ID，不能使用 employee_code
await bot.send_group_message(
    "group-id", Message("你好 ") + MessageSegment.at("12345", id_type="seatalk_id")
)
```

私聊和群聊均支持话题回复。消息引用仅支持群聊，私聊 API 文档未明确支持引用。被引用的消息、话题根消息须在七天内，引用消息还须属于当前会话流或话题。私聊发送目标必须提供 `employee_code`；事件缺少该字段时会报错，不会改发到其他会话。

`reply_mode` 仅用于事件驱动的群消息回复，原生 `bot.send` 与 Alconna 的事件及事件派生目标行为一致。显式 `quote_id` 或 Reply 消息段优先，保留原会话或话题；`quote_id=None` 可关闭本次自动回复策略。主动调用 `send_group_message`、`send_private_message` 或手动创建 Alconna `Target` 时，仍由调用方指定话题与引用。无原消息 ID 的事件不自动添加话题或引用。

| 内容类型 | 接收 | 发送 |
| --- | --- | --- |
| 文本 | 转换为原生文本消息段 | 单条正文 1–4096 个字符，默认使用纯文本格式 |
| @ 提及 | 根据唯一且不重叠的 `@用户名` 映射转换；歧义内容保留为文本 | 在群聊中 @ 指定数字 SeaTalk ID 的用户 |
| 引用回复 | 保留原生引用消息段及事件元数据 | 最多引用一条群聊消息 |
| 图片 | 保留类型及需要鉴权的媒体 URL | 图片字节、本地文件、base64、公开 HTTP(S) URL；自动拆分图文 |
| 文件、视频 | 保留类型及需要鉴权的媒体 URL | 暂不支持 |
| 卡片、合并转发、未知类型 | 保留原始载荷 | 暂不支持 |

官方文档未明确提及位置偏移量的单位，因此适配器仅使用无歧义的用户名文本映射，不猜测偏移量。命令预处理会移除开头可识别的机器人 @ 或昵称，并通过 `original_message` 保留原始消息。

建议配置 `bot_seatalk_id` 以准确识别并移除命令开头的机器人 @。未配置时不会把其他用户的提及当作机器人，也不会删除任何提及；平台明确标记的群聊 @ 事件仍保留 `to_me` 标记。多个提及中的非机器人提及和用户正文会保留。

媒体 URL 需要鉴权，七天后过期；适配器不会自动下载。消息编辑、撤回、成员变更和交互卡片点击作为通知事件处理，不会重新触发普通消息命令。

按官方应用消息 API 文档，图片支持 PNG、JPEG、GIF，base64 编码后的正文最多 5 MB；适配器保守按 5,000,000 字节检查，不会自动转码或压缩。群聊图片的话题和引用有明确文档支持；私聊图片会保留调用方传入的话题参数，但该组合仍需真实环境验证。公开图片 URL 下载不携带应用令牌；收到的鉴权媒体 URL 不会自动转发，需由调用方提供图片字节。

图文混合消息自动按顺序拆分，每张图片一个请求，连续文字和提及保留为一个文本请求；每段保留同一个会话、话题和引用。单请求返回 `SendResult`，多请求返回实际回执的 `list[SendResult]`，Alconna 同样保留每段回执。不会生成虚假的消息 ID，服务端未提供时 `message_id` 为 `None`。

发送前会检查全部内容并准备图片；不支持的类型或无效图片会抛出 `UnsupportedMessage`。下载失败抛出 `NetworkError`。某段发送失败时立即停止并报告错误，已发出的前面片段不会撤回，也不会自动重试，避免重复发送。

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

接收的文本、用户提及、引用和媒体会转换为通用消息段；无法进一步解析的内容保留为 `Other`。发送支持文本、`Image(raw=...)` / `Image(path=...)` / `Image(url=...)`、`At("user", "seatalk:12345")` 和群聊 `Reply`。文本样式按纯文本发送。

`employee_code` 无法直接用于发送 @，因此 `at_sender=True` 在部分事件中不可用。即使启用了 fallback，不支持的媒体或提及仍会抛出适配器的 `UnsupportedMessage`，不会静默转换成文本。发送回执缺少消息 ID 时，尝试从回执获取引用会抛出 `SerializeFailed`。

暂不支持撤回、编辑、目标枚举、作用域，以及通过 `Target.dump` → `Target.load` 恢复持久化目标。基础适配器和入口加载器可以在未安装 Alconna 的环境中导入。

## 事件投递与故障排查

适配器发出确认表示事件已被当前进程接收处理，不代表所有插件都执行成功。每个机器人最多同时处理 128 个未完成事件；处理期间持续去重，处理完成后在最多 4,096 条记录的缓存中保留十分钟。

缓存会跨 WebSocket 重连保留，但进程重启后失效。确认后进程崩溃可能导致未完成事件丢失，插件执行失败不会自动重放。处理容量耗尽时，适配器会关闭连接且不确认新事件；不保证服务端重投或消息恰好处理一次。

网络故障会触发重连，等待时间从一秒逐步增加至三十秒。注册被拒绝或连接被踢出时，该机器人停止重连，需要修正配置后重启进程。适配器会记录连接尝试、注册后的连接成功、已建立连接的断开、临时故障类别及重连等待时间；正常关闭只记录断开，不报告重连故障。拒绝与踢出日志显示原因类别，不回显服务端原始错误载荷。

NoneBot 入站消息日志显示应用、事件和消息 ID、发送者的 `employee_code` / `seatalk_id`、群聊或私聊、话题（如有）以及 `original_message` 的可读正文。提及保留实际用户名显示，媒体、卡片和未知消息仅显示类型摘要，不记录需要鉴权的 URL 或原始载荷。正文中的 Loguru 标签会转义。事件的 `username` 仅来自回调中实际存在的字符串用户名，缺失时为空，不以用户 ID 代替。适配器不记录应用密钥、注册令牌或鉴权请求头；NoneBot 与插件各自控制自己的日志内容。

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
