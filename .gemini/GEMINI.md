# Gemini — AnonyHire

## 專案說明
AI 驅動的招募隱私與公平性防護工具。透過物理脫敏與多層級倫理稽核，確保 AI 招募符合 EU AI Act，排除演算法偏見。

## 技術棧
- Python（scripts/、rules/）
- Claude API
- 無前端框架

## 開發慣例
- 脫敏邏輯修改前需有測試案例
- masked/ 資料夾內容只讀，不提交到 git
- rules/ 的規則異動需在 HANDOFF 說明原因

## 不要手動修改的檔案（自動產生）
- masked/（執行期產生）
- reports/（執行期產生）

## Handoff 協議
- **Session 開始**：先 `git pull`，再讀 `AI_HANDOFF.md` 了解目前進度與誰在負責哪個檔案
- **Session 進行中**：若要動某個檔案，先確認 AI_HANDOFF.md 裡沒有 🔒 標記
- **Session 結束**：在 `AI_HANDOFF.md` 最上方新增記錄，移除自己的 🔒，commit & push

### AI_HANDOFF.md 記錄格式
```
## YYYY-MM-DD | Gemini | 家裡／公司
- 完成：（做了什麼）
- 下次：（下個 session 要繼續的）
- 🔒 進行中：（還沒 push 完的檔案，請另一個 AI 暫勿修改）
```
