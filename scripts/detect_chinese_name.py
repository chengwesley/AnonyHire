#!/usr/bin/env python3
"""
Chinese Name Auto-Detector
自動從文字中偵測中文姓名，無需手動傳入 --cname

策略：
  1. 上下文模式 (高精度) — 括號內中文、姓名標籤後的中文
  2. 姓氏表比對 (中精度) — 常見姓氏 + 1-3 字元給名
  3. 英文名旁比對 (輔助)  — 英文名附近的中文字串

Usage:
  python detect_chinese_name.py <pdf_path>
  python detect_chinese_name.py <pdf_path> --ename "Emily"
"""
import re
import sys
from pathlib import Path
from typing import List

# 常見中文姓氏（百家姓前 150 名）
COMMON_SURNAMES = set(
    "趙錢孫李周吳鄭王馮陳褚衛蔣沈韓楊朱秦尤許何呂施張孔曹嚴華金魏陶姜"
    "戚謝鄒喻柏水竇章雲蘇潘葛奚范彭郎魯韋昌馬苗鳳花方俞任袁柳酆鮑史唐"
    "費廉岑薛雷賀倪湯滕殷羅畢郝鄔安常樂于時傅皮卞齊康伍余元卜顧孟平黃"
    "和穆蕭尹姚邵湛汪祁毛禹狄米貝明臧計伏成戴談宋茅龐熊紀舒屈項祝董梁"
    "杜阮藍閔席季麻強賈路婁危江童顏郭梅盛林刁鐘徐丘駱高夏蔡田樊胡凌霍"
)


def extract_from_context(text: str) -> List[str]:
    """
    高精度：從上下文模式中提取中文姓名
    """
    candidates = []
    patterns = [
        # 括號內的中文名：(陳慧心)、（王小明）
        r'[（(]\s*([\u4e00-\u9fff]{2,4})\s*[）)]',
        # 標籤後的中文名：姓名：陳慧心、中文名:王小明
        r'(?:姓名|中文名|名字|Name)[：:]\s*([\u4e00-\u9fff]{2,4})',
        # 履歷標題格式：個人履歷：王小美 (Wang...)、履歷：佐藤和也 (Sato...)
        r'(?:個人履歷|履歷|簡歷)[：:]\s*([\u4e00-\u9fff]{2,4})\s*[（(]',
        # 冒號後直接跟中文名再跟英文名括號（通用格式）
        r'[：:]\s*([\u4e00-\u9fff]{2,4})\s+[（(][A-Z]',
        # 「我是 xxx」
        r'我是\s*([\u4e00-\u9fff]{2,4})',
        # 「候選人：xxx」
        r'候選人\s*[：:]\s*([\u4e00-\u9fff]{2,4})',
        # 「本人 xxx」
        r'本人\s*([\u4e00-\u9fff]{2,4})',
        # Email 前的中文名
        r'([\u4e00-\u9fff]{2,4})\s+[a-zA-Z][\w.+-]*@',
        # 英文名後括號：Emily Chen (陳慧心)
        r'[A-Z][a-zA-Z]+\s+[A-Z][a-zA-Z-]+\s+[（(]([\u4e00-\u9fff]{2,4})[）)]',
        # Resume 第一行格式：Resume: Emily Chen (陳慧心)
        r'Resume\s*:\s*[A-Z][a-zA-Z]+\s+[A-Z][a-zA-Z]+\s+[（(]([\u4e00-\u9fff]{2,4})[）)]',
    ]
    for pat in patterns:
        for m in re.finditer(pat, text):
            name = m.group(1)
            if name and len(name) >= 2:
                candidates.append(name)
    return candidates


