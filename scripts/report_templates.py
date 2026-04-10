# scripts/report_templates.py

CANDIDATE_CERTIFICATE_TEMPLATE = """# 🛡️ Ethical Screening Certificate
**Candidate ID**: `{candidate_id}` | **Project ID**: `{project_id}`
**Recruitment Tool**: `{tool}` | **Date**: `{timestamp}`

---

## 📊 稽核總結 (Audit Summary)

{status_badge}

| 項目 | 狀態 | 詳情 |
| :--- | :--- | :--- |
| **隱私保護 (Privacy)** | {privacy_status} | {privacy_detail} |
| **公平競爭 (Equity)** | {fairness_status} | {fairness_detail} |

---

## 🔍 稽核證據 (Audit Evidence)

### 1. 隱私洩漏偵測 (Privacy Leaks)
{privacy_leaks_list}

### 2. 公平性偏見偵測 (Fairness Flags)
{fairness_flags_list}

---

## 📝 原始報告存檔 (Original Report Snapshot)
> [!NOTE]
> 原始分析報告已備份至同目錄下的 `analysis_original.txt`。

---
*Digitally Signed by AnonyHire Audit Engine*
"""

DASHBOARD_TEMPLATE = """# 📊 AnonyHire 治理控制台 (Governance Dashboard)
最後更新時間：`{timestamp}`

---

## 🚨 需要進行人工審核 (Manual Review Required)
下表列出偵測到隱私洩漏或公平性疑慮的候選人，請管理人員點擊連結進行複核。

| 專案 ID | 候選人 | 工具 | 狀態 | 警告標籤 | 操作 | 審核狀態 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
{review_rows}

---

## ✅ 已通過合規 (Compliant)
下表為完全通過倫理稽核的候選人。

| 專案 ID | 候選人 | 工具 | 隱私 | 公平性 | 詳情 |
| :--- | :--- | :--- | :--- | :--- | :--- |
{pass_rows}

---

## 📈 統計概覽 (Insights)
- **總處理份數**：{total_count}
- **需人工審查比例**：{review_percent}%
- **常見風險標籤**：{top_flags}

---
*本報告由 AnonyHire 自動生成。*
"""
