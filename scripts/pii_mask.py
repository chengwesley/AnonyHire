#!/usr/bin/env python3
"""
PII Masking Script — AnonyHire
Usage: python pii_mask.py <candidate_id> <project_path>

Output (stdout): JSON with keys:
  masked_profile  — candidate data with PII replaced by tokens
  resume_text     — extracted + masked resume text (HTML or PDF)
  pii_fields      — list of fields that were masked
  masked_pdf_file — path to the redacted PDF
"""
import json
import re
import sys
import uuid
from pathlib import Path
from datetime import datetime
from html.parser import HTMLParser

# Import Chinese name detector (same directory)
sys.path.insert(0, str(Path(__file__).parent))
try:
    from detect_chinese_name import detect_chinese_names
    HAS_CN_DETECTOR = True
except ImportError:
    HAS_CN_DETECTOR = False

try:
    import fitz  # PyMuPDF
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False

try:
    import io as _io
    import logging as _logging
    from pdfminer.high_level import extract_text_to_fp
    from pdfminer.layout import LAParams
    HAS_PDFMINER = True
except ImportError:
    HAS_PDFMINER = False


def _is_garbled(text: str) -> bool:
    """偵測文字是否為 CID 字型損毀輸出。
    判斷依據：高比例的 Latin-1 supplement / private use chars 混入中文文件。
    """
    if not text or len(text) < 20:
        return False
    total = len(text)
    # 正常 CJK 字元
    cjk = sum(1 for c in text if '\u4e00' <= c <= '\u9fff' or '\u3400' <= c <= '\u4dbf')
    # 損毀特徵：Latin Extended / cp950 亂碼範圍大量出現
    garbled = sum(1 for c in text if '\u0080' <= c <= '\u00ff' or '\uf000' <= c <= '\uf8ff')
    if total == 0:
        return False
    # 如果亂碼字元多於正常 CJK，且亂碼比例超過 5%，視為損毀
    return garbled > cjk and garbled / total > 0.05


def extract_pdf_text(pdf_path: Path) -> str:
    """多層備援 PDF 文字提取：PyMuPDF → pdfminer（CID 字型備援）。"""
    text = ""

    # Layer 1: PyMuPDF（速度快，但 CID 字型可能損毀）
    if HAS_PYMUPDF:
        try:
            doc = fitz.open(str(pdf_path))
            text = '\n'.join(page.get_text() for page in doc)
            doc.close()
        except Exception:
            text = ""

    # Layer 2: 若 PyMuPDF 輸出損毀，切換至 pdfminer
    if _is_garbled(text) and HAS_PDFMINER:
        try:
            _logging.getLogger('pdfminer').setLevel(_logging.ERROR)
            buf = _io.StringIO()
            with open(str(pdf_path), 'rb') as f:
                extract_text_to_fp(f, buf, laparams=LAParams(),
                                   output_type='text', codec='utf-8')
            candidate = buf.getvalue()
            if candidate.strip():
                text = candidate
                print(f"[FontFallback] pdfminer used for: {pdf_path.name}", file=sys.stderr)
        except Exception as e:
            print(f"[FontFallback] pdfminer failed: {e}", file=sys.stderr)

    return text


# ── HTML text extractor ──────────────────────────────────────────────────────

class _StripHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self._parts = []

    def handle_data(self, data):
        self._parts.append(data)

    def get_text(self):
        return ' '.join(p.strip() for p in self._parts if p.strip())


def strip_html(html: str) -> str:
    parser = _StripHTML()
    parser.feed(html)
    return parser.get_text()


# ── PII masking ──────────────────────────────────────────────────────────────