_SURNAME_EXCLUSIONS = {
    # 地名
    '台灣', '台北', '台中', '台南', '高雄', '新竹', '桃園', '基隆', '嘉義', '台東',
    '花蓮', '宜蘭', '苗栗', '彰化', '南投', '雲林', '屏東', '澎湖', '金門', '馬祖',
    '北京', '上海', '廣州', '深圳', '香港', '新加坡',
    # 常見職稱/部門/學校詞
    '工程師', '工程部', '工程學', '工程系', '工程院',
    '林口', '林業', '林園', '林森', '江南', '江北', '江蘇', '江西',
    '周邊', '周遭', '楊梅', '楊光', '梁山', '梁柱',
    '李白', '李商', '唐山', '唐朝', '宋朝', '宋詞',
    # 常見動詞/形容詞開頭詞
    '負責', '參與', '管理', '協助', '執行', '維護', '設計', '開發',
    '專案', '專業', '技能', '學歷', '學校', '學院', '學系',
    '公司', '公務', '部門', '職位', '職能',
}


def extract_by_surname(text: str) -> List[str]:
    """
    中精度：姓氏開頭 + 1-3 字元給名 的中文字串。
    只掃描前 300 字（履歷標題區），並排除已知非姓名詞彙，降低誤觸率。
    """
    candidates = []
    # 只看前 300 字，姓名通常在履歷開頭
    scan_text = text[:300]
    pattern = r'(?:^|[\s，。、\n（(「])([' + ''.join(COMMON_SURNAMES) + r'][\u4e00-\u9fff]{1,3})'
    for m in re.finditer(pattern, scan_text, re.MULTILINE):
        candidate = m.group(1)
        if 2 <= len(candidate) <= 4 and candidate not in _SURNAME_EXCLUSIONS:
            candidates.append(candidate)
    return candidates


def extract_near_english_name(text: str, english_name: str) -> List[str]:
    """
    輔助：英文名附近（同行或相鄰行）的中文字串
    """
    if not english_name:
        return []
    candidates = []
    # 找英文名所在的行及上下各 1 行
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if re.search(re.escape(english_name), line, re.IGNORECASE):
            # 在這行及相鄰行中找中文
            context = '\n'.join(lines[max(0, i-1):min(len(lines), i+2)])
            for m in re.finditer(r'[\u4e00-\u9fff]{2,4}', context):
                cn = m.group()
                # 過濾常見非名詞中文詞彙
                if cn not in {'簡歷', '履歷', '學歷', '工作', '經驗', '技能', '設計', '工程', '專案', '年份', '職位', '公司'}:
                    candidates.append(cn)
    return candidates


def detect_chinese_names(text: str, english_name: str = '') -> List[str]:
    """
    主函式：綜合三種策略，去重、排序回傳
    """
    found = []

    # 優先級 1：上下文模式（高精度）
    ctx = extract_from_context(text)
    found.extend(ctx)

    # 優先級 2：英文名附近（輔助，僅在上下文無結果時加入）
    if not found and english_name:
        near = extract_near_english_name(text, english_name)
        found.extend(near)

    # 優先級 3：姓氏比對（最後回退）
    if not found:
        sur = extract_by_surname(text)
        found.extend(sur)

    # 去重，保持優先順序
    seen = set()
    result = []
    for name in found:
        if name not in seen and len(name) >= 2:
            seen.add(name)
            result.append(name)

    return result


def main():
    if len(sys.argv) < 2:
        print("Usage: python detect_chinese_name.py <pdf_or_text_path> [--ename <english_name>]")
        sys.exit(1)

    path = Path(sys.argv[1])
    english_name = ''
    args = sys.argv[2:]
    if '--ename' in args:
        idx = args.index('--ename')
        english_name = args[idx + 1] if idx + 1 < len(args) else ''

    # 讀取文字
    text = ''
    if path.suffix.lower() == '.pdf':
        try:
            import fitz
            doc = fitz.open(str(path))
            text = '\n'.join(page.get_text() for page in doc)
            doc.close()
        except ImportError:
            print("PyMuPDF not installed. Please provide a .txt file.", file=sys.stderr)
            sys.exit(1)
    else:
        text = path.read_text(encoding='utf-8')

    names = detect_chinese_names(text, english_name)

    if names:
        print(f"Detected Chinese names: {names}", file=sys.stderr)
        # stdout: 空格分隔，供 shell 使用
        for name in names:
            print(name)
    else:
        print("No Chinese names detected.", file=sys.stderr)


if __name__ == '__main__':
    main()
