import hashlib
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from universal_agent import model_transport
from universal_agent.ai_research_planner import propose_design
from universal_agent.isolated_codex import PRIVATE_ROOT
from universal_agent.research_planner import plan_goal
from universal_agent.research_runtime import plan_with_model
from test_ai_research_planner import GOAL, candidate_for


class ModelDesignTests(unittest.TestCase):
    def test_one_shot_transport_to_queue_and_missing_capabilities(self):
        PRIVATE_ROOT.mkdir(exist_ok=True)
        for supported in (True, False):
            with self.subTest(supported=supported), tempfile.TemporaryDirectory(dir=PRIVATE_ROOT) as tmp:
                goal = GOAL if supported else 'Evaluate hourly rainfall against municipal flood damage.'
                goal_id = 'research_' + hashlib.sha256(goal.encode()).hexdigest()[:12]
                candidate = candidate_for(goal) if supported else None
                design = dict(goal_id=goal_id, interpretation=goal, holdout_plan='sealed future window',
                    pit_requirements='first access evidence', resource_estimate='bounded',
                    stopping_condition='missing data', validation_metrics=['accuracy'],
                    hypotheses=[candidate['hypothesis']] if supported else ['flood damage rises'],
                    source_candidates=candidate['allowed_sources'] if supported else ['weather office'],
                    methods=candidate['evaluation_methods'] if supported else ['time split'],
                    required_data=candidate['data_requirements'] if supported else ['hourly rainfall'],
                    target_variables=[plan_goal(goal)['goal_contract']['target']] if supported else ['damage'],
                    missing_capabilities=[] if supported else ['municipal loss adapter'],
                    executable_candidate=candidate)
                queue = Path(tmp)
                scope = plan_with_model(goal, queue, approval={'status':'PREFLIGHT'})['required_scope']
                permit = dict(scope, project='proj_trial', status='APPROVED', max_cost_usd=0.05,
                    expires_at_utc=(datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat(),
                    accept_billing_overrun=True)
                with patch.dict(os.environ, OPENAI_PROJECT_ID='proj_trial', OPENAI_API_KEY='test'), \
                        patch.object(model_transport, 'exchange', return_value=(
                            json.dumps(design).encode(), {'input_tokens': 100, 'output_tokens': 200})) as exchange:
                    for invalid in (dict(permit, body_sha256='0'*64), dict(permit, accept_billing_overrun=False),
                                    dict(permit, expires_at_utc='2000-01-01T00:00:00+00:00'),
                                    dict(permit, max_cost_usd=0.00001)):
                        self.assertEqual(plan_with_model(goal, queue, approval=invalid)['status'], 'APPROVAL_REQUIRED')
                    self.assertFalse(exchange.called)
                    for _ in range(2):
                        result = plan_with_model(goal, queue, approval=permit)
                        self.assertEqual(result['status'], 'PENDING' if supported else 'BLOCKED_MISSING_CAPABILITIES')
                    exchange.assert_called_once()
                    self.assertEqual((queue/'state.json').exists(), supported)
