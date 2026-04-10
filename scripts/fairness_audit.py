#!/usr/bin/env python3
"""
Fairness Audit Agent — AnonyHire

稽核 AI 分析報告是否含偏見。分兩層：
  FAIL  — 明確提及受保護屬性（直接歧視，需打回重做）
  WARN  — 含代理指標或疑似偏見詞彙（需人工確認）
  PASS  — 未偵測到任何問題
"""
import json
import re
import sys
from pathlib import Path

# ── 硬編碼觸發詞 ─────────────────────────────────────────────────────────────

# FAIL：直接提及受保護屬性，明確違反就業服務法 / Title VII
FAIL_KEYWORDS_ZH = [
    '歲', '年齡', '出生年', '幾歲',           # 年齡
    '性別', '男性', '女性', '男生', '女生',    # 性別
    '已婚', '未婚', '婚姻',                    # 婚姻狀況
    '懷孕', '生育', '育嬰',                    # 生育代理
    '原住民', '新住民', '族裔',                # 種族/族裔
    '宗教', '信仰', '教會', '清真寺',          # 宗教
    '身障', '殘疾', '自閉', '過動',            # 身心障礙
    '政黨', '黨籍',                            # 政治
]

FAIL_KEYWORDS_EN = [
    'years old', 'born in', 'birth year',           # 年齡（排除裸字 age，改用 regex）
    'gender', 'male', 'female', 'sex',              # 性別
    'married', 'single', 'marital',                 # 婚姻
    'pregnant', 'maternity',                        # 生育
    'race', 'ethnicity', 'hispanic', 'latino',      # 種族
    'religion', 'church', 'mosque',                 # 宗教
    'disability', 'disabled', 'autism', 'adhd',     # 身心障礙
]

# 年齡相關詞用整字比對（避免 stage/manage/average 誤觸）
FAIL_REGEX_EN = [
    r'\bage\b',       # "age" 獨立單字才算，years of experience 不觸發
]

# 職能詞白名單：出現這些詞時，age 觸發視為誤判跳過
AGE_WHITELIST_CONTEXT = [
    'years of experience', 'year of experience',
    'years experience', '年資', '工作年資', '年限',
]

# WARN：代理指標或疑似偏見，中性但需人工確認
WARN_KEYWORDS_ZH = [
    '空窗期', '就業空白', '兵役', '役畢', '免役',  # 代理偏見
    '家庭背景', '家中成員', '排行',                 # 家庭代理
    '星座', '血型',                                 # 台灣特有偽科學代理
    '外貌', '容貌', '五官', '身高', '體重',         # 外貌
    '口音', '腔調',                                 # 語言歧視代理
    '郵遞區號',                                     # 社經地位代理
]

WARN_KEYWORDS_EN = [
    'gap', 'employment gap', 'career gap',          # 空窗期代理
    'zip code', 'neighborhood',                     # 地區代理
    'accent', 'foreign',                            # 語言代理
    'appearance', 'looks', 'height', 'weight',      # 外貌
    'sorority', 'fraternity', 'hbcu',               # 學校/族裔代理
    'union', 'trade union',                         # 工會
]


def load_custom_keywords(rules_path: Path):
    """從 masking_rules.md 載入自訂黑名單作為額外 WARN 詞。"""
    if not rules_path.exists():
        return [], []
    content = rules_path.read_text(encoding='utf-8')
    cn = re.findall(r'- `([\u4e00-\u9fff]+)`', content)
    en = re.findall(r'- `([A-Za-z][\w\s\']*)`', content)
    return cn, en


def run_fairness_audit(report_text: str, extra_warn_zh: list, extra_warn_en: list):
    report_lower = report_text.lower()
    fail_flags = []
    warn_flags = []

    # FAIL 檢查（中文）
    for kw in FAIL_KEYWORDS_ZH:
        if kw in report_text:
            fail_flags.append(kw)

    # FAIL 檢查（英文）
    for kw in FAIL_KEYWORDS_EN:
        if kw in report_lower:
            fail_flags.append(kw)

    # FAIL 檢查（英文 regex，整字比對）
    has_age_whitelist = any(ctx in report_lower for ctx in AGE_WHITELIST_CONTEXT)
    for pattern in FAIL_REGEX_EN:
        if re.search(pattern, report_lower):
            # \bage\b：若同時有年資白名單詞，視為職能描述，跳過
            if pattern == r'\bage\b' and has_age_whitelist:
                continue
            fail_flags.append(re.sub(r'\\b', '', pattern))

    # WARN 檢查（中文）
    for kw in WARN_KEYWORDS_ZH + extra_warn_zh:
        if kw in report_text and kw not in fail_flags:
            warn_flags.append(kw)

    # WARN 檢查（英文）
    for kw in WARN_KEYWORDS_EN + extra_warn_en:
        if kw in report_lower and kw not in fail_flags:
            warn_flags.append(kw)

    # 去重
    fail_flags = list(dict.fromkeys(fail_flags))
    warn_flags = list(dict.fromkeys(warn_flags))

    if fail_flags:
        status = 'FAIL'
    elif warn_flags:
        status = 'WARN'
    else:
        status = 'PASS'

    return status, fail_flags, warn_flags


def main():
    if len(sys.argv) < 3:
        sys.exit(1)

    report_path = Path(sys.argv[2])
    skill_dir = Path(__file__).parent.parent
    rules_path = skill_dir / 'rules' / 'masking_rules.md'

    report_text = report_path.read_text(encoding='utf-8')
    extra_zh, extra_en = load_custom_keywords(rules_path)
    status, fail_flags, warn_flags = run_fairness_audit(report_text, extra_zh, extra_en)

    result = {
        'agent': 'FairnessAuditAgent',
        'status': status,
        'flags': fail_flags + warn_flags,
        'fail_flags': fail_flags,
        'warn_flags': warn_flags,
    }
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
