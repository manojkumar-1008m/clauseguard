from fastapi.testclient import TestClient
from clauseguard.backend.main import app
client = TestClient(app)
questions = [
    'hi',
    'why am I seeing this?',
    'what evidence did you find?',
    'what are the consequences i can able to face',
    'what could happen to me?',
    'how much could this cost me?',
    'what should I check?',
    'is this definitely a dark pattern?',
    'tell me everything',
    'what is social proof?'
]
payload_template = {
    'page_id': 'page-a',
    'journey_id': 'journey-a',
    'route': '/product',
    'risk_level': 'POTENTIAL',
    'risk_score': 3.4,
    'gate_decision': 'POTENTIAL',
    'actionable': False,
    'requires_context': True,
    'risk_detected': True,
    'primary_pattern': 'social_proof',
    'evidence': [
        {'evidence_id': 'E10', 'source': 'text', 'type': 'social_proof', 'pattern': 'social_proof', 'description': 'Trending Now', 'strength': 'moderate'},
        {'evidence_id': 'E11', 'source': 'price', 'type': 'displayed_price', 'description': 'Displayed price is ₹149', 'value': 149, 'currency': '₹', 'strength': 'strong'},
    ],
    'consequences': ['May create a false sense of consensus and influence the purchase decision.'],
    'recommended_action': 'Evaluate the product independently and check the actual terms before buying.',
}
for q in questions:
    payload = {'request_id': 'qa-' + q[:8], 'question': q, 'context': payload_template, 'current_page_id': 'page-a', 'current_journey_id': 'journey-a'}
    r = client.post('/ask', json=payload)
    body = r.json()
    print('QUESTION:	' + q)
    print('STATUS:	' + str(r.status_code))
    print('INTENT:	' + str(body.get('intent')))
    print('ANSWER:	' + str(body.get('answer')))
    print('---')
