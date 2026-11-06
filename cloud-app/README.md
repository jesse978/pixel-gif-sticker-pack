# 真人照片表情包：云端入口

此目录是 **[pixel-gif-sticker-pack](https://github.com/WoYun520/pixel-gif-sticker-pack) 原项目的薄封装**。
加字、动效、GIF 编码、技术校验、离线画廊和 GIF ZIP 均直接运行仓库原有的
[`scripts/export_pack.py`](../scripts/export_pack.py)，没有另写合成引擎。
原脚本、原 Skill 和参考文档保持原样，基线版本见 [UPSTREAM.json](UPSTREAM.json)。

你的仓库：<https://github.com/jesse978/pixel-gif-sticker-pack>。
后续修改在此 fork 中提交，`upstream` 指向原作者仓库。

## 运行

Python 3.12+。从本仓库根目录开始：

```bash
cd cloud-app
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
bash start.sh
```

浏览器打开终端输出的本机地址 `http://127.0.0.1:8000`。
云端机器的这个地址用于云端浏览器或受支持的端口转发，不能当成其他设备可访问的公网网址。
当前任务没有发布公网服务。

如需让已有的私有开发代理访问服务，可用 `STICKER_HOST=0.0.0.0 bash start.sh`。
生产 HTTPS 部署应启用 `STICKER_SECURE_COOKIE=true`，在服务前增加登录/访问控制；
当前是单进程、会话隔离的开发工作台，不是多租户付费平台。
原项目的 MP4 导出另需 FFmpeg；网页版本提供原生 GIF 播放和离线画廊，不依赖 FFmpeg。

## 三种用法

1. **真人照片生成**：在服务端 `.env` 设置 `OPENAI_API_KEY`，重启。
   选择一张本人或获准使用的单人照片，勾选 1–8 个表情，选择真人/手绘/像素风并修改文案。
   点击生成后，服务端用同一张参考照片，通过 Image Edits API 请求一张透明姿势图集。
   提示词要求保留脸型、发型、肤色、眼镜和服装，并为每个格子生成不同表情或姿势。
   API 的实际人物一致性和图集布局需要用照片验收，尚不能仅凭代码保证。
2. **导入透明图集**：不需要密钥。按表情顺序导入真正透明的 PNG：
   1 张 `1×1`，2 张 `2×1`，3–4 张 `2×2`，5–8 张 `4×2`，未用的格子保持透明。
   此入口直接连接原项目的 atlas / manifest 工作流。
3. **开源示例体验**：不需要照片或密钥。使用仓库鲸鱼娘示例的首帧角色区域，
   去掉原有文案区后组成演示图集，再调用原始脚本重新导出。**不是新生成的 AI 作品，也不是照片变换结果。**

所有入口都要经过图集检查：按阅读顺序确认每格的角色、表情、完整头发和双手、透明间隔。
确认后才运行原脚本。错误图集不应直接批量导出；清除后重新准备即可。
技术校验通过只说明格式、边距和循环符合脚本要求，不代表真人相似度或视觉效果已获验收。

## 交付内容

- 原脚本生成的 512×512 高清 GIF，或明确选择像素风时的 320×320 GIF。
- 24 帧、80ms/帧、约 1.92 秒透明循环。属于原项目的轻动效：位移、弹跳、摇摆、形变，
  不属于逐帧重新绘制的肢体动作。
- 原脚本生成的 GIF ZIP，包含分类目录和 `动图浏览.html`，解压即可离线预览。
- 每张最终 GIF 的首帧 PNG 及 PNG 合集 ZIP。PNG 为额外提取，没有修改原 GIF ZIP。
- 下载路径带会话检查，照片和生成图集不会进入可分享的表情 ZIP。

## 图像服务、隐私和费用

- **选择文件时只在浏览器预览**。点击照片生成且确认处理后，才上传到本服务并发送给已配置的服务商。
- 参考照片先按 EXIF 纠正方向，去掉 EXIF/GPS 等元数据、限制输入尺寸，再发往 Image Edits。
  服务端不把原照片写入持久存储；照片的像素仍会被发送给外部图像服务。
- 密钥只从服务端环境/`.env` 读取。浏览器不能提交或改写 API 地址、模型密钥；配置接口不返回密钥。
  `OPENAI_BASE_URL` 只允许 HTTPS，默认 `https://api.openai.com/v1`；兼容服务必须支持
  multipart `image[]`、`background=transparent`、PNG、`b64_json` 和同等 Image Edits 参数。
- 默认模型为 `gpt-image-1.5`，设置 `input_fidelity=high`；改用 GPT Image 2 系列时不发送该参数。
  模型是否可用取决于当前账号权限。没有密钥会明确阻止照片生成，不会把原照片加字当成 AI 结果。
- 每次照片任务发出 **一次图集编辑请求**，API 可能收费；费用以所选服务的账单为准，
  不承诺 ChatGPT 订阅覆盖 API。默认不自动重试付费请求，超时/清除时已发出的请求仍可能产生费用。
  示例、图集导入、合成和下载不调用图像模型。
- 工作台以随机 HttpOnly、SameSite 会话 cookie 隔离任务。新浏览器、无痕窗口或丢失 cookie 后无法找回旧文件。
  生成的图集和成品存储于 `.runtime` 下的会话临时目录，默认 60 分钟后清除（最多额外 30 秒），
  可手动立即清除，正常关闭服务器时清理。异常退出可能留下临时文件，应在确认没有运行中的实例后由管理员清理。
  不记录上传内容或密钥；外部服务商的数据保留规则另计。
- 保持 `STICKER_DATA_DIR` 在静态资源目录外，保持单进程启动；会话信息和任务状态在内存中。
  无账号体系、计费/支付、多实例持久队列或自动重试，不应直接作为公共商用生成服务。

接口核对：[OpenAI Image Edits](https://developers.openai.com/api/reference/resources/images/methods/edit)。

## 验证

```bash
# 原项目测试
python3 -m unittest discover -s ../tests -v
# 包装层：真实调用原始导出器，另以 MockTransport 检查模型请求，不调用付费接口
python3 -m unittest discover -s tests -v
# 已安装 Playwright + Chromium 时执行浏览器检查；先运行服务
python3 scripts/check_ui.py --url http://127.0.0.1:8000
```

UI 检查覆盖桌面/手机布局、示例图集检查、原项目导出和下载，以及无密钥时的真实状态。
详情见 [docs/VALIDATION.md](docs/VALIDATION.md)。

## 许可

原项目 MIT 许可原样保留于仓库根目录 [LICENSE](../LICENSE)，版权归 WoYun520。
网页使用的示例来自该仓库 `examples/whale-maid/`，素材说明见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
捆绑 Noto Sans CJK 简体中文字体按 SIL Open Font License 分发，许可见
`licenses/NotoSansCJK-OFL.txt`。代码许可不自动覆盖用户上传的肖像、商标或其他第三方素材权益。
