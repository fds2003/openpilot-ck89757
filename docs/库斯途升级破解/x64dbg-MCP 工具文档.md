# x64dbg-MCP Server 工具文档

> 安装日期：2026-10-11
> 项目地址：https://github.com/duty1g/x64dbg-mcp-server
> 版本：v1.5
> 用途：把 x64dbg 调试器的完整功能通过 MCP 暴露给 AI Agent

---

## 1. 简介

x64dbg-MCP Server 是一个 x64dbg 原生 MCP 插件（Zig 编写，零依赖），让 AI Agent 可以程序化控制调试器：

- **84 个 MCP 工具**：断点、单步、内存读写、寄存器、反汇编、符号、PE 分析、Dump 等
- **22 个事件回调**：调试器事件全覆盖（断点命中、异常、DLL 加载等）
- **零依赖**：纯原生插件，单二进制输出，无需 .NET/Python/运行时
- **双架构**：x32 + x64 一套代码
- **双传输**：Streamable HTTP + SSE
- **强制 Bearer 认证**：首次运行自动生成 token，每次请求必须携带

---

## 2. 已完成安装

### 2.1 安装位置

| 组件 | 路径 |
|------|------|
| x64dbg 主程序 | `D:\tools\x64dbg\release\x64\x64dbg.exe` |
| x64dbg-MCP 插件（x64） | `D:\tools\x64dbg\release\x64\plugins\x64dbg-MCP-Server.dp64` |
| x64dbg-MCP 插件（x32） | `D:\tools\x64dbg\release\x32\plugins\x64dbg-MCP-Server.dp32` |
| MCP 配置文件 | `D:\tools\x64dbg\release\x64\mcp_config.json` |

### 2.2 MCP 配置内容

`mcp_config.json`（首次启动 x64dbg 自动生成）：

```json
{
  "IpAddress": "127.0.0.1",
  "Port": 9094,
  "AutoStart": true,
  "AuthToken": "fc8492267d8c010c45d5760f42e05db9"
}
```

### 2.3 默认端口

| 架构 | 端口 |
|------|------|
| x64 | `9094` |
| x32 | `9095` |

### 2.4 Claude Code 注册

已写入 `C:\Users\fds20\.claude.json`：

```json
"x64dbg-mcp": {
  "type": "http",
  "url": "http://127.0.0.1:9094/",
  "headers": {
    "Authorization": "Bearer fc8492267d8c010c45d5760f42e05db9"
  }
}
```

---

## 3. 使用流程

### 3.1 启动顺序

1. 启动 `D:\tools\x64dbg\release\x64\x64dbg.exe`
2. MCP 服务器自动启动（AutoStart=true）
3. 在 Claude Code 中即可调用 x64dbg-mcp 工具

### 3.2 配置修改

x64dbg 菜单：`Plugins → x64dbg-MCP Server → Configure MCP Server...`

- `127.0.0.1`：仅本机访问（默认）
- `0.0.0.0`：允许 WSL/远程访问
- token 可重新生成或复制

---

## 4. 工具清单（分类）

### 4.1 始终可用（11 个）

| 工具 | 说明 |
|------|------|
| `GetDebugState` | 当前调试器状态、PID、指令指针 |
| `LoadBinary` | 加载可执行文件到调试器 |
| `ExecuteDebuggerCommand` | 执行任意 x64dbg 命令 |
| `ListCommandsByCategory` | 列出可用工具 |
| `SearchForStrings` | 搜索进程内存文本 |
| `GetEventLog` | 最近 N 条调试事件 |
| `ClearEventLog` | 清空事件日志 |
| `EvalExpression` | 求值 x64dbg 表达式 |
| `AttachProcess` | 按 PID 附加进程 |
| `Echo` | 回显输入 |
| `WaitForEvent` | 长轮询调试事件 |

### 4.2 执行控制（11 个）

| 工具 | 说明 |
|------|------|
| `run` | 继续运行（F9） |
| `StepInto` | 单步进入（F7） |
| `StepOver` | 单步跳过（F8） |
| `StepOut` | 运行到返回（Ctrl+F9） |
| `PauseDebug` | 暂停（F12） |
| `StopDebug` | 终止调试 |
| `RestartDebug` | 重启调试 |
| `WaitForPause` | 阻塞直到暂停 |
| `RunToAddress` | 运行到指定地址 |
| `TraceInto` | 单步 N 条指令并记录 |
| `TraceOver` | 单步跳过 N 条指令 |

### 4.3 断点管理（13 个）

| 工具 | 说明 |
|------|------|
| `SetBreakpoint` | 软件断点（INT3） |
| `SetHardwareBreakpoint` | 硬件断点（DR0-DR3） |
| `SetConditionalBreakpoint` | 条件断点 |
| `SetMemoryBreakpoint` | 内存断点（读/写/执行） |
| `SetExceptionBreakpoint` | 异常断点 |
| `EnableBreakpoint` / `DisableBreakpoint` | 启用/禁用 |
| `ToggleBreakpoint` | 切换断点 |
| `DeleteBreakpoint` / `DeleteAllBreakpoints` | 删除断点 |
| `ResetHitCount` | 重置命中计数 |
| `ListBreakpoints` | 列出断点 |
| `SetBreakpointCommand` | 断点命中时执行命令 |
| `SetBreakpointFastResume` | 快速恢复（自动继续） |

