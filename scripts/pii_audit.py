#!/usr/bin/env python3
"""
Audit Coordinator — AnonyHire
Triggers specialized agents (Privacy & Fairness) and merges results.
"""
import json
import sys
import subprocess
from pathlib import Path
from datetime import datetime
import shutil
from report_templates import CANDIDATE_CERTIFICATE_TEMPLATE

def generate_candidate_certificate(skill_dir, pid, cid, tool, timestamp, privacy_data, fairness_data, report_text):
    """Generate a professional MD certificate for the candidate."""
    project_dir = skill_dir / 'reports' / 'projects' / pid / cid
    project_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. Save original report snapshot
    (project_dir / 'analysis_original.txt').write_text(report_text, encoding='utf-8')
    
    # 2. Map data to template
    p_status = privacy_data.get('status', 'ERROR')
    f_status = fairness_data.get('status', 'ERROR')
    
    status_badge = ""
    if p_status == 'FAIL' or f_status == 'FAIL':
        status_badge = "## 🔴 狀態：不合規 (NON-COMPLIANT)"
    elif f_status == 'WARN':
        status_badge = "## 🟡 狀態：需人工審核 (MANUAL REVIEW REQUIRED)"
    else:
        status_badge = "## 🟢 狀態：合規 (COMPLIANT)"
        
    privacy_leaks_list = ""
    for leak in privacy_data.get('leaks', []):
        privacy_leaks_list += f"- `[{leak['token']}]` -> `{leak['value']}`\n"
    if not privacy_leaks_list: privacy_leaks_list = "未偵測到個資洩漏。"
    
    fairness_flags_list = ""
    all_flags = fairness_data.get('fail_flags', []) + fairness_data.get('warn_flags', [])
    for flag in all_flags:
        fairness_flags_list += f"- `{flag}`\n"
    if not fairness_flags_list: fairness_flags_list = "未偵測到公平性疑慮。"

    cert_content = CANDIDATE_CERTIFICATE_TEMPLATE.format(
        candidate_id=cid,
        project_id=pid,
        tool=tool,
        timestamp=timestamp,
        status_badge=status_badge,
        privacy_status="🔴 FAIL" if p_status == 'FAIL' else "🟢 PASS",
        privacy_detail="偵測到個資洩漏" if p_status == 'FAIL' else "無洩漏",
        fairness_status="🔴 FAIL" if f_status == 'FAIL' else ("🟡 WARN" if f_status == 'WARN' else "🟢 PASS"),
        fairness_detail="偵測到偏見關鍵字" if f_status == 'FAIL' else ("疑似代理偏見" if f_status == 'WARN' else "無偏見"),
        privacy_leaks_list=privacy_leaks_list.strip(),
        fairness_flags_list=fairness_flags_list.strip()
    )
    
    (project_dir / 'CERTIFICATE.md').write_text(cert_content, encoding='utf-8')
    return project_dir / 'CERTIFICATE.md'


import argparse

def main():
    parser = argparse.ArgumentParser(description='AnonyHire Audit Coordinator')
    parser.add_argument('candidate_id', help='The ID of the candidate being audited')
    parser.add_argument('report_path', help='Path to the AI-generated analysis report (txt)')
    parser.add_argument('--tool', default='Unknown', help='Name of the recruitment tool used')
    parser.add_argument('--project-id', default='Unknown', help='Override project ID (defaults to folder-based lookup)')
    
    args = parser.parse_args()

    candidate_id = args.candidate_id
    report_path = Path(args.report_path)
    skill_dir = Path(__file__).parent.parent
    
    tool_name = args.tool
    project_id = args.project_id
    
    if not report_path.exists():
        print(f"[Error] Report file not found: {report_path}", file=sys.stderr)
        sys.exit(1)

    # 0. Try to recover Project ID from vault if not provided
    vault_path = skill_dir / 'masked' / f"vault_{candidate_id}.json"
    if project_id == "Unknown" and vault_path.exists():
        try:
            with open(vault_path, 'r', encoding='utf-8') as f:
                vault_data = json.load(f)
                project_id = vault_data.get('metadata', {}).get('project_id', "Unknown")
        except:
            pass

    # 1. Run Privacy Agent
    privacy_res = subprocess.run(
        [sys.executable, str(skill_dir / 'scripts' / 'privacy_audit.py'), candidate_id, str(report_path)],
        capture_output=True, text=True, encoding='utf-8'
    )
    privacy_data = json.loads(privacy_res.stdout) if privacy_res.stdout else {'status': 'ERROR'}

    # 2. Run Fairness Agent
    fairness_res = subprocess.run(
        [sys.executable, str(skill_dir / 'scripts' / 'fairness_audit.py'), candidate_id, str(report_path)],
        capture_output=True, text=True, encoding='utf-8'
    )
    fairness_data = json.loads(fairness_res.stdout) if fairness_res.stdout else {'status': 'ERROR'}

    # 3. Determine combined status
    privacy_status = privacy_data.get('status', 'ERROR')
    fairness_status = fairness_data.get('status', 'ERROR')
    needs_review = privacy_status == 'FAIL' or fairness_status in ('WARN', 'FAIL') or \
                   privacy_status == 'ERROR' or fairness_status == 'ERROR'

    # 4. Generate Professional Certificate
    report_text = report_path.read_text(encoding='utf-8')
    cert_path = generate_candidate_certificate(
        skill_dir, project_id, candidate_id, tool_name, 
        datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        privacy_data, fairness_data, report_text
    )

    # 5. Append to central violations log
    log_path = skill_dir / 'reports' / 'violations_log.json'
    all_violations = []
    if log_path.exists():
        try:
            with open(log_path, 'r', encoding='utf-8') as f:
                all_violations = json.load(f)
        except:
            pass

    all_violations.append({
        'candidate_id': candidate_id,
        'project_id': project_id,
        'recruitment_tool': tool_name,
        'timestamp': datetime.now().isoformat(),
        'privacy': privacy_data,
        'fairness': fairness_data,
        'needs_review': needs_review,
    })
    
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, 'w', encoding='utf-8') as f:
        json.dump(all_violations, f, ensure_ascii=False, indent=2)

    print(f"Audit completed for: {candidate_id} | Project: {project_id} | Tool: {tool_name} | needs_review={needs_review}")

if __name__ == '__main__':
    main()
