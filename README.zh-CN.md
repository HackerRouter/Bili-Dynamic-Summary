# BiliDynamicSummary（中文说明）

[English README](README.md)

一个通过 网页缓存数据 获取、分类、排序、AI总结 指定时间内 个性化B站动态（视频、图文、专栏等），基于 `prompt_toolkit` 的 TUI 工具。

![demo0](demo0.png)
![demo](demo.png)

## 功能
- 时间范围筛选（自定义 / 最近 24 小时 / 7 天 / 30 天 / 365 天 / 今年 / 不限）
- 关键词过滤（空格分词，AND 逻辑）
- 关注 UP 主动态数量排序（升序/降序）
- 列表 简略/详情 模式
- 动态列表分页浏览
- 本地缓存 + 过期时间（TTL）
- 每个 UP 主支持 AI 总结（可按总结句子反查对应动态）
- 中英文 UI（自动识别或配置）

## 环境要求
- Python 3.8+
- `requests`
- `prompt_toolkit`

安装依赖：
```powershell
python -m pip install requests prompt_toolkit
```

## 快速开始
```powershell
python BiliDynamicSummary.py --sessdata "你的 SESSDATA"
```

也可以传入完整 Cookie：
```powershell
python BiliDynamicSummary.py --cookie "你的完整 Cookie"
```

## 获取网页缓存数据的方式
以 Windows 环境下， Google Chrome 为例：

### 获取 SESSDATA
1. 打开 https://t.bilibili.com/
2. 按 F12 打开开发者工具，选中 More tabs 里的 Application
3. 可找到 Cookies 下名为 https://t.bilibili.com 的项
4. 选中后，其中有一项为 SESSDATA，复制即可

### 获取 Cookie
1. 打开 https://t.bilibili.com/
2. 按 F12 打开开发者工具，选择 Network 页面
3. 勾选 Preserve log，选择 XHR/Fetch 项
4. 刷新网页
5. 在搜索框输入：web-dynamic
6. 选中正确的项后，在 Headers 下，其 Request URL 类似：`https://api.bilibili.com/x/polymer/web-dynamic/v1/feed/all?...`
7. 往下滚动，可以在 Request Headers 下找到 Cookie 项，复制即可

--- 

## 使用流程
0. 在终端输入
```powershell
python BiliDynamicSummary.py --sessdata "你的 SESSDATA"
```
1. 进入 **当前设置** 页面
2. 选择 **编辑设置**（可选）
3. 选择 **开始检索**
4. 在 **选择 UP 主** 列表中选中你要查看的 UP 主动态
5. 进入动态列表分页浏览，可以选择查看详情
6. 在你查看的 UP 主 的列表页选择 **AI总结**，可查看 动态总结 和 其关联的动态

## 快捷键
- 方向键：选择
- 回车：确认
- Tab：切换当前选中焦点

## 参数说明
- `type`: 动态类型（`all` / `video` / `pgc` / `article`）
- `pages`: 最多请求页数（时间范围越大通常需要更高）
- `page_size`: 列表每页条数
- `sort`: UP 主排序方式（`desc` / `asc`）
- `view`: 列表模式（`summary` / `detail`）
- `keyword`: 关键词过滤（空格分词，全部命中才保留）
- `time_from`, `time_to`: 时间范围
- `cache`: 是否启用缓存
- `cache_ttl`: 缓存有效期（分钟）
- `summary_provider`: `local` / `openai` / `gemini` / `custom_openai`
- `summary_api_mode`: `chat_completions` / `responses`（OpenAI兼容提供方）
- `summary_model`: 对应提供方模型名
- `summary_api_key`: API 密钥（`local` 可留空）
- `summary_base_url`: `custom_openai` 使用的基础地址
- `summary_use_json_format`: 在 `chat_completions` 模式下是否发送 `response_format=json_object`
- `summary_extra_headers`: AI 请求额外 Header（JSON 对象）
- `summary_max_items`: 每次总结使用的动态上限
- `summary_timeout`: AI 总结请求超时秒数

### 关于 `pages`
接口以页数来抓取动态信息，`pages` 表示最多抓取的页数。时间范围越大，为覆盖更多历史动态，需要更大的 `pages`。

## 时间格式
自定义输入支持：
- `YYYY-MM-DD HH:MM`
- `YYYY-MM-DD HH:MM:SS`
- `YYYY-MM-DD`