### 4.4 寄存器与内存（9 个）

| 工具 | 说明 |
|------|------|
| `GetAllRegisters` | 全部通用寄存器 |
| `SetRegister` | 设置寄存器值 |
| `ReadMemory` | 内存 hex dump |
| `WriteMemToAddress` | 写入内存 |
| `GetMemoryMap` | 内存区域（地址/大小/保护） |
| `GetDumpableRegions` | 可 dump 区域 |
| `AllocateMemory` / `FreeMemory` | 分配/释放内存 |
| `RestorePatches` | 恢复所有补丁 |
| `FollowPointer` | 解引用指针链 N 层 |

### 4.5 反汇编与分析（10 个）

| 工具 | 说明 |
|------|------|
| `GetCurrentAddress` | 当前 EIP/RIP + 标签 + 注释 |
| `Disassemble` | 反汇编 N 条指令 |
| `DisassembleFunction` | 反汇编整个函数 |
| `Assemble` | 汇编一条指令 |
| `AnalyzeCode` | 代码分析（函数/模块/控制流） |
| `GetFunctions` | 列出分析出的函数 |
| `GetReferences` | 查找 CALL/JMP 引用（xref） |
| `GetImports` / `GetExports` | 导入/导出表 |
| `AnalyzeModule` | PE 结构分析 |
| `DetectOEP` | 检测加壳程序 OEP |

### 4.6 模块、符号、线程（12 个）

| 工具 | 说明 |
|------|------|
| `ListModules` | 已加载模块 |
| `SearchSymbols` / `ListSymbols` | 符号搜索/列表 |
| `GetCallStack` | 调用栈 |
| `GetThreads` | 线程列表 |
| `SwitchThread` | 切换线程 |
| `SuspendThread` / `ResumeThread` | 挂起/恢复线程 |
| `GetSEHChain` | SEH 链（x32） |
| `GetPEB` | PEB 结构 |
| `GetArguments` | 函数参数（栈/寄存器） |
| `GetStrings` | 提取 ASCII 字符串 |
| `FindPattern` | 字节模式扫描（?? 通配符） |

### 4.7 注释、标签、书签（7 个）

| 工具 | 说明 |
|------|------|
| `CommentOrLabelAtAddress` | 地址添加注释/标签 |
| `SetBookmark` / `DeleteBookmark` / `ListBookmarks` | 书签管理 |
| `GetPatches` | 补丁列表 |
| `WatchExpressions` | 批量求值表达式 |
| `SaveDatabase` | 保存 x64dbg 数据库 |

### 4.8 Dump（2 个）

| 工具 | 说明 |
|------|------|
| `DumpMemory` | 内存区域保存到文件 |
| `DumpModule` | 整个模块 dump |

---

## 5. 与 REA 配合使用

### 5.1 互补关系

| | REA | x64dbg-MCP |
|--|-----|-----------|
| 定位 | 逆向 Agent Framework | Debugger Bridge |
| 关注 | 该查什么？证据是什么？ | 运行/断点/内存/寄存器 |
| 分析 | 静态（伪代码/调用图） | 动态（运行时行为） |

### 5.2 组合工作流

```
REA
  ↓ 静态定位关键函数
  ↓ 形成分析假设
x64dbg-MCP
  ↓ 动态下断点验证
  ↓ 读寄存器/内存确认
  ↓ 把结果写回 REA 的 Evidence
```

### 5.3 典型会话示例

```
用户: 加载 calc.exe 并在入口断点
AI: [LoadBinary, SetBreakpoint, run, WaitForPause]
    → 已加载 calc.exe，命中断点 0x7FF7A1234000

用户: 当前寄存器？
AI: [GetAllRegisters]
    → RAX: 0x0, RCX: 0x7FF7A1234000, ...

用户: 读当前 IP 的 64 字节
AI: [ReadMemory]
    → 48 83 EC 28 E8 12 34 00 00 ...

用户: 单步跳过 3 条并看栈
AI: [StepOver x3, GetCallStack]
    → 已步到 0x7FF7A1234010，调用栈: ...
```

---

## 6. 安全注意事项

1. **Bearer token 强制**：每次请求必须携带，未授权返回 401
2. **HTTP 明文**：服务器走未加密 HTTP，勿暴露到不可信网络
3. **完整调试器控制**：可读写进程内存、执行代码、操作进程
4. **仅限合法用途**：逆向研究、恶意软件分析、安全研究、教育
5. **默认仅本机**：`127.0.0.1`，除非必要勿改 `0.0.0.0`

---

## 7. 关键信息速查

| 项目 | 值 |
|------|-----|
| 插件文件（x64） | `x64dbg-MCP-Server.dp64` |
| 插件文件（x32） | `x64dbg-MCP-Server.dp32` |
| x64 端口 | `9094` |
| x32 端口 | `9095` |
| 认证 token | `fc8492267d8c010c45d5760f42e05db9` |
| 配置文件 | `D:\tools\x64dbg\release\x64\mcp_config.json` |
| MCP 传输 | Streamable HTTP（`/`）+ SSE（`/sse`） |
| 工具数量 | 84 个 MCP 工具 + 22 事件回调 |
| 编写语言 | Zig（零依赖，单二进制） |

---

*本文档为 x64dbg-MCP 的安装与使用记录，用于后续调试分析参考。*
