# GL Reconciliation 演示（串行 Pipeline + spawn 时工具限制）

本地模拟数据，不需要任何 MCP。演示 gl-reconciler 插件的串行协作链：

    主 agent → gl-reconciler (L1, 无写权限)
        → reader ×2 (L2, 只读) → 根因(bash) → critic (L2, 只读复核) → resolver (L2, 唯一可写)

## 运行

1. 把两个 CSV 复制到 workspace：

   ```powershell
   Copy-Item examples/gl-recon-demo/*.csv workspace/
   ```

2. 启动 CLI（PowerShell，GBK 控制台先设编码）：

   ```powershell
   $env:PYTHONIOENCODING="utf-8"; uv run mini-agent
   ```

3. 输入任务：

   ```text
   Run the GL reconciliation for trade date 2026-09-25, asset classes: equities, fixed income. The extracts are workspace/gl_extract.csv and workspace/subledger_extract.csv — internal-gl and subledger MCPs are not available today, so read the files directly.
   ```

## 预设 break

| key | 类型 | 说明 |
|---|---|---|
| ABC123 | mapping | GL 记 11420，SL 记 11410 |
| DEF456 | FX | 金额差 3.40（-2500.00 vs -2496.70） |
| GHI789 | timing | posting date 差一天（09-26 vs 09-25） |
| JKL012 | duplicate | SL 重复一条 |
| MNO345 | subledger-only | GL 缺失 |

## 验收点

- workspace 出现 resolver 写出的 exception report 文件
- 日志（运行时打印的 log 文件路径）里 reader 只有 `read_file` 调用
- 注意：resolver"不接触原始外部内容"由 gl-reconciler 的任务文本纪律保证（spec §Review Focus #4），不是工具机制强制