## 缓存
缓存文件存放在 `cache/`。可在 TUI 或 `config.json` 中配置：
```json
{
  "lang": "auto",
  "cookie": "",
  "sessdata": "",
  "ui_wrap_width": 60,
  "cache": true,
  "cache_ttl_minutes": 60,
  "auto_save_auth": false,
  "summary": {
    "provider": "local",
    "api_mode": "chat_completions",
    "model": "",
    "api_key": "",
    "base_url": "",
    "use_json_format": true,
    "extra_headers": {},
    "max_items": 80,
    "timeout_seconds": 45
  }
}
```

### `config.json` 字段说明
- `lang`：`auto` | `zh-CN` | `en-US`。`auto` 按系统语言自动选择
- `cookie`：完整 Cookie 字符串（可选）。为空时也可以通过 `--cookie` 传入
- `sessdata`：`SESSDATA` 值（可选）。为空时也可以通过 `--sessdata` 传入
- `ui_wrap_width`：TUI 长文本换行宽度（程序会限制在 `40..200`）
- `cache`：`true` 或 `false`。控制是否读写本地缓存
- `cache_ttl_minutes`：缓存有效期（分钟），`<= 0` 表示不做过期判断
- `auto_save_auth`：自动把最新 `cookie`/`sessdata` 写回 `config.json`（默认 `false`）
- `summary.provider`：`local` | `openai` | `gemini` | `custom_openai` （OpenAI兼容）
- `summary.api_mode`：`chat_completions` | `responses`（OpenAI兼容提供方）
- `summary.model`：对应提供方模型名，例如 `gpt-4o-mini`、`gemini-1.5-flash`
- `summary.api_key`：`openai` 或 `gemini` 使用的 API 密钥
- `summary.base_url`：`custom_openai` 的基础地址（OpenAI 兼容接口），例如 `https://api.xxx.com/v1`
- `summary.use_json_format`：`chat_completions` 模式下发送 `response_format={"type":"json_object"}`
- `summary.extra_headers`：将 JSON 对象合并到 AI 请求头中，例如 `{"x-channel":"kiro"}`
- `summary.max_items`：AI 总结时最多使用的动态条数
- `summary.timeout_seconds`：AI 总结 HTTP 请求超时秒数

## 命令行参数
```text
--cookie         完整 Cookie 字符串
--sessdata       SESSDATA 值
--dedeuserid     DedeUserID 值（mid）
--bili-jct       bili_jct 值（CSRF）
--type           all | video | pgc | article
--pages          最大翻页数
--page-size      列表每页条数
--from           起始时间（YYYY-MM-DD HH:MM）
--to             结束时间（YYYY-MM-DD HH:MM）
--sort           asc | desc
--view           summary | detail
--keyword        关键词过滤
--cache          开启缓存
--no-cache       关闭缓存
--cache-ttl      缓存有效期（分钟，覆盖 config）
--auto-save-auth 开启自动保存最新 cookie/sessdata
--no-auto-save-auth 关闭自动保存最新 cookie/sessdata
--summary-provider  local | openai | gemini | custom_openai
--summary-api-mode  chat_completions | responses
--summary-model     AI模型名
--summary-api-key   AI提供方API密钥
--summary-base-url  custom_openai 基础地址
--summary-use-json-format 启用 response_format json_object
--summary-no-json-format  关闭 response_format json_object
--summary-extra-headers   额外请求头 JSON 对象字符串
--summary-max-items 总结使用动态上限
--summary-timeout   AI总结请求超时秒数
--lang           auto | zh-CN | en-US
--interactive    抓取下一页前询问
```

## 备注
- 需要登录后的 Cookie 才能访问动态接口。
- 未设置 API 密钥或 AI 请求失败时，会自动回退到本地简单总结。

## 免责声明
- 本工具仅供个人学习、研究与合法用途。
- 使用者需自行确保符合 B 站 服务条款及所在地法律法规。
- 请妥善保管敏感信息（`cookie`、`sessdata`、API 密钥），避免泄露或提交到公开仓库。
- AI 总结可能存在遗漏或错误，请以原始动态内容为准。

---

我写这个应用程序的唯一原因是为了跟上中国 Minecraft 技术社区的步伐，因为我已经忘记我的 Bilibili 帐户密码很多年了。
:P