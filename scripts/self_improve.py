#!/usr/bin/env python3
"""
Self-Improvement Script — AnonyHire
Analyzes violations log to suggest rule updates and AI prompt feedback.

Usage:
  python self_improve.py [--since YYYY-MM-DD] [--keep N]

Options:
  --since YYYY-MM-DD   Only process violations on or after this date
  --keep N             Trim violations_log.json to the latest N entries after processing
"""
import json
import re
import sys
from pathlib import Path
from report_templates import DASHBOARD_TEMPLATE

# Token 格式（不應被自動學習為黑名單）
_TOKEN_PATTERN = re.compile(r'^\[[A-Z_]+_\d{3}\]$')


def parse_args():
    since = None
    keep = None
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == '--since' and i + 1 < len(args):
            since = args[i + 1]; i += 2
        elif args[i] == '--keep' and i + 1 < len(args):
            try:
                keep = int(args[i + 1])
            except ValueError:
                pass
            i += 2
        else:
            i += 1
    return since, keep


def filter_violations(violations, since):
    if not since:
        return violations
    return [v for v in violations if v.get('timestamp', '') >= since]


def analyze_violations(violations):
    suggestions = {
        'new_masking_list': set(),    # PII 洩漏 → 加入遮蔽清單
        'fairness_masking_list': set(), # 公平性漏洞 → 加入遮蔽清單
        'bias_guidelines': set()
    }

    for v in violations:
        privacy = v.get('privacy', {})
        fairness = v.get('fairness', {})

        # 1. PII 洩漏 → 加入遮蔽黑名單
            val = leak.get('value')
            if val and len(str(val)) > 1 and not _TOKEN_PATTERN.match(str(val)):
                suggestions['new_masking_list'].add(str(val))

        # 2. 公平性 FAIL flags → 補入遮蔽清單（閉環）
        for flag in fairness.get('fail_flags', []):
            if flag and len(flag) > 1 and not _TOKEN_PATTERN.match(flag):
                suggestions['fairness_masking_list'].add(flag)

        # 3. 公平性 WARN flags → 生成補強指引
        for flag in fairness.get('warn_flags', []) + fairness.get('flags', []):
            if flag in ('歲', '年齡'):
                suggestions['bias_guidelines'].add("嚴禁在分析中提及『年齡』或『歲數』，即使是讚賞其資深或年輕。")
            if flag in ('女', '男', '性別', 'gender', 'male', 'female'):
                suggestions['bias_guidelines'].add("嚴禁分析候選人的『性別』，請僅專注於專業技能。")

    return suggestions


def generate_feedback_file(skill_dir, suggestions):
    feedback_path = skill_dir / 'reports' / 'feedback_for_ai.md'
    all_blocked = suggestions['new_masking_list'] | suggestions['fairness_masking_list']

    content = f"""# AI 分析優化指引 (Audit Feedback)

本文件由 Audit Agent 根據歷史違規記錄自動生成。請在進行下一次分析時遵循以下準則：

## 1. 嚴禁出現的實體 (Leakage Prevention)
以下文字曾在歷史報告中造成個資洩漏或公平性違規，**嚴禁**在報告中直接提及：
{chr(10).join([f"- `{item}`" for item in sorted(all_blocked)]) if all_blocked else "- 目前無"}

## 2. 倫理與公平性準則 (Fairness Guidelines)
{chr(10).join([f"- {g}" for g in suggestions['bias_guidelines']]) if suggestions['bias_guidelines'] else "- 繼續保持中立客觀的語言。"}

---
*請 AI 助理在執行分析指令前，先讀取此文件作為補充 System Prompt。*
"""
    feedback_path.write_text(content, encoding='utf-8')
    return feedback_path


def update_masking_rules(skill_dir, new_items, section_label='PII'):
    """將新詞加入 masking_rules.md Section 5，跳過 Token 格式與已存在的項目。"""
    rules_path = skill_dir / 'rules' / 'masking_rules.md'
    if not rules_path.exists():
        return

    content = rules_path.read_text(encoding='utf-8')
    valid_items = [
        item for item in new_items
        if f"`{item}`" not in content and not _TOKEN_PATTERN.match(item) and len(item) > 1
    ]
    if not valid_items:
        return

    SECTION_HEADER = "## 5. 自動學習新增 (Auto-Learned)"
    ANCHOR = "## 4. 邏輯排除 (Exclusions)"
    new_lines = "\n".join(f"- `{item}`" for item in sorted(valid_items))

    if SECTION_HEADER in content:
        content = content.replace(SECTION_HEADER, f"{SECTION_HEADER}\n{new_lines}", 1)
    elif ANCHOR in content:
        content = content.replace(ANCHOR, f"{SECTION_HEADER}\n{new_lines}\n\n{ANCHOR}", 1)
    else:
        content += f"\n\n{SECTION_HEADER}\n{new_lines}\n"

    rules_path.write_text(content, encoding='utf-8')
    print(f"[{section_label}] 已更新遮蔽清單：{sorted(valid_items)}")


