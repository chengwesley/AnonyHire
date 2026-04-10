#!/usr/bin/env python3
import json
import re
import sys
from pathlib import Path

def load_vault(vault_path: Path):
    if not vault_path.exists(): return {}
    with open(vault_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        return data.get('vault', data)  # fallback to old structure if metadata missing

def run_privacy_audit(report_text, vault):
    leaks = []
    for token, original in vault.items():
        if not original or len(str(original)) < 2: continue
        if re.search(re.escape(str(original)), report_text, re.IGNORECASE):
            leaks.append({'token': token, 'value': original})
    return leaks

def main():
    if len(sys.argv) < 3: sys.exit(1)
    
    candidate_id = sys.argv[1]
    report_path = Path(sys.argv[2])
    skill_dir = Path(__file__).parent.parent
    vault_path = skill_dir / 'masked' / f"vault_{candidate_id}.json"
    
    report_text = report_path.read_text(encoding='utf-8')
    vault = load_vault(vault_path)
    leaks = run_privacy_audit(report_text, vault)
    
    result = {
        'agent': 'PrivacyAuditAgent',
        'status': 'FAIL' if leaks else 'PASS',
        'leaks': leaks
    }
    print(json.dumps(result))

if __name__ == '__main__':
    main()
