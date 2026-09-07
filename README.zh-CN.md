# Private GitHub Pro Review

[English](README.md) · [安装](#安装到-codex) · [安全与数据](#安全与数据) · [执行流程](SKILL.md) · [版本发布](https://github.com/Liii8888/private-github-pro-review/releases) · [MIT 许可证](LICENSE)

让 Codex 把本地 Git 项目备份到**你自己的 GitHub 私有仓库**，再打开**网页版 ChatGPT**，
选择 **Pro**，提交仓库链接和审查要求，最后保存回答。

这是面向**本地 Codex** 的社区 Skill。每个项目对应一个长期使用的私有备份库：
首次创建，修改后继续更新，后续复审复用。整个流程使用你自己的 GitHub 账号和 ChatGPT 会话。

## 让 Agent 帮你安装

把下面这段话交给 Codex：

> 帮我把 https://github.com/Liii8888/private-github-pro-review 安装为 Codex Skill。
> 先读 README 和安全声明，再按下方说明安装已审核的 v2.0.2 提交。
> 保留已有安装和审查记录，告诉我安装位置，以及还需要哪些 GitHub 或浏览器配置。
> 安装阶段不用上传项目，也不用发起审查。

安装包包含 [Skill 指令](SKILL.md)、Python 脚本、浏览器协议和测试。
安装完整快照后，后续任务可以直接调用 `$private-github-pro-review`，无需记住脚本路径。

## 已有功能

- 首次为项目创建私有备份库，后续审查继续使用同一个库。
- 备份本地分支、tag、可达历史，以及当次选择纳入的未提交修改，保留源工作区原状。
- 上传成功后取得仓库链接，与原始审查要求一起提交；审查要求按原文保留。
- 支持 Pro 和 Pro + Deep Research，每次按需求选择。
- 在本地保存审查提交、对话链接、进度和最终回答。
- 中断后继续原任务，防止下一次上传改变仍在审查的版本。

## 安装到 Codex

需要 Python 3.10+、Git、GitHub CLI（`gh`），以及具备 shell 和受支持浏览器工具的 Codex 环境。
当前验证平台是 macOS，脚本使用 POSIX 文件锁。网页审查还需要账号中可用的 Pro，
以及能访问私有备份库的 ChatGPT GitHub 连接。

阅读源码后，在没有同名 `private-github-pro-review` 文件夹的位置执行。
下面的命令通过完整提交 SHA 固定安装 **v2.0.2**：

```bash
(
  PGPR_REVIEWED_SHA=0d9a4b389011de3fa22bfb9384ed0619cdd2a282 &&
  git clone --no-checkout https://github.com/Liii8888/private-github-pro-review.git private-github-pro-review &&
  cd private-github-pro-review &&
  git checkout --detach "$PGPR_REVIEWED_SHA" &&
  python3 scripts/export_skill.py export \
    --ref "$PGPR_REVIEWED_SHA" \
    --output "$HOME/.agents/skills/private-github-pro-review"
)
```

安装程序**先切换到审核提交，再执行其中的代码**，导出内容也来自同一提交。
任一步失败都会停止；已有目标目录会保留。只想让当前项目使用时，可把输出目录改为
该项目下的 `.agents/skills/private-github-pro-review`。如果安装由 Skill Vault 管理，
通过 Vault 更新已审核快照。位置说明见 [Codex 官方 Skill 文档](https://developers.openai.com/codex/skills#where-to-save-skills)。

安装后新开一个 Codex 任务，显式调用这个 Skill；如果还未显示，重启 Codex 并检查安装的 `SKILL.md` 路径。

## 怎么使用

例如：

> 用 $private-github-pro-review 把这个项目备份到私有 GitHub 仓库，再交给网页版 GPT Pro 审查。
> 包含我当前未提交的修改，重点找正确性问题和遗漏的测试。

> 用 $private-github-pro-review，通过 Pro + Deep Research 审查已提交版本，重点看架构和剩余安全问题。

> 继续上次中断的 private GitHub Pro review，收集审查结果。

流程是：**上传 → 选择 Pro → 粘贴链接和审查要求 → 等待 → 保存回答**。
后续修改和复审继续更新同一个私有备份库。

按当次需求选择模式和代码范围，不统一预设是否使用 Deep Research 或纳入未提交修改。
直接操作 CLI 时，`pro` 表示 Pro，`review` 表示 Pro + Deep Research；
范围参数为 `--include-working-tree` 和 `--committed-only`。
上传与准备消息的步骤见 [SKILL.md](SKILL.md)，完整命令见 `scripts/review_repo.py --help`；
网页提交和回答收集遵循 [浏览器协议](references/browser-protocol.md)。

### 首次使用的小提示

以下供首次配置或遇到访问问题时参考，不增加每次运行的强制检查：

- **GitHub 连接**：在 ChatGPT 中连接 GitHub，并授予它访问备份库的权限。
  本机 `gh` 登录与 ChatGPT 的 GitHub 授权是两回事。参见 [OpenAI 插件说明](https://learn.chatgpt.com/docs/plugins)。
- **仓库权限**：经常使用时，建议在接受对应账号或组织全部仓库授权范围的前提下，选择
  **All repositories**，这样新建备份库不用逐个补授权。也可以使用 **Only select repositories**，
  每次新增备份库后将其加入列表。这不会把私有库变成公开库。参见 [GitHub App 权限设置](https://docs.github.com/en/apps/using-github-apps/reviewing-and-modifying-installed-github-apps)。
- **Pro 选择**：看看网页模型选择器里是否有 Pro，发送前确认已选中。
  具体名称以账号实际页面为准，`high`、`xhigh` 推理强度不能替代 Pro。
- **浏览器连接**：使用能操作已登录 ChatGPT 会话的受支持工具。以 Chrome 为例，
  按桌面端 **Settings → Computer Use** 的提示，在正确的浏览器配置文件中安装配套插件与扩展。
  本 Skill 不要求固定名称的插件。参见 [浏览器配置说明](https://learn.chatgpt.com/docs/chrome-extension#set-up-the-chrome-extension)。

## 安全与数据

本 Skill 只在用户显式请求并授权上传与审查时运行。
**没有维护者自建的数据接收端，也没有遥测上报**；这个公开源码仓库不接收用户项目。

| 数据 | 保存或发送到哪里 |
| --- | --- |
| 本地分支、tag、可达历史，以及当次选择纳入的未提交修改 | 经过核对的、你自己的 GitHub 私有备份库 |
| 仓库链接、审查要求，以及通过已授权 GitHub 连接读取的代码 | 你已登录的 ChatGPT 会话 |
| 项目映射、原文副本、来源证据、最终回答 | 本机状态目录 |

认证沿用 Git／GitHub CLI 的既有凭据和受支持的浏览器会话，
不要求提供原始 token，不复制浏览器 cookie 或 profile。
仓库授权范围由用户控制，Skill 不会自行扩大授权。

上传前核对仓库身份、私有状态、管理标记和实际 Git 目标，并扫描已知敏感路径与凭据模式；
回答提取使用当前用户专用的私有目录和文件。这些检查有明确边界：可达历史中可能仍有已删除的文件，
扫描无法识别所有秘密或业务机密，commit／tag 消息也不在完整扫描范围内。
使用者需要选择适合交给 GitHub 和 ChatGPT 的项目及历史。

粘贴了链接或记录了来源选择，不代表能够证明模型实际读了哪些代码。
审查意见仍需结合源码核实；浏览器、来源证据和恢复方面的其他限制见 [KNOWN-ISSUES.md](KNOWN-ISSUES.md)。

## 本地记录与中断恢复

状态目录默认使用 `$XDG_STATE_HOME/private-github-pro-review`；没有设置 XDG 时，
使用 `~/.local/state/private-github-pro-review`。
`PRIVATE_GITHUB_PRO_REVIEW_HOME` 可覆盖默认值，显式 `--state-root` 参数优先。
本机适配的 Vault 快照可以保留原默认位置，仍接受上述显式覆盖。
运行资料保存在源码与公开安装包之外。

中断后继续保存的任务和对话。放弃一轮审查时，先确认网页已经完成或取消，再记录 `end`；
仅超时或关闭标签页不会解除活动版本的占用。结束或归档任务不会删除私有备份库和本地证据。

项目身份按同一个状态目录下的本地仓库实际路径确定。
移动文件夹、切换账号，或改用其他 worktree、机器之前，需要核对原映射；本机锁不会跨机器协调。

## 开发与验证

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_*.py'
```

测试使用临时仓库、假数据和模拟服务，覆盖上传安全、快照、来源绑定、恢复、回答收集与固定版本安装，
不会进行真实私有项目上传或网页版 ChatGPT 审查。

`scripts/export_skill.py` 从完整提交 SHA 导出和校验快照，
`DISTRIBUTION.json` 与 `UPSTREAM.md` 记录来源和校验值；开发源码前进不会自动升级已安装版本。
`RUN_VERSION = 3` 是运行记录格式，与发布版本号分开；旧记录继续可读，并保留未验证标记。

版本沿革见 [CHANGELOG.md](CHANGELOG.md)。本仓库由 HubSage 原地改名，旧仓库链接继续跳转，
原有 v1.x tag、Release 与历史保留。项目采用 [MIT 许可证](LICENSE)。
