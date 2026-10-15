import json
from pathlib import Path

PIPELINE = Path(__file__).with_name('client-hunter-pipeline.json')

def readiness(path=PIPELINE):
    data = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    blockers = []
    if not data.get('sender_address_verified'):
        blockers.append('Business postal address not verified')
    seen = set()
    for item in data['leads']:
        key = (item.get('domain'), item.get('public_contact'))
        if key in seen:
            blockers.append('Duplicate prospect: ' + item['id'])
        seen.add(key)
        if not item.get('recipient_approved'):
            blockers.append('Recipient-specific outreach approval missing: ' + item['id'])
        if not item.get('opt_out_checked') or item.get('opted_out'):
            blockers.append('Opt-out status not cleared: ' + item['id'])
        if item['status'] == 'SENT' and not item.get('sent_provider_message_id'):
            blockers.append('Missing provider send receipt: ' + item['id'])
        if item['status'] == 'PAID' and not item.get('verified_payment_provider_event'):
            blockers.append('Missing verified payment event: ' + item['id'])
    return {'ready_for_outreach': not blockers, 'blockers': blockers,
            'drafts': sum(x['status'] == 'DRAFTED' for x in data['leads']),
            'verified_sent': sum(bool(x.get('sent_provider_message_id')) for x in data['leads']),
            'verified_payments': sum(bool(x.get('verified_payment_provider_event')) for x in data['leads'])}

if __name__ == '__main__':
    print(json.dumps(readiness(), indent=2))
