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

流程是：首次为项目创建私有备份库 → 上传本次版本 → 取得链接并与原审查要求一起粘贴到网页 ChatGPT → 选择 Pro → 等待并保存回答。后续修改、复审继续更新同一个库，审查后保留仓库。

CLI 入口是 `scripts/review_repo.py`。先 `publish --repo /absolute/project/path`，成功后用 `prepare-review --run-dir ... --mode pro|review --prompt-file ...` 固定消息；默认采用粘贴库链接的方式。原审查要求保存为 `request.txt`，发送的完整消息保存为 `prompt.txt`。旧版一次提供 mode 和 Prompt 的 `publish` 命令继续兼容。

`pro` 使用 Pro，`review` 使用 Pro + Deep Research；根据当次请求选择，不统一偏好。有未提交修改时，按用户意图选择 `--include-working-tree` 或 `--committed-only`；未说明范围时才询问。完整参数见 `--help`，执行步骤见 [SKILL.md](SKILL.md) 与 [browser protocol](references/browser-protocol.md)。

### 首次使用的小提示

以下供首次配置或访问异常时按需参考，不增加每次运行的强制预检。

- **ChatGPT 的 GitHub 连接**：确认网页版已连接 GitHub App／连接器，并能访问用于审查的私有备份库。本机 `gh` 登录和 ChatGPT 的连接授权需要分别配置。插件安装与连接方式见 [OpenAI 官方说明](https://learn.chatgpt.com/docs/plugins)。
- **仓库权限范围**：建议首次连接时，在你接受该账号或组织全部仓库授权范围的前提下，在对应 GitHub App 的 `Repository access` 中选择 `All repositories`，一次配置后，新建项目的备份库也在授权范围内，无需每次补授权。也可用 `Only select repositories`，但新建备份库后要把它加入授权列表。这里的全部授权仅适用于该 App 安装所在的账号或组织；它不会把私有库改成公开库。设置入口见 [GitHub 官方说明](https://docs.github.com/en/apps/using-github-apps/reviewing-and-modifying-installed-github-apps)。
- **Pro 模型**：使用前看看当前账号的网页模型选择器是否提供 `Pro`，发送前再确认当前对话已选中 `Pro`；具体模型名称以页面为准，`high`／`xhigh` 推理强度不能替代 Pro。`review` 模式还会使用 Deep Research。
- **浏览器工具**：准备能操作已登录 ChatGPT 会话的受支持浏览器工具。例如使用 Chrome 时，按桌面端 `Computer Use` 设置提示安装配套插件和浏览器扩展，并连接实际登录的浏览器配置文件；本 Skill 不限定插件名称。参见 [浏览器扩展配置](https://learn.chatgpt.com/docs/chrome-extension#set-up-the-chrome-extension)。

## 安全声明

使用本 Skill 需显式授权备份和网页审查。它把选定项目备份到用户自己的 GitHub 私有仓库，再向用户已登录的 ChatGPT 提交审查要求和仓库链接。备份包含本地分支、tag 与可达历史；历史中已删除的文件也可能上传，未提交内容按用户选择纳入。源码分发仓库 `Liii8888/HubSage` 不接收用户项目；本 Skill 没有维护者自建的数据接收端或遥测上报。

认证使用 Git／GitHub CLI 的既有机制及受支持的浏览器会话；不要求把原始 token 交给 Agent，也不复制浏览器 cookie 或 profile。仓库授权由用户控制：`All repositories` 是可选的便利配置，会扩大该 App 可访问的仓库范围；只授权目标仓库也能使用，本 Skill 不会自行扩大授权。

上传前核对目标仓库身份、私有状态和实际 Git 地址，并扫描已识别的敏感路径与凭据模式；回答临时文件按用户专用权限创建。扫描不是完整的秘密检测：未知凭据、业务机密，以及 commit/tag 消息等元数据不在完整检测保障内。私有上传仍会让数据进入 GitHub／ChatGPT，使用者应确认项目及历史适合交给这些服务。网页来源记录也不能证明模型内部实际读取了哪些内容；详见 [行为与数据](#行为与数据) 和 [当前限制](KNOWN-ISSUES.md)。

## 行为与数据

| 内容 | 去向与用途 |
| --- | --- |
| 指定仓库的本地分支、tag、可达历史，以及明确批准的未提交快照 | 当前 GitHub CLI 账号下、通过身份与私有性检查的长期备份仓库。历史中已删除的文件也可能包含在备份内。 |
| 用户的原始审查要求、建库上传后取得的链接或选定来源 | 用户已登录的 `chatgpt.com` 对话；通过用户已授权的 GitHub 连接访问链接指向的私有库；也支持用户选择精确来源 chip。 |
| 项目映射、Prompt 副本、来源证据和收集到的回答 | 本机配置的状态目录；回答提取先写入用户专用临时目录。 |
| 登录与仓库访问权限 | 使用既有 GitHub CLI / Git 凭据机制和受支持的浏览器会话；不要求向 Agent 提供原始 token，不记录 token，不复制浏览器 cookie 或 profile。 |

Git 上传前会解析实际读取和上传地址，拒绝指向其他主机、其他仓库或多个目标的配置。指向同一 GitHub 仓库的标准 HTTPS／SSH 转换受支持；检查只在临时仓库内配置 remote，不修改用户的全局 Git 配置。

- 每个项目一个私有备份库，保存分支、tag 和可达历史；未提交快照按用户选择纳入，忽略文件不上传，源仓库保持原状。
- 固定原始审查要求和完整消息的字节、仓库与提交；上传后再组合链接。每个本地项目同时一个活动审查，防止下一次上传改变尚在审查的版本。
- 分别记录 GitHub CLI 登录、GitHub App 授权、页面来源绑定和最终回答证据。
- 上传和使用 ChatGPT 需要授权；不自动登录、强推或重写历史。凭据扫描会拦截已识别的路径和内容，逐路径覆盖需明确授权；有限识别规则无法发现所有种类的秘密。
- 浏览器观察证明本地记录的页面状态，不证明 ChatGPT 内部实际检索了哪些内容。当前限制见 [KNOWN-ISSUES.md](KNOWN-ISSUES.md)。

公开版默认使用 `$XDG_STATE_HOME/private-github-pro-review`，未设置时使用 `~/.local/state/private-github-pro-review`。`PRIVATE_GITHUB_PRO_REVIEW_HOME` 可显式覆盖；已有 `--state-root` 参数优先。使用本机适配的 Vault 快照时，其固定本机默认值优先于 XDG 默认值，显式环境变量和 CLI 参数仍可覆盖。

中断后再次调用上传入口会返回已有任务和下一步，不会重复上传或发送。网页已经完成时可继续核对并收集；放弃某轮时，先确认网页审查结束或取消，再记录 `end` 解除占用。单纯超时、关闭标签或出现警告不会释放仍在审查的版本，结束也不会删除备份库。

项目映射按本地仓库的实际路径保存。改名、搬家、切换 GitHub 账号或换状态目录时，需要先核对原映射，避免把同一项目意外分成两个备份。不同工作树使用同一备份时也需统一运行入口；当前不会跨机器协调上传。

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