class PIIMasker:
    def __init__(self, rules_path: Path = None):
        self.vault = {}
        self._counter = 0
        self.doc_language = 'CHINESE'
        self.rules = {
            'regex': [],
            'masking_list_cn': [],
            'masking_list_en': [],
            'transforms': []
        }
        if rules_path and rules_path.exists():
            self._load_rules(rules_path)

    def _load_rules(self, path: Path):
        content = path.read_text(encoding='utf-8')
        # Parse Regex patterns
        regex_matches = re.findall(r'\| (.*?) \| `(.*?)` \|', content)
        for _, pattern in regex_matches:
            self.rules['regex'].append(pattern)

        # Parse Masking Lists by section
        cn_section = re.search(r'## 2\. \[CHINESE\].*?(?=## 3\. \[ENGLISH\]|## 4\. \w+)', content, re.DOTALL)
        if cn_section:
            self.rules['masking_list_cn'] = re.findall(r'- `(.*?)`', cn_section.group())
            
        en_section = re.search(r'## 3\. \[ENGLISH\].*?(?=## 4\. \w+)', content, re.DOTALL)
        if en_section:
            self.rules['masking_list_en'] = re.findall(r'- `(.*?)`', en_section.group())

        # Also grab Auto-Learned items (stopping before any other header)
        auto_section = re.search(r'## 5\. 自動學習新增.*?(?=##|$)', content, re.DOTALL)
        if auto_section:
            self.rules['masking_list_cn'].extend(re.findall(r'- `(.*?)`', auto_section.group()))

    def detect_language(self, text: str):
        # Very simple check: if any Chinese character exists, assume Chinese
        if re.search(r'[\u4e00-\u9fff]', text):
            self.doc_language = 'CHINESE'
        else:
            self.doc_language = 'ENGLISH'

    def _extract_english_name(self, text: str) -> str:
        """Extract full English name (First Last) from resume text.

        Strategy (highest confidence first):
          1. Explicit label: "Name: John Smith"
          2. Resume header: first non-empty line that looks like "First[ Middle] Last"
          3. Self-introduction phrases: "I'm / I am / called"
          4. Chinese introduction: "我是 ... John"
        Returns the full matched name string (may include first+last).
        """
        # 1. Labelled name field
        label_pat = re.search(
            r'(?:^|\n)\s*(?:Name|Full Name)\s*[:\-]\s*([A-Z][a-z]{1,19}(?:\s+[A-Z][a-z]{0,19}){1,2})',
            text, re.MULTILINE
        )
        if label_pat:
            return label_pat.group(1).strip()

        # 2. First non-empty line matching "Firstname Lastname" (pure English resume header)
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            m = re.fullmatch(r'([A-Z][a-z]{1,19}(?:\s+[A-Z][a-z]{0,19}){1,2})', line)
            if m:
                return m.group(1)
            break  # only check the very first non-empty line

        # 3. Self-introduction phrases
        intro_patterns = [
            r"I(?:'m| am)\s+([A-Z][a-z]{1,19}(?:\s+[A-Z][a-z]{1,19})?)\b",
            r'\bcalled\s+([A-Z][a-z]{1,19}(?:\s+[A-Z][a-z]{1,19})?)\b',
            r'我是\S*\s+([A-Z][a-z]{1,19})\b',
        ]
        for pat in intro_patterns:
            m = re.search(pat, text)
            if m:
                return m.group(1)

        return ''

    def _token(self, prefix: str, original: str) -> str:
        for tok, val in self.vault.items():
            if val == original and tok.startswith(f'[{prefix}_'):
                return tok
        self._counter += 1
        token = f'[{prefix}_{self._counter:03d}]'
        self.vault[token] = original
        return token

    def mask_text(self, text: str, name: str, email: str,
                  english_name: str = '') -> str:
        if not text:
            return text
        
        # 1. Primary identifiers (Redacted with high priority)
        if name:
            name_token = self._token('CANDIDATE', name)
            # Create a regex that allows optional whitespace/newlines between each character of the name
            # This is crucial for Chinese names in PDFs (e.g., "陳 志 瑋")
            name_pattern = r'\s*'.join([re.escape(c) for c in name])
            text = re.sub(name_pattern, name_token, text)
            
            # Also mask 2-char suffix (given name) for names of 3+ chars.
            # Use word-boundary-like anchors to avoid false positives on short suffixes.
            if len(name) >= 3:
                suffix = name[1:]
                suffix_pattern = r'\s*'.join([re.escape(c) for c in suffix])
                # Require suffix NOT preceded by another CJK char to reduce false positives
                text = re.sub(r'(?<![\u4e00-\u9fff])' + suffix_pattern, name_token, text)

        if email:
            email_token = self._token('EMAIL', email)
            text = text.replace(email, email_token)

        if english_name:
            en_token = self._token('CANDIDATE_EN', english_name)
            # Use word boundaries for English names
            text = re.sub(
                rf'\b{re.escape(english_name)}\b',
                en_token, text, flags=re.IGNORECASE
            )

        # 2a. Hardcoded demographic patterns (不依賴規則檔解析，確保一定生效)
        # 年齡：50歲、50 歲
        text = re.sub(r'\d{1,3}\s*歲', '[AGE_REDACTED]', text)
        # 民國年次：75年次、民國75年次
        text = re.sub(r'(?:民國\s*)?\d{2,3}\s*年次', '[BIRTHYEAR_REDACTED]', text)
        # 性別：包容多元性別描述，如「[AGE_REDACTED] 男」、「多元性別」、「跨性別」
        text = re.sub(r'(\[AGE_REDACTED\])\s*(男|女|多元性別|跨性別|無性別|X)', r'\1 [GENDER_REDACTED]', text)
        # 出生年月日
        text = re.sub(r'(?:出生|生日)[：:\s]*\d{2,4}[/\-年]\d{1,2}[/\-月]\d{1,2}日?', '[BIRTHDATE_REDACTED]', text)

        # 2. Rule-based Regex
        for pattern in self.rules['regex']:
            def _replace_regex(m):
                return self._token('PII', m.group())
            try:
                # Optimized Year Redaction (Universal)
                if pattern == r'\b(19\d{2}|20\d{2})\b':
                    text = re.sub(pattern, '[YEAR_REDACTED]', text)
                    continue

                if '歲' in pattern or '年次' in pattern or '出生' in pattern:
                    label = '[DEMOGRAPHIC_REDACTED]'
                    if '歲' in pattern: label = '[AGE_REDACTED]'
                    if '年次' in pattern: label = '[BIRTHYEAR_REDACTED]'
                    text = re.sub(pattern, label, text)
                else:
                    text = re.sub(pattern, _replace_regex, text)
            except re.error:
                continue

        # 3. Bilingual Masking List
        self.detect_language(text)
        active_masking_list = self.rules['masking_list_cn'] if self.doc_language == 'CHINESE' else self.rules['masking_list_en']
        
        text_lower = text.lower()
        for word in active_masking_list:
            if word.lower() in text_lower:
                # Case-insensitive replace
                text = re.sub(re.escape(word), self._token('SENSITIVE', word), text, flags=re.IGNORECASE)
                text_lower = text.lower()

        # 4. Graduation year cleanup (year already blocked by universal year masking)
        text = re.sub(r'(\[YEAR_REDACTED\])\s*年?\s*畢業',
                      lambda m: '工作經驗已遮蔽（畢業年份已遮蔽）', text)

        return text

    def mask_profile(self, candidate: dict) -> dict:
        name = candidate.get('name', '')
        email = candidate.get('email', '')
        
        # Determine english name
        english_name = candidate.get('english_name', '')
        if not english_name:
            english_name = self._extract_english_name(
                candidate.get('coverLetter', '') + ' ' + candidate.get('jobTitle', '')
            )

        masked = dict(candidate)
        masked['name'] = self._token('CANDIDATE', name)
        masked['email'] = self._token('EMAIL', email)

        if candidate.get('coverLetter'):
            masked['coverLetter'] = self.mask_text(
                candidate['coverLetter'], name, email, english_name
            )

        if masked.get('resumes'):
            masked['resumes'] = [
                {k: v for k, v in r.items() if k not in ('downloadUrl', 'pdfUrl')}
                for r in masked['resumes']
            ]
        return masked


def pdf_redact(input_path: Path, output_path: Path, vault: dict):
    """Physically redact PDF using tokens (e.g., [CANDIDATE_001]) as text overlays."""
    if not HAS_PYMUPDF:
        return False

    # Regex-based patterns to redact directly on PDF (not via vault)
    # These produce fixed labels rather than vault tokens
    DIRECT_PATTERNS = [
        (re.compile(r'\d{1,3}\s*歲'),           '[AGE_REDACTED]'),
        (re.compile(r'(?:民國\s*)?\d{2,3}\s*年次'), '[BIRTHYEAR_REDACTED]'),
        (re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}'), '[EMAIL_REDACTED]'),
        (re.compile(r'09\d{2}[\s\-]?\d{3}[\s\-]?\d{3}'), '[PHONE_REDACTED]'),
        (re.compile(r'\b(19|20)\d{2}\b'),        '[YEAR_REDACTED]'),
    ]

    try:
        raw = fitz.open(str(input_path))
        if not raw.is_pdf:
            # HTML5 / 非 PDF 格式：先轉成真正的 PDF bytes 再操作
            print(f"[HTML5Mode] 轉換 HTML→PDF 再遮蔽: {input_path.name}", file=sys.stderr)
            pdf_bytes = raw.convert_to_pdf()
            raw.close()
            doc = fitz.open('pdf', pdf_bytes)
        else:
            doc = raw

        def _redact_areas(page, areas, label):
            for area in areas:
                page.add_redact_annot(area, text=label,
                                      fill=(0, 0, 0), text_color=(1, 1, 1), fontsize=8)

        for page in doc:
            # 1. Vault-based redaction (names, addresses, etc.)
            for token, original in vault.items():
                if not original or len(str(original)) < 2:
                    continue
                original_str = str(original)
                variants = {original_str}
                # Also try without spaces and reversed order for Chinese names
                no_space = original_str.replace(' ', '')
                variants.add(no_space)
                # If it looks like "名 姓" (given-name space surname), also try "姓名" order
                parts = original_str.split()
                if len(parts) == 2 and all(re.search(r'[\u4e00-\u9fff]', p) for p in parts):
                    variants.add(parts[1] + parts[0])  # surname + given name, no space
                    variants.add(parts[0] + parts[1])  # as-is but no space
                for variant in variants:
                    if len(variant) < 2:
                        continue
                    areas = page.search_for(variant)
                    _redact_areas(page, areas, token)

            # 2. Regex-based redaction (age, gender, email, phone, year)
            page_text = page.get_text()
            for pattern, label in DIRECT_PATTERNS:
                for m in pattern.finditer(page_text):
                    areas = page.search_for(m.group())
                    _redact_areas(page, areas, label)

            # 3. Gender — redact inclusive gender pronouns/labels appearing right after age token area
            for m in re.finditer(r'\d{1,3}\s*歲\s*(男|女|多元性別|跨性別|無性別|X)', page_text):
                areas = page.search_for(m.group(1))
                _redact_areas(page, areas, '[GENDER_REDACTED]')

            page.apply_redactions()

        doc.save(str(output_path))
        doc.close()
        return True
    except Exception as e:
        print(f"PDF Redaction error: {e}", file=sys.stderr)
        return False


