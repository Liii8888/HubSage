# 🤖 HubSage

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](http://makeapullrequest.com)

[English](#english) | [中文](#chinese)

---

<a name="chinese"></a>
## 📖 简介 (Introduction)

HubSage 是一个通用的专业开源项目维护者技能（Agent Skill），适用于各类具备 Shell 执行能力的 AI Agent。它能够帮助你以专业的开源作者标准（如 Gitmoji 规范、中英双语文档、生成徽章和 Release Notes）自动化管理仓库、编写文档并执行版本发布。

### 🏗 架构 / 工作流 (Architecture)

```mermaid
graph TD
    A[用户输入指令] --> B{触发 HubSage}
    B -->|文档化| C[生成双语 README & 徽章]
    B -->|代码提交| D[Gitmoji + Conventional Commits]
    B -->|版本发布| E[自动收集日志 & 生成 Release Notes]
    E --> F[gh release create]
    C --> G[标准化开源仓库]
    D --> G
    F --> G
```

### 🚀 快速开始 (Quick Start)

**安装技能：**
在终端中唤醒你的 AI Agent 并输入以下指令，让其自动下载并配置此技能：

```text
下载这个 Skills：https://github.com/Liii8888/HubSage
```

**使用技能：**
配置完成后，你可以向 Agent 发送如下指令来管理你的项目：

```text
使用 HubSage 规范化当前开源项目，并生成双语 README
```

### 🤝 参与贡献

欢迎提交 PR！请查阅我们的 [贡献指南 (CONTRIBUTING.md)](CONTRIBUTING.md) 了解更多分支规范与提交流程。

---

<a name="english"></a>
## 📖 Introduction

HubSage is a professional open-source project maintainer skill (Agent Skill) designed for AI Agents with Shell execution capabilities. It helps you automate repository management, write documentation, and execute releases using professional open-source standards (such as Gitmoji, bilingual documentation, badges, and release notes).

### 🏗 Architecture / Workflow

```mermaid
graph TD
    A[User Input] --> B{Trigger HubSage}
    B -->|Documentation| C[Generate Bilingual README & Badges]
    B -->|Commits| D[Gitmoji + Conventional Commits]
    B -->|Release| E[Collect Logs & Gen Release Notes]
    E --> F[gh release create]
    C --> G[Standardized Open Source Repo]
    D --> G
    F --> G
```

### 🚀 Quick Start

**Installation:**
Launch your AI Agent in the terminal and input the following prompt to let it download and configure the skill automatically:

```text
Download this skill: https://github.com/Liii8888/HubSage
```

**Usage:**
Once configured, you can manage your project by sending a prompt like this:

```text
Use HubSage to standardize the current open-source project and generate a bilingual README
```

### 🤝 Contributing

PRs are welcome! Please check out our [Contributing Guidelines (CONTRIBUTING.md)](CONTRIBUTING.md) for more details on branching and commit workflows.