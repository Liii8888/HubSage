# 📝 HubSage 待办事项与更新规划 (TODO & Roadmap)

## v1.1.0 核心目标：规范化与易用性提升

### 1. 严格规范 Gitmoji 语义辞典 (Gitmoji Dictionary)
**问题描述：** 目前的 Gitmoji 使用可能依赖 AI 的自由发挥，容易导致同一个操作使用了不同的表情包（例如修复有时用 `🐛`，有时用 `🚑`）。
**解决方案：** 
- 在 `SKILL.md` 中强制内嵌一份精简且无歧义的 **Gitmoji 字典**。
- 规定：
  - `✨ feat:` 仅用于新功能。
  - `🐛 fix:` 仅用于修复常规 Bug。
  - `🚑 hotfix:` 紧急热修复。
  - `♻️ refactor:` 代码重构（无功能变化）。
  - `📝 docs:` 仅修改文档。
  - `🎨 style:` 格式化代码（空格、分号等，不影响逻辑）。
  - `🚀 release:` 发布新版本或 Tag。
  - `👷 build:` 构建系统或 CI/CD 变更。
- **目标：** 限制自由度，消除混淆。

### 2. 提升“开箱即用”体验 (Zero-Config / Plug & Play)
**问题描述：** HubSage 强依赖 `gh` CLI 工具。如果其他用户安装了 HubSage 但没有安装配置 `gh`，会导致流程中断并报错。
**解决方案：**
- 在 SOP 中增加 **环境自检 (Pre-flight Check)** 步骤。
- 如果检测到未安装 `gh` 或未授权（`gh auth status` 失败），则不能直接报错，而是要优雅地触发预设的“保姆级安装与授权引导流程”。
- 对于 macOS 用户，甚至可以通过解释 Sandbox 机制（macOS Seatbelt）指导他们在独立终端手动运行 `brew install gh`。
- **目标：** 让小白用户也能无痛享受专业的开源提交流程。

---

## 📌 未来规划 (Backlog)
- [ ] 支持多分支策略管理（例如自动切出 `release/vX.X` 分支）。
- [ ] 增加检查并自动修复代码根目录缺少 `.gitignore` 的能力。