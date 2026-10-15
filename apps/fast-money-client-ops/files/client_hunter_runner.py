"""Client Hunter dry-run executor. No external side effects or sales state mutations."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
try:
    from .client_hunter_readiness import PIPELINE, readiness
except ImportError:
    from client_hunter_readiness import PIPELINE, readiness

REPORT = Path(__file__).with_name('client-hunter-latest-run.json')

def run_cycle(path=PIPELINE):
    data = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    status = readiness(path)
    items = []
    for lead in data['leads']:
        contact = lead.get('public_contact', '').strip()
        source = lead.get('public_source', '').strip()
        draft = lead.get('outlook_draft', '').strip()
        blockers = []
        if not source.startswith('https://'):
            blockers.append('missing secure evidence source')
        if not contact or '@' not in contact:
            blockers.append('missing public business contact')
        if not draft:
            blockers.append('no provider draft reference')
        if not lead.get('recipient_approved'):
            blockers.append('recipient not approved')
        if not lead.get('opt_out_checked') or lead.get('opted_out'):
            blockers.append('suppression not cleared')
        if not data.get('sender_address_verified'):
            blockers.append('sender mailing address unverified')
        items.append({'lead_id':lead['id'],'company':lead['company'],
                      'recommended_action':'REVIEW_DRAFT' if source and contact and draft else 'RESEARCH',
                      'send_allowed':False,'blockers':blockers,
                      'evidence_digest':hashlib.sha256((source+'|'+contact+'|'+draft).encode()).hexdigest()[:16]})
    return {'run_utc':datetime.now(timezone.utc).isoformat(), 'mode':'DRY_RUN_NO_SEND',
            'summary':status, 'actions':items, 'external_messages_sent':0,
            'actual_revenue_collected_usd':0}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--report',default=str(REPORT))
    args=ap.parse_args()
    result=run_cycle()
    Path(args.report).write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({'mode':result['mode'],'processed':len(result['actions']),
                      'ready_for_outreach':result['summary']['ready_for_outreach'],
                      'report':args.report},indent=2))
if __name__=='__main__': main()

