# Private GitHub Pro Review

[English](README.md) · [安装](#安装到-codex) · [安全与数据](#安全与数据) · [版本发布](https://github.com/Liii8888/private-github-pro-review/releases) · [MIT](LICENSE)

让 Codex 把本地项目上传到**你自己的 GitHub 私有库**，打开**网页版 ChatGPT**，
选择 **Pro**，提交仓库链接和审查要求，最后保存回答。每个项目保留一个备份库，后续复审继续更新它。

## 让 Agent 帮你安装

> 帮我把 https://github.com/Liii8888/private-github-pro-review 安装为 Codex Skill。
> 先读 README 和安全声明，再按下方说明安装已审核的 v2.0.2 提交。
> 保留已有安装和审查记录，告诉我还需要哪些配置；安装阶段不用上传项目或发起审查。

## 安装到 Codex

需要 Python 3.10+、Git、GitHub CLI（`gh`），以及具备 shell 和受支持浏览器连接的本地 Codex。
当前验证平台是 macOS，脚本使用 POSIX 文件锁。网页审查还需要账号中可用的 Pro，
以及能访问私有备份库的 ChatGPT GitHub 连接。

阅读源码后，在没有同名 `private-github-pro-review` 文件夹的位置执行。以下安装 **v2.0.2**：

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

完整 SHA 同时固定执行的代码和安装内容。任一步失败都会停止，已有目标目录会保留。
只想让当前项目使用时，把输出目录改为该项目下的 `.agents/skills/private-github-pro-review`。
安装后新开一个 Codex 任务，显式调用这个 Skill。

安装内容只有 Skill 指令、浏览器协议、运行脚本、Codex 元数据、许可证和来源校验清单。
项目说明与维护测试不参与运行。导出或核验某个版本时，使用该版本提交中的 `scripts/export_skill.py`。

## 怎么使用

> 用 $private-github-pro-review 把这个项目交给网页版 GPT Pro 审查。
> 包含我当前未提交的修改，重点找正确性问题。

> 用 $private-github-pro-review，通过 Pro + Deep Research 审查已提交版本，重点看架构。

> 继续上次中断的 private GitHub Pro review，收集审查结果。

流程是：**上传 → 选择 Pro → 粘贴链接和审查要求 → 等待 → 保存回答**。
按当次需求选择 Deep Research 和代码范围，审查要求原文保留，后续复审更新同一个私有备份库。
流程见 [SKILL.md](SKILL.md)，直接操作 CLI 时可查看 `python3 scripts/review_repo.py --help`。

### 首次使用的小提示

供首次配置或遇到访问问题时参考，不增加每次运行的强制检查：

- **GitHub 连接**：在 ChatGPT 中连接 GitHub，并授权访问备份库；这与本机 `gh` 登录是两回事。
  参见 [连接说明](https://learn.chatgpt.com/docs/plugins)。
- **仓库权限**：经常使用时，建议在接受对应账号或组织全部仓库访问范围的前提下选择
  **All repositories**，省去逐库授权。也可以使用 **Only select repositories**。
  两者都不会把私有库变成公开库。参见 [GitHub App 设置](https://docs.github.com/en/apps/using-github-apps/reviewing-and-modifying-installed-github-apps)。
- **Pro 选择**：确认网页中可用并在发送前选中。名称以实际页面为准，`high`、`xhigh` 推理强度不等于 Pro。
- **浏览器连接**：使用能操作已登录 ChatGPT 会话的受支持工具，按其说明配置浏览器插件或扩展；
  不要求固定名称的插件。参见 [浏览器配置](https://learn.chatgpt.com/docs/chrome-extension#set-up-the-chrome-extension)。

## 安全与数据

只有用户显式请求并授权上传与审查时才运行。
**没有维护者自建的数据接收端，也没有遥测上报**；这个公开仓库不接收用户项目。

| 数据 | 保存或发送到哪里 |
| --- | --- |
| 分支、tag、可达历史，以及当次选择纳入的未提交修改 | 经过核对的、你自己的 GitHub 私有备份库 |
| 链接、审查要求，以及通过 GitHub 连接读取的代码 | 你已登录的 ChatGPT 会话 |
| 项目映射、原文副本、证据和最终回答 | 本机状态目录 |

认证沿用 Git／GitHub CLI 的既有凭据和受支持的浏览器会话，
不索要原始 token、不复制 cookie 或 profile，也不自行扩大仓库授权。
上传目标检查、敏感路径与凭据扫描、回答文件的私有权限保护仍会自动执行。
扫描无法识别所有秘密；可达历史可能包含已删除的文件，commit／tag 消息也不在完整扫描范围内。
使用者需要选择适合交给 GitHub 和 ChatGPT 的项目及历史。

网页来源记录不能证明模型实际读了哪些代码，审查意见仍需结合源码核实。
界面变化或索引延迟可能需要暂停后续跑；具体等待与恢复规则见 [浏览器协议](references/browser-protocol.md)。

## 本地记录与恢复

状态目录默认是 `$XDG_STATE_HOME/private-github-pro-review`；没有设置 XDG 时使用
`~/.local/state/private-github-pro-review`。可用 `PRIVATE_GITHUB_PRO_REVIEW_HOME` 覆盖，
显式 `--state-root` 参数优先。运行资料不进入源码和发布包。

中断后继续原任务和对话。放弃一轮审查时，先确认网页已完成或取消，再记录 `end`；
仅超时或关闭标签页不够。结束或归档任务会保留备份库和证据。
移动项目、改用其他 worktree、状态目录或机器前，先核对原映射；本机锁不会协调不同位置的写入者。
旧记录继续可读，保留原有的验证状态。

[版本沿革](CHANGELOG.md) · 项目原名 HubSage，旧链接、tag 和 Release 继续保留。
