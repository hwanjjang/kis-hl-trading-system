from __future__ import annotations

import contextlib
import io
import json
import unittest
from unittest.mock import patch

from kis_hl.cli import main
from kis_hl.kis.client import KisHttpResponse
from tests.test_kis_client import RecordingKisClient


class KisAccountTests(unittest.TestCase):
    def invoke(self, response=None, error=None, config=None):
        config = config or RecordingKisClient().config
        out, err = io.StringIO(), io.StringIO()
        with patch('kis_hl.cli.load_env_file'), patch('kis_hl.cli.configure_logging'), \
             patch('kis_hl.cli.load_kis_config', return_value=config), \
             patch('kis_hl.cli.KisClient') as factory, \
             contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            factory.return_value.inquire_domestic_balance.return_value = response
            factory.return_value.inquire_domestic_balance.side_effect = error
            code = main(['kis-account'])
        return code, out.getvalue(), err.getvalue(), factory.call_args.args[0]

    def test_summary_is_whitelisted_and_account_masked(self):
        summary = {'dnca_tot_amt': '437', 'tot_evlu_amt': '329452', 'scts_evlu_amt': '0'}
        for raw in [summary, [summary]]:
            code, out, err, _ = self.invoke(KisHttpResponse(200, {
                'rt_cd': '0', 'output2': raw,
                'output1': [{'private': 'secret'}], 'msg1': 'token private',
            }, {}))
            self.assertEqual(code, 0, err)
            self.assertEqual(json.loads(out), {
                'mode': 'sim', 'account': '******7801', 'currency': 'KRW',
                'domestic_summary': summary,
            })
            self.assertNotIn('12345678', out + err)
            self.assertNotIn('secret', out + err)

    def test_failures_are_nonzero_without_raw_vendor_data(self):
        responses = [
            KisHttpResponse(500, {'msg1': 'secret'}, {}),
            KisHttpResponse(200, {'rt_cd': '1', 'msg1': 'secret'}, {}),
            KisHttpResponse(200, {'rt_cd': '0', 'output2': []}, {}),
            KisHttpResponse(200, {'rt_cd': '0', 'output2': [{}]}, {}),
            KisHttpResponse(200, {'rt_cd': '0', 'output2': {
                'dnca_tot_amt': 'NaN', 'tot_evlu_amt': '0', 'scts_evlu_amt': '0'}}, {}),
        ]
        for response in responses:
            code, out, err, _ = self.invoke(response)
            self.assertEqual(code, 1)
            self.assertEqual(out, '')
            self.assertNotIn('secret', err)
        code, out, err, _ = self.invoke(error=RuntimeError('secret 12345678 token'))
        self.assertEqual(code, 1)
        self.assertNotIn('secret', err)
        self.assertNotIn('12345678', err)

    def test_client_receives_unmodified_config(self):
        # Credential-scoped token caching lives in KisClient, so every command
        # must pass the loaded config through untouched to share one cache.
        config = RecordingKisClient().config
        _, _, _, passed = self.invoke(error=RuntimeError('network unavailable'), config=config)
        self.assertEqual(passed.token_dir, config.token_dir)


if __name__ == '__main__':
    unittest.main()
