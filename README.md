# Private GitHub Pro Review

把本地 Git 仓库备份到长期使用的 GitHub 私有仓库，再交给 ChatGPT Pro 或 Pro + Deep Research 审查，保存来源、状态与回答证据。Skill ID 为 `private-github-pro-review`，仅接受显式调用。

This Codex Skill maintains a persistent private GitHub backup and records the source and result of a bounded ChatGPT review. The existing HubSage repository is its public distribution home.

## 安装与调用

需要 Python 3.10+、Git、GitHub CLI，以及具备现有脚本所需 POSIX 文件锁能力的环境。本轮验证平台为 macOS。网页步骤需要 ChatGPT Pro、获准访问目标私有仓库的 GitHub App，以及受支持的 Codex 浏览器工具。

从你已审查的完整提交 SHA 导出到一个尚不存在的目录：

```bash
(
  PGPR_REVIEWED_SHA=FULL_REVIEWED_COMMIT_SHA &&
  git clone --no-checkout https://github.com/Liii8888/HubSage.git private-github-pro-review &&
  cd private-github-pro-review &&
  git checkout --detach "$PGPR_REVIEWED_SHA" &&
  python3 scripts/export_skill.py export \
    --ref "$PGPR_REVIEWED_SHA" \
    --output "$HOME/.agents/skills/private-github-pro-review"
)
```

先切换到已审核的完整 SHA，再运行该提交中的导出脚本；执行代码与安装内容使用同一个审核版本。命令链中任一步失败就停止，避免继续执行旧目录中的脚本。导出工具不会覆盖已有目录或替换现有 Skill Vault 入口。通过 Vault 使用时，由维护者在审核后更新固定分发快照。

```text
使用 $private-github-pro-review，把当前仓库备份到长期私有 GitHub 仓库，并交给 GPT Pro + Deep Research 审查。
```

CLI 入口保持为 `scripts/review_repo.py`。`publish --mode review` 使用 Pro + Deep Research，`--mode pro` 使用 Pro；完整参数可通过 `--help` 查看。执行约束和浏览器步骤见 [SKILL.md](SKILL.md) 与 [browser protocol](references/browser-protocol.md)。

### 首次使用的小提示

以下供首次配置或访问异常时按需参考，不增加每次运行的强制预检。

