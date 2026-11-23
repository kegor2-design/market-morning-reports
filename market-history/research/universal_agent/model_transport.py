"""Single text-only Responses request with a separately reviewed host permit."""
import hashlib
import json
import os
import re
import subprocess
import tempfile
from datetime import datetime, timezone

from .engine import canonical

MODEL = 'gpt-5-mini-2025-08-07'
MAX_INPUT_BYTES = 32000
OUTPUT_TOKENS = 4096


def prepare(prompt, schema, directory, purpose, goal_id, seconds):
    message = prompt + '\nReturn JSON matching this schema:\n' + schema.read_text()
    if len(message.encode()) > MAX_INPUT_BYTES:
        raise ValueError('Model input exceeds reviewed byte budget')
    body = canonical({'model': MODEL, 'input': message, 'store': False,
                      'max_output_tokens': OUTPUT_TOKENS, 'tools': [],
                      'text': {'format': {'type': 'json_object'}}})
    scope = {'provider': 'OPENAI_RESPONSES', 'model': MODEL, 'goal_id': goal_id,
             'purpose': purpose, 'state_directory': str(directory.resolve()),
             'body_sha256': hashlib.sha256(body).hexdigest(), 'max_calls': 1,
             'max_seconds': seconds, 'input_bytes': len(message.encode()),
             'max_output_tokens': OUTPUT_TOKENS}
    return body, scope


def authorized(scope, approval):
    if not approval or any(approval.get(k) != v for k, v in scope.items()):
        return False
    try:
        expires = datetime.fromisoformat(approval['expires_at_utc'])
        valid = expires.tzinfo is not None and expires > datetime.now(timezone.utc)
    except (KeyError, ValueError, TypeError):
        return False
    project = os.environ.get('OPENAI_PROJECT_ID', '')
    # Conservative byte-based estimate for the pinned model, including an
    # allowance for framing. The operator separately accepts billing variance.
    estimate = ((scope['input_bytes'] + 256) * 0.25 + OUTPUT_TOKENS * 2) / 1_000_000
    return (approval.get('max_cost_usd', 0) >= estimate and valid and approval.get('status') == 'APPROVED'
            and approval.get('accept_billing_overrun') is True
            and re.fullmatch(r'proj_[a-zA-Z0-9_-]+', project) is not None
            and approval.get('project') == project
            and re.fullmatch(r'[A-Za-z0-9_.-]+', os.getenv('OPENAI_API_KEY', '')) is not None)


def exchange(body, directory, seconds):
    # Curl reads credentials only from stdin. No curlrc, redirects, proxy,
    # tools or automatic retries. Killing the client cannot cancel remote billing.
    headers = ('Authorization: Bearer ' + os.environ['OPENAI_API_KEY'] +
               '\nOpenAI-Project: ' + os.environ['OPENAI_PROJECT_ID'] +
               '\nContent-Type: application/json\n')
    with tempfile.NamedTemporaryFile(dir=directory) as stream:
        stream.write(body)
        stream.flush()
        result = subprocess.run(['/usr/bin/curl', '--disable', '--silent', '--fail',
            '--noproxy', '*', '--proto', '=https', '--max-filesize', '131072',
            '--max-time', str(seconds), '--header', '@-', '--data-binary', '@' + stream.name,
            'https://api.openai.com/v1/responses'], input=headers.encode(),
            capture_output=True, timeout=seconds, env={'PATH': '/usr/bin:/bin'})
    if result.returncode or len(result.stdout) > 131072:
        raise RuntimeError('Model transport outcome uncertain')
    response = json.loads(result.stdout)
    if response.get('status') != 'completed' or response.get('model') != MODEL:
        raise ValueError('Model identity or completion status changed')
    parts = [part for item in response['output'] if item['type'] == 'message'
             for part in item['content']]
    if len(parts) != 1 or parts[0].get('type') != 'output_text':
        raise ValueError('Model did not return one text proposal')
    output = parts[0]['text'].encode()
    if len(output) > 64000:
        raise ValueError('Model candidate too large')
    usage = {k: response['usage'][k] for k in ('input_tokens', 'output_tokens')}
    if any(type(x) is not int or x < 0 for x in usage.values()) or usage['output_tokens'] > OUTPUT_TOKENS:
        raise ValueError('Model usage outside reviewed contract')
    return output, usage