def generate_project_id() -> str:
    """Generate a unique project ID: PRJ-YYYYMMDD-SHORTUUID."""
    date_str = datetime.now().strftime('%Y%m%d')
    short_id = str(uuid.uuid4())[:4].upper()
    return f"PRJ-{date_str}-{short_id}"


import argparse

# ── Single PDF processing (shared logic) ─────────────────────────────────────

def _process_single_pdf(pdf_path: Path, skill_dir: Path, masker: 'PIIMasker',
                         name: str = '', english_name: str = '', chinese_name: str = '',
                         project_id: str = '') -> dict:
    """Process one PDF and return the result dict. Also writes vault and masked PDF."""
    if not project_id:
        project_id = generate_project_id()
    if not name:
        # Fallback to filename stem
        name = pdf_path.stem.split('+')[-1]

    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    # Layer 0: Check for encryption/password before full processing
    if HAS_PYMUPDF:
        try:
            test_doc = fitz.open(str(pdf_path))
            if test_doc.needs_password:
                 test_doc.close()
                 raise PermissionError(f"PDF is encrypted/password-protected: {pdf_path.name}")
            test_doc.close()
        except Exception as e:
            if "password" in str(e).lower():
                raise PermissionError(f"PDF is encrypted: {pdf_path.name}")

    raw_text = extract_pdf_text(pdf_path)

    detected_cn_names = []
    if not chinese_name and HAS_CN_DETECTOR and raw_text:
        detected_cn_names = detect_chinese_names(raw_text, english_name)
        if detected_cn_names:
            print(f"[AutoDetect] Chinese names found: {detected_cn_names}", file=sys.stderr)

    candidate = {'id': pdf_path.stem, 'name': name, 'english_name': english_name, 'chinese_name': chinese_name}
    masked_profile = masker.mask_profile(candidate)

    masked_text = masker.mask_text(raw_text, name, '', english_name)
    if chinese_name:
        masked_text = masker.mask_text(masked_text, chinese_name, '', '')
    for cn in detected_cn_names:
        masked_text = masker.mask_text(masked_text, cn, '', '')

    result = {
        'candidate_id': pdf_path.stem,
        'project_id': project_id,
        'masked_profile': masked_profile,
        'resume_text': masked_text,
        'pii_fields': list(masker.vault.keys()),
    }

    masked_pdf_path = skill_dir / 'masked' / f"audit_ready_{pdf_path.name}"
    if pdf_redact(pdf_path, masked_pdf_path, masker.vault):
        result['masked_pdf_file'] = str(masked_pdf_path)

    vault_path = skill_dir / 'masked' / f"vault_{pdf_path.stem}.json"
    vault_data = {
        'metadata': {
            'project_id': project_id,
            'timestamp': datetime.now().isoformat(),
            'source_file': pdf_path.name
        },
        'vault': masker.vault
    }
    with open(vault_path, 'w', encoding='utf-8') as f:
        json.dump(vault_data, f, ensure_ascii=False, indent=2)

    return result


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='AnonyHire — PII Masking & Redaction Tool')
    
    # Subcommands or Grouping
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--pdf', type=str, help='Path to a single PDF resume')
    group.add_argument('--batch', type=str, help='Path to a directory containing multiple PDF resumes')
    group.add_argument('legacy_cid', nargs='?', help=argparse.SUPPRESS) # candidate_id
    group.add_argument('legacy_path', nargs='?', help=argparse.SUPPRESS) # project_path

    parser.add_argument('--name', type=str, help='Primary candidate name (for masking)')
    parser.add_argument('--ename', type=str, help='English name')
    parser.add_argument('--cname', type=str, help='Additional Chinese name')
    parser.add_argument('--project-id', type=str, help='Optional Project ID')

    args = parser.parse_args()

    skill_dir = Path(__file__).parent.parent
    rules_path = skill_dir / 'rules' / 'masking_rules.md'

    # 1. Batch Mode
    if args.batch:
        batch_dir = Path(args.batch)
        if not batch_dir.is_dir():
            print(f"[Error] Not a directory: {batch_dir}", file=sys.stderr)
            sys.exit(1)
        pdfs = sorted(batch_dir.glob('*.pdf'))
        if not pdfs:
            print(f"[Info] No PDF files found in {batch_dir}", file=sys.stderr)
            sys.exit(0)
        
        print(f"[Batch] Processing {len(pdfs)} files...", file=sys.stderr)
        results = []
        for pdf_path in pdfs:
            masker = PIIMasker(rules_path)
            try:
                result = _process_single_pdf(pdf_path, skill_dir, masker)
                results.append({'file': pdf_path.name, 'status': 'ok', 'candidate_id': result['candidate_id']})
                print(f"[Batch] ✓ {pdf_path.name}", file=sys.stderr)
            except Exception as e:
                results.append({'file': pdf_path.name, 'status': 'error', 'error': str(e)})
                print(f"[Batch] ✗ {pdf_path.name}: {e}", file=sys.stderr)
        
        sys.stdout.buffer.write(json.dumps(results, ensure_ascii=False, indent=2).encode('utf-8'))
        sys.stdout.buffer.write(b'\n')
        return

    # 2. Single PDF Mode
    if args.pdf:
        pdf_path = Path(args.pdf)
        masker = PIIMasker(rules_path)
        try:
            result = _process_single_pdf(
                pdf_path, skill_dir, masker, 
                name=args.name or '', 
                english_name=args.ename or '', 
                chinese_name=args.cname or '', 
                project_id=args.project_id or ''
            )
            sys.stdout.buffer.write(json.dumps(result, ensure_ascii=False, indent=2).encode('utf-8'))
            sys.stdout.buffer.write(b'\n')
        except Exception as e:
            print(f"[Error] {e}", file=sys.stderr)
            sys.exit(1)
        return

    # 3. Legacy Cache Mode (Positionals)
    # Check sys.argv directly for positional logic to avoid argparse confusion with 2 positionals
    if len(sys.argv) >= 3 and not sys.argv[1].startswith('-'):
        candidate_id = sys.argv[1]
        project_path = Path(sys.argv[2])
        cache_file = project_path / 'cache' / 'candidates_latest.json'

        if not cache_file.exists():
            print(f"[Error] Cache file missing at {cache_file}", file=sys.stderr)
            sys.exit(1)

        masker = PIIMasker(rules_path)
        with open(cache_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        candidate = next((c for c in data['candidates'] if str(c['id']) == candidate_id), None)
        if not candidate:
            print(f"[Error] Candidate {candidate_id} not found in cache", file=sys.stderr)
            sys.exit(1)

        masked_profile = masker.mask_profile(candidate)
        resume_dir = project_path / 'cache' / 'resumes' / str(candidate_id)
        raw_text = ""
        original_pdf = None
        for pdf in resume_dir.glob('*.pdf'):
            original_pdf = pdf
            try:
                raw_text = extract_pdf_text(pdf)
            except Exception as e:
                print(f"[Error] PDF extraction failed: {e}", file=sys.stderr)
            break
        
        masked_text = masker.mask_text(raw_text, candidate['name'], candidate.get('email', ''), '')
        result = {
            'candidate_id': candidate_id,
            'masked_profile': masked_profile,
            'resume_text': masked_text,
            'pii_fields': list(masker.vault.keys()),
        }

        if original_pdf:
            masked_pdf_path = skill_dir / 'masked' / f"audit_ready_{candidate_id}.pdf"
            if pdf_redact(original_pdf, masked_pdf_path, masker.vault):
                result['masked_pdf_file'] = str(masked_pdf_path)

        vault_path = skill_dir / 'masked' / f"vault_{candidate_id}.json"
        with open(vault_path, 'w', encoding='utf-8') as f:
            json.dump(masker.vault, f, ensure_ascii=False, indent=2)

        sys.stdout.buffer.write(json.dumps(result, ensure_ascii=False, indent=2).encode('utf-8'))
        sys.stdout.buffer.write(b'\n')
        return

    parser.print_help()


if __name__ == '__main__':
    main()
