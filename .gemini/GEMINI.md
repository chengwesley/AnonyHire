# Gemini — AnonyHire

## 專案說明
AI 驅動的招募隱私與公平性防護系統。透過物理脫敏與多層級倫理稽核，確保 AI 招募符合 EU AI Act 等法規，排除演算法偏見。

## Gemini 的職責範圍
- 履歷文件的多模態解析（PDF、圖片）
- 法規文件研究與合規性分析
- 偏見案例的資料集建立

## 禁區（不要動）
- Claude 負責的脫敏核心邏輯（scripts/）
- rules/ 資料夾（由 Claude 維護）

## 重要規則
- Session 開始先讀 `AI_HANDOFF.md`
- Session 結束前更新 `AI_HANDOFF.md` 並 push