- **ChatGPT 的 GitHub 连接**：确认网页版已连接 GitHub App／连接器，并能访问用于审查的私有备份库。本机 `gh` 登录和 ChatGPT 的连接授权需要分别配置。插件安装与连接方式见 [OpenAI 官方说明](https://learn.chatgpt.com/docs/plugins)。
- **仓库权限范围**：如果经常新建备份库，并愿意授权所在账号或组织的全部仓库，建议在对应 GitHub App 的 `Repository access` 中选择 `All repositories`，省去逐库补授权。也可用 `Only select repositories`，但新建备份库后要把它加入授权列表。这里的全部授权仅适用于该 App 安装所在的账号或组织；它不会把私有库改成公开库。设置入口见 [GitHub 官方说明](https://docs.github.com/en/apps/using-github-apps/reviewing-and-modifying-installed-github-apps)。
- **Pro 模型**：使用前看看当前账号的网页模型选择器是否提供 `Pro`，发送前再确认当前对话已选中 `Pro`；具体模型名称以页面为准，`high`／`xhigh` 推理强度不能替代 Pro。`review` 模式还会使用 Deep Research。
- **浏览器工具**：准备能操作已登录 ChatGPT 会话的受支持浏览器工具。例如使用 Chrome 时，按桌面端 `Computer Use` 设置提示安装配套插件和浏览器扩展，并连接实际登录的浏览器配置文件；本 Skill 不限定插件名称。参见 [浏览器扩展配置](https://learn.chatgpt.com/docs/chrome-extension#set-up-the-chrome-extension)。

## 行为与数据

| 内容 | 去向与用途 |
| --- | --- |
| 指定仓库的本地分支、tag、可达历史，以及明确批准的未提交快照 | 当前 GitHub CLI 账号下、通过身份与私有性检查的长期备份仓库。历史中已删除的文件也可能包含在备份内。 |
| 用户的原始 Prompt 与选定审查来源 | 用户已登录的 `chatgpt.com` 对话；通过用户授权的 GitHub App 选择目标私有库作为审查来源。 |
| 项目映射、Prompt 副本、来源证据和收集到的回答 | 本机配置的状态目录；回答提取先写入用户专用临时目录。 |
| 登录与仓库访问权限 | 使用既有 GitHub CLI / Git 凭据机制和受支持的浏览器会话；不要求向 Agent 提供原始 token，不记录 token，不复制浏览器 cookie 或 profile。 |

`Liii8888/HubSage` 是这个 Skill 的公开源码分发仓库，不是用户项目的上传目标。实现没有维护者自建的数据接收地址或遥测上报。向 GitHub 和 ChatGPT 提交数据是需要用户授权的核心功能；仓库权限仍由用户控制。

Git 上传前会解析实际读取和上传地址，拒绝指向其他主机、其他仓库或多个目标的配置。指向同一 GitHub 仓库的标准 HTTPS／SSH 转换受支持；检查只在临时仓库内配置 remote，不修改用户的全局 Git 配置。

- 保存分支、tag 和可达历史；未提交快照需明确授权，源仓库保持原状。
- 固定 Prompt 字节、仓库与提交，验证发布后来源漂移，并限制每个本地仓库同时一个活动审查。
- 分别记录 GitHub CLI 登录、GitHub App 授权、页面来源绑定和最终回答证据。
- 上传和使用 ChatGPT 需要授权；不自动登录、强推或重写历史。凭据扫描会拦截已识别的路径和内容，逐路径覆盖需明确授权；有限识别规则无法发现所有种类的秘密。
- 浏览器观察证明本地记录的页面状态，不证明 ChatGPT 内部实际检索了哪些内容。当前限制见 [KNOWN-ISSUES.md](KNOWN-ISSUES.md)。

公开版默认使用 `$XDG_STATE_HOME/private-github-pro-review`，未设置时使用 `~/.local/state/private-github-pro-review`。`PRIVATE_GITHUB_PRO_REVIEW_HOME` 可显式覆盖；已有 `--state-root` 参数优先。使用本机适配的 Vault 快照时，其固定本机默认值优先于 XDG 默认值，显式环境变量和 CLI 参数仍可覆盖。

私有库映射、Prompt、回答和运行记录保存在状态目录，既不进入源码，也不进入公开安装包。`RUN_VERSION = 3` 是运行记录格式；旧记录继续按既有兼容规则只读展示。

## 固定提交分发

```bash
python3 scripts/export_skill.py export --ref FULL_REVIEWED_COMMIT_SHA --output /tmp/review-snapshot
python3 scripts/export_skill.py verify --ref FULL_REVIEWED_COMMIT_SHA --directory /tmp/review-snapshot
```

导出只读取指定 Git 提交，不读取未提交内容；`DISTRIBUTION.json` 和 `UPSTREAM.md` 记录来源和文件校验值。校验针对该提交，新源码 HEAD 前进不会改变已固定的快照。

本机分发可以额外指定 `--local-state-root /absolute/local/state`；验证时必须独立提供相同参数。唯一允许的源码差异是脚本的默认状态目录赋值。这种包含本机配置的快照只用于本机；公开分发省略该参数。

## 验证与发布

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_*.py'
```

候选提交及其公开安装包须通过测试和内容检查，再交给维护者复审。用户批准后才推送、打 tag、发布 Release 和升级正式 Vault 快照。Release Notes 取自 [CHANGELOG.md](CHANGELOG.md)，不重复维护另一份版本说明。

`v2.0.0` 接续原 HubSage 版本线，标明用途转为 Pro review；旧 `v1.x` 的 tag、Release 和 Git 历史继续保留。[现有发布历史](https://github.com/Liii8888/HubSage/releases)。

## License

[MIT](LICENSE) — Copyright (c) 2026 Liii8888.
