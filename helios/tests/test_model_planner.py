"""Endpoint contract and fallback regression tests; no external service required."""
import io
import json
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from helios import llm

QUESTION = 'What percentage has diabetes?'
RAW = dict(intent='metric_query', metric_id='diabetes',
           filters={}, breakdown=None, reasoning='Published diabetes estimate.')


class ModelPlannerTests(unittest.TestCase):
    def response(self, raw=RAW):
        return io.BytesIO(json.dumps({
            'choices': [{'message': {'content': json.dumps(raw)}}],
            'usage': {'prompt_tokens': 12, 'completion_tokens': 8},
        }).encode())

    def planner(self):
        return llm.ModelPlanner(model='test-model',
                                endpoint='https://model.example/chat', api_key='test-key')

    @patch.dict(os.environ, {}, clear=True)
    def test_default_and_missing_configuration(self):
        self.assertIsInstance(llm.get_planner(), llm.DeterministicPlanner)
        with patch('urllib.request.urlopen') as call:
            plan = llm.get_planner('model').plan(QUESTION)
        call.assert_not_called()
        self.assertEqual(plan['metric_id'], RAW['metric_id'])
        self.assertIn('unavailable', plan['planner'])
        self.assertTrue(plan['validation_errors'])

    def test_success_contract_and_usage(self):
        with patch('urllib.request.urlopen', return_value=self.response()) as call:
            plan = self.planner().plan(QUESTION)
        request = call.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(request.get_header('Authorization'), 'Bearer test-key')
        self.assertEqual(payload['response_format']['json_schema']['schema'], llm.PLAN_SCHEMA)
        self.assertEqual(payload['messages'][0]['content'], llm.SYSTEM)
        self.assertIn(QUESTION, payload['messages'][1]['content'])
        self.assertEqual(plan['planner'], 'model')
        self.assertEqual(plan['usage'], {'input_tokens': 12, 'output_tokens': 8})
        self.assertEqual(plan['metric_id'], RAW['metric_id'])

    def test_failure_and_malformed_response_fall_back(self):
        for response in [TimeoutError('private-endpoint-secret'),
                         io.BytesIO(b'not json'), io.BytesIO(b'{}')]:
            kwargs = {'side_effect': response} if isinstance(response, Exception) else {'return_value': response}
            with self.subTest(response=type(response).__name__), patch('urllib.request.urlopen', **kwargs):
                plan = self.planner().plan(QUESTION)
                self.assertEqual(plan['metric_id'], RAW['metric_id'])
                self.assertIn('error', plan['planner'])
                self.assertNotIn('private-endpoint-secret', str(plan))

    def test_ungoverned_model_output_is_sanitised(self):
        raw = dict(RAW, metric_id='M99_exfiltrate', filters={'ssn': ['123']}, breakdown='patient_id')
        with patch('urllib.request.urlopen', return_value=self.response(raw)):
            plan = self.planner().plan(QUESTION)
        self.assertEqual(plan['intent'], 'out_of_scope')
        self.assertEqual(plan['filters'], {})
        self.assertIsNone(plan['breakdown'])
        self.assertEqual(len(plan['validation_errors']), 3)

    @patch.dict(os.environ, {'HELIOS_PLANNER': 'model', 'HELIOS_MODEL': 'configured',
                             'HELIOS_MODEL_ENDPOINT': 'https://model.example/chat'}, clear=True)
    def test_environment_and_optional_auth(self):
        planner = llm.get_planner()
        self.assertEqual(planner.model, 'configured')
        with patch('urllib.request.urlopen', return_value=self.response()) as call:
            planner.plan(QUESTION)
        self.assertIsNone(call.call_args.args[0].get_header('Authorization'))

    def test_unknown_planner_is_reported(self):
        with self.assertRaises(ValueError):
            llm.get_planner('typo')


if __name__ == '__main__':
    unittest.main()
