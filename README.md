# HubSage

HubSage 目前用于发布 `private-github-pro-review` Codex Skill。

它会把本地 Git 仓库备份到一个长期使用的 GitHub 私有仓库，再将指定版本交给 ChatGPT Pro 或 Deep Research 审查，并保存本次审查的来源、状态和结果证据。

本仓库只包含可公开分发的版本，不包含本机绝对路径、真实私有仓库名称、运行记录或凭据。

## 功能

- 保存本地分支、标签和可达 Git 历史。
- 使用同一个私有 GitHub 仓库持续备份项目，不为每次审查新建临时仓库。
- 支持经过用户确认的未提交工作树快照。
- 支持 GPT Pro 和 GPT Pro + Deep Research 两种审查模式。
- 冻结 Prompt 的字节数和 SHA-256，防止提交前后发生变化。
- 绑定仓库、默认分支和 Commit，并在发送前检查远端漂移。
- 同一个本地仓库同一时间只允许一个活动审查任务。
- 记录浏览器标签页、会话地址、完成状态、回答文件和 SHA-256。
- 区分 GitHub CLI 登录与 ChatGPT GitHub App 授权。
- 遇到凭据文件、超大对象、Git LFS 指针、未知页面状态或访问警告时停止。

## 基本流程

1. 检查本地 Git 仓库和 GitHub CLI 登录状态。
2. 创建或复用该项目对应的 GitHub 私有备份仓库。
3. 上传分支、标签、历史，以及明确获准的工作树快照。
4. 在新的 ChatGPT 会话中绑定指定仓库版本并发送原始 Prompt。
5. 等待生成结束，收集最终回答并记录校验信息。

`scripts/review_repo.py` 负责 GitHub 发布和证据状态管理。浏览器操作由受支持的 Codex 浏览器工具完成，具体约束见 [`references/browser-protocol.md`](references/browser-protocol.md)。

## 环境要求

- Python 3.10 或更高版本
- Git
- GitHub CLI (`gh`)
- 可以创建私有仓库的 GitHub 账号
- ChatGPT Pro
- 已授权访问目标私有仓库的 ChatGPT GitHub App
- 受支持的 Codex 浏览器工具

## 安装

在本仓库的本地检出目录中执行：

```bash
mkdir -p "$HOME/.agents/skills/private-github-pro-review"
cp -R SKILL.md KNOWN-ISSUES.md agents references scripts \
  "$HOME/.agents/skills/private-github-pro-review/"
```

安装后的 Skill ID 为：

```text
private-github-pro-review
```

该 Skill 只接受显式调用。

## 使用

可以直接要求 Codex 使用 Skill：

```text
使用 $private-github-pro-review，把当前仓库备份到长期私有 GitHub 仓库，并交给 GPT Pro + Deep Research 审查。
```

也可以单独运行发布脚本：

```bash
python3 scripts/review_repo.py publish \
  --repo /absolute/path/to/repository \
  --mode review \
  --binding source-chip \
  --prompt-file /absolute/path/to/prompt.txt
```

使用 `--mode pro` 时只使用 GPT Pro，不启用 Deep Research。Prompt 会按原始字节提交，不会自动扩写或改写。

## 状态目录

默认状态目录为：

```text
$XDG_STATE_HOME/private-github-pro-review
```

未设置 `XDG_STATE_HOME` 时使用：

```text
~/.local/state/private-github-pro-review
```

也可以通过 `PRIVATE_GITHUB_PRO_REVIEW_HOME` 指定其他目录。

## 安全边界

- 上传仓库和使用 ChatGPT 前必须得到用户明确许可。
- 目标 GitHub 仓库必须保持私有。
- 不执行强制推送或 Git 历史重写。
- 不自动上传高风险凭据文件。
- 不读取、复制或保存 GitHub Token、密码、Cookie、二次验证码或恢复码。
- 不通过高频页面读取判断生成进度。
- 浏览器证据只能说明本地观察到了什么，不能证明 ChatGPT 内部实际读取了哪些内容。

完整执行规则见 [`SKILL.md`](SKILL.md)，已知限制见 [`KNOWN-ISSUES.md`](KNOWN-ISSUES.md)。

## 测试

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
```

## License

MIT