def trim_violations_log(log_path, violations, keep):
    """保留最新 N 筆，寫回 violations_log.json。"""
    if keep and len(violations) > keep:
        trimmed = violations[-keep:]
        with open(log_path, 'w', encoding='utf-8') as f:
            json.dump(trimmed, f, ensure_ascii=False, indent=2)
        print(f"violations_log.json 已保留最新 {keep} 筆（共 {len(violations)} 筆）。")
        return trimmed
    return violations


def generate_governance_dashboard(skill_dir, violations):
    """Generate a high-level Governance Dashboard (DASHBOARD.md)."""
    from datetime import datetime
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    dashboard_path = skill_dir / 'reports' / 'DASHBOARD.md'

    review_needed = [v for v in violations if v.get('needs_review')]
    pass_list = [v for v in violations if not v.get('needs_review')]
    total_count = len(violations)
    review_percent = round((len(review_needed) / total_count * 100), 1) if total_count > 0 else 0

    # 1. Build Review Rows (Priority)
    review_rows = ""
    all_flags_list = []
    for v in sorted(review_needed, key=lambda x: x.get('timestamp', ''), reverse=True):
        p = v['privacy'].get('status', '?')
        f = v['fairness'].get('status', '?')
        pid = v.get('project_id', 'Unknown')
        cid = v['candidate_id']
        tool = v.get('recruitment_tool', 'Unknown')
        flags = v['fairness'].get('fail_flags', []) + v['fairness'].get('warn_flags', [])
        all_flags_list.extend(flags)
        
        status_text = "🔴 FAIL" if (p == 'FAIL' or f == 'FAIL') else "🟡 WARN"
        flag_str = ", ".join(flags) if flags else "PII Leak"
        cert_link = f"[查看證書](./projects/{pid}/{cid}/CERTIFICATE.md)"
        
        review_rows += f"| {pid} | {cid} | {tool} | {status_text} | {flag_str} | {cert_link} | [ ] 已複核 |\n"

    # 2. Build Pass Rows
    pass_rows = ""
    for v in sorted(pass_list, key=lambda x: x.get('timestamp', ''), reverse=True):
        pid = v.get('project_id', 'Unknown')
        cid = v['candidate_id']
        tool = v.get('recruitment_tool', 'Unknown')
        p = v['privacy'].get('status', '?')
        f = v['fairness'].get('status', '?')
        cert_link = f"[查看證書](./projects/{pid}/{cid}/CERTIFICATE.md)"
        pass_rows += f"| {pid} | {cid} | {tool} | 🟢 PASS | 🟢 PASS | {cert_link} |\n"

    # 3. Stats
    from collections import Counter
    top_flags = ", ".join([f"{k}" for k, _ in Counter(all_flags_list).most_common(3)]) or "無"

    content = DASHBOARD_TEMPLATE.format(
        timestamp=timestamp,
        review_rows=review_rows.strip() or "| - | 沒有待核項目 | - | - | - | - | - |",
        pass_rows=pass_rows.strip() or "| - | 尚無紀錄 | - | - | - | - |",
        total_count=total_count,
        review_percent=review_percent,
        top_flags=top_flags
    )

    dashboard_path.write_text(content, encoding='utf-8')
    return dashboard_path


def main():
    since, keep = parse_args()
    skill_dir = Path(__file__).parent.parent
    log_path = skill_dir / 'reports' / 'violations_log.json'

    if not log_path.exists():
        print("No violations log found. System is performing perfectly!")
        return

    with open(log_path, 'r', encoding='utf-8') as f:
        all_violations = json.load(f)

    violations = filter_violations(all_violations, since)
    if since:
        print(f"篩選 {since} 之後的記錄：{len(violations)}/{len(all_violations)} 筆")

    suggestions = analyze_violations(violations)

    # 1. 生成 AI 補強指引
    feedback_path = generate_feedback_file(skill_dir, suggestions)
    print(f"Generated AI feedback at: {feedback_path}")

    # 2. PII 洩漏 → 自動加入遮蔽清單
    if suggestions['new_masking_list']:
        update_masking_rules(skill_dir, suggestions['new_masking_list'], section_label='PII')

    # 3. 公平性 FAIL → 自動加入遮蔽清單（閉環補強）
    if suggestions['fairness_masking_list']:
        update_masking_rules(skill_dir, suggestions['fairness_masking_list'], section_label='Fairness')

    # 4. 產生治理控制台 (Dashboard)
    dashboard_path = generate_governance_dashboard(skill_dir, violations)
    print(f"Governance Dashboard: {dashboard_path}")

    # 5. violations_log 清理
    if keep:
        trim_violations_log(log_path, all_violations, keep)

    # 6. 摘要輸出
    print("\n### 自我優化摘要 (Self-Improvement Summary) ###")
    all_new = suggestions['new_masking_list'] | suggestions['fairness_masking_list']
    if all_new:
        print("已自動更新以下關鍵字至遮蔽清單：")
        for item in sorted(all_new):
            print(f"- `{item}`")
    else:
        print("未發現新的漏洞。")


if __name__ == '__main__':
    main()
