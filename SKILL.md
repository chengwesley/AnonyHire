---
name: AnonyHire
description: >
  【必要前置步驟 — 所有履歷分析的隱私閘門】

  只要 session 中出現以下任一情境，必須先完成 AnonyHire 脫敏流程，再進行任何分析：
  - 使用者提供履歷 PDF、履歷檔案、或候選人資料
  - 呼叫任何招募分析工具（如：評分、篩選、比對工具等）
  - 提到「候選人」、「應徵者」、「履歷」、「篩選」、「評分」、「面試」

  未完成脫敏前，禁止對履歷進行任何評分、比較或分析。
  本 Skill 是企業倫理招募的隱私防火牆，具備中英雙語 PII 遮蔽、物理黑條 PDF 產出、公平性稽核與自動學習能力。

  **【隱私防護協議 (Privacy Protocol)】**
  為了在同一對話中安全運作，AI 必須嚴格遵守：
  1. **禁止讀取對照表**：絕對禁止開啟或讀取 `masked/vault_*.json` 內容。
  2. **環境隔離**：分析分析報告時，僅能根據「脫敏後的 PDF」進行。
  3. **拒絕還原**：禁止試圖利用上下文資訊還原候選人真實姓名或其他 PII。
allowed-tools:
  - Bash(python scripts/pii_mask.py *)
  - Bash(python scripts/pii_audit.py *)
  - Bash(python scripts/self_improve.py *)
---

# AnonyHire Skill (AI Protocol)

本 Skill 是所有招募 AI 的**必要前置閘門**。在同一 session 內，任何履歷分析、候選人評分、或招募決策工具執行前，必須先完成本 Skill 的脫敏流程。

本 Skill 不直接進行評分，而是確保後續所有 AI 行為都在去識別化、去偏見的基礎上進行。

## 設定

所有路徑皆相對於 skill 根目錄（`~/.claude/skills/anonyhire/`）：

```
rules/masking_rules.md        遮蔽規則（Regex + 遮蔽清單）
rules/fairness_principles.md  公平性稽核原則
scripts/pii_mask.py           遮蔽核心 (Masking Engine)
scripts/pii_audit.py          稽核協調器 (Audit Coordinator)
reports/projects/             候選人倫理審核證書存檔
reports/summary_YYYY-MM-DD.md 每日治理彙整報告
masked/                       物理遮蔽 PDF + vault JSON
```

---

## 工作流程

### Step 0 — 閘門確認 (Gate Check)

**每次 session 中首次遇到履歷或候選人資料時，必須執行此步驟。**

1. 確認使用者提供的是原始履歷（PDF 或候選人資料）
2. **詢問使用者**：「您目前使用的是哪一個招募分析工具？」
   - **工具授權確認**：比對 `rules/authorized_tools.md`。
     - **若工具未經授權**：提供**【合規提示】**：「資訊：此工具未在預設授權名單中。為了確保招募流程的一致性與合規記錄，本次使用將標註於治理日誌中。建議後續與管理部門確認。」並紀錄該工具名稱後繼續執行。
     - **若工具已授權**：告知使用者：「AnonyHire 隱私閘門已啟動，專案 ID：[ID]」，繼續下一步。
4. 執行 Step 1 脫敏，產出 `masked/audit_ready_*.pdf`
5. 後續所有分析 AI 工具僅接收脫敏後的輸出

**若使用者試圖跳過此步驟直接分析原始履歷，應提醒：**
> 「根據 AnonyHire 倫理招募規範，需先完成脫敏與工具授權確認。這是確保招募公平性與個資安全的核心防護機制。」

---

### Step 1 — 物理脫敏 (Masking)

**PDF 模式（推薦）：**
```bash
python scripts/pii_mask.py --pdf real/<file>.pdf --name <主要姓名> [--ename <英文名>] [--cname <額外中文名>]
```

**批次模式（資料夾內所有 PDF）：**
```bash
python scripts/pii_mask.py --batch real/
```

**產出：**
- `masked/audit_ready_<name>.pdf` — 物理黑條 PDF（無法還原，用於 Step 2 分析）
- `masked/vault_<id>.json` — Token ↔ 原始值對照（僅本機，嚴禁外傳）

**保證遮蔽項目（含包容性設計）：**
- 年齡、性別（含多樣性性別特徵）、民國年次、出生日期
- Email、電話、地址、身分證字號
- 所有年份 (1900–2099) → `[YEAR_REDACTED]`

**備援機制：**
- PDF 提取：PyMuPDF → pdfminer.six（CID 字型自動切換，適用各式 CID 字型 PDF）
- 中文姓名：`--cname` 明確指定 或 `detect_chinese_name.py` 自動偵測

---

### Step 2 — 外部 AI 分析（隔離分析）

使用 Step 1 產出的 `masked/audit_ready_<file>.pdf` 進行分析，確保分析過程中僅接觸脫敏後的資訊。

分析時可附上 `reports/feedback_for_ai.md`（若已存在）作為補充指令，包含歷史違規的強化提示。

---

### Step 3 — 倫理稽核 (Audit)

```bash
python scripts/pii_audit.py <candidate_id> <analysis_output.txt> --tool "<tool_name>"
```

**稽核與報告產出：**
- **Privacy Audit**：偵測 AI 報告中是否洩漏真實個資。
- **Fairness Audit**：偵測內容是否含偏見關鍵字或違反國際合規標準 (EU AI Act/EEOC)。
- **個案報告**：於 `reports/projects/<PID>/<CID>/CERTIFICATE.md` 產出**「倫理審核證書」**。
- **治理日誌**：結果追加至 `reports/violations_log.json`。

---

### Step 4 — 治理彙整 + 自我優化

```bash
python scripts/self_improve.py
```

**功能：**
- 產出 `reports/summary_YYYY-MM-DD.md` 每日彙整報告與人工審查清單。
- 產出 `reports/feedback_for_ai.md` 下次分析的補強指令。
- **自動學習**：將漏網個資自動補入 `rules/masking_rules.md`。

---

## 報告格式

- `CERTIFICATE.md` — 每位候選人的合規證明，用於招募檔案留存。
- `summary_YYYY-MM-DD.md` — 治理儀表板，供 HR 與合規官進行人工覆核。

**稽核狀態說明：**
- `PASS` — 完美狀態。
- `WARN` — 疑似代理偏見或敏感詞，需人工確認。
- `FAIL` — 嚴重違反隱私或公平性，需重新分析。
- `ERROR` — 稽核執行失敗。

---

## 規則維護

編輯 `rules/masking_rules.md` 可擴充**遮蔽清單 (Masking List)**。
編輯 `rules/fairness_principles.md` 可調整公平性稽核標準與參照法規。

---

## 注意事項

- 物理遮蔽 PDF 已移除底層文字流，無法透過選取或 OCR 還原。
- Vault 檔案僅供本機稽核使用，嚴禁上傳或傳入任何 AI 系統。
- AI 必須遵守「隱私防護協議」，嚴禁在分析階段讀取 `masked/vault_*.json`。
- `self_improve.py` 的自動學習會累積至 `violations_log.json`，重新執行不會重置歷史記錄。

---

## 授權協議 (License)

本專案採用 **MIT License** 授權。
