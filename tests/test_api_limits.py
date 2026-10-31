"""No network or real sleeps: shared budgets and gh header/error handling."""
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import github_api as api


class LimitsTests(unittest.TestCase):
    def setUp(self):
        api._COOLDOWNS.clear()
        api._LAST_SEARCH = None

    def tearDown(self):
        self.setUp()

    def test_gh_parses_headers_on_nonzero_exit_and_redirect(self):
        response = 'HTTP/1.1 301 Moved\r\nLocation: /next\r\n\r\nHTTP/2.0 403 Forbidden\r\nRetry-After: 7\r\nX-RateLimit-Remaining: 0\r\n\r\n{"message":"rate limited"}'
        with patch.object(api, 'gh_available', return_value=True), patch.object(api.subprocess, 'run', return_value=SimpleNamespace(stdout=response, stderr='gh: forbidden', returncode=1)) as run:
            status, headers, body = api._gh_http('/search/repositories', {}, 25, 'GET', None)
        self.assertEqual(status, 403)
        self.assertEqual(headers['retry-after'], '7')
        self.assertEqual(json.loads(body)['message'], 'rate limited')
        self.assertIn('--include', run.call_args.args[0])

    def test_gh_retry_after_uses_common_policy_without_rest_fallback(self):
        with patch.object(api, '_gh_http', side_effect=[(403, {'retry-after':'4'}, '{"message":"secondary rate limit"}'), (200, {}, '{}')]) as gh, patch.object(api, '_http') as rest, patch.object(api.time, 'sleep') as sleep:
            self.assertEqual(api.fetch_json('/test', provider='gh'), {})
        self.assertEqual(gh.call_count, 2)
        sleep.assert_called_once_with(4)
        rest.assert_not_called()

    def test_long_primary_cooldown_skips_later_search_but_allows_core(self):
        with patch.object(api.time, 'time', return_value=100), patch.object(api.time, 'sleep') as sleep, patch.object(api, '_http', return_value=(403, {'x-ratelimit-remaining':'0','x-ratelimit-reset':'500'}, '{"message":"API rate limit exceeded"}')) as http:
            with self.assertRaises(api.GitHubAPIError):
                api.fetch_json('/search/repositories', provider='api')
            with self.assertRaises(api.GitHubAPIError) as raised:
                api.fetch_json('/search/repositories', provider='api')
            self.assertEqual(http.call_count, 1)
            self.assertGreater(raised.exception.details['retry_after_seconds'], 60)
            sleep.assert_not_called()
            http.return_value = (200, {}, '{}')
            self.assertEqual(api.fetch_json('/repos/owner/repo', provider='api'), {})

    def test_secondary_cooldown_blocks_other_resources(self):
        with patch.object(api.time, 'time', return_value=100), patch.object(api, '_gh_http', return_value=(429, {'retry-after':'120'}, '{}')) as gh:
            with self.assertRaises(api.GitHubAPIError):
                api.fetch_json('/search/repositories', provider='gh')
            with self.assertRaises(api.GitHubAPIError):
                api.fetch_json('/repos/owner/repo', provider='gh')
            self.assertEqual(gh.call_count, 1)

    def test_success_with_exhausted_budget_prevents_next_request(self):
        with patch.object(api.time, 'time', return_value=100), patch.object(api, '_http', return_value=(200, {'X-RateLimit-Remaining':'0','X-RateLimit-Reset':'500'}, '{}')) as http:
            self.assertEqual(api.fetch_json('/search/repositories', provider='api'), {})
            with self.assertRaises(api.GitHubAPIError):
                api.fetch_json('/search/repositories', provider='api')
            self.assertEqual(http.call_count, 1)

    def test_shared_search_pacing_across_transports(self):
        with patch.object(api.time, 'monotonic', return_value=0), patch.object(api.time, 'sleep') as sleep, patch.object(api, '_http', return_value=(200, {}, '{}')), patch.object(api, '_gh_http', return_value=(200, {}, '{}')):
            api.fetch_json('/search/repositories', token='fixture', provider='api')
            api.fetch_json('/search/repositories', provider='gh')
            sleep.assert_called_once_with(3.1)

    def test_permissions_error_does_not_retry_and_mutation_not_replayed(self):
        with patch.object(api, '_gh_http', return_value=(403, {}, '{"message":"Resource not accessible"}')) as gh:
            with self.assertRaises(api.GitHubAPIError):
                api.fetch_json('/test', provider='gh')
            self.assertEqual(gh.call_count, 1)
        with patch.object(api, '_http', return_value=(503, {}, '{}')) as http:
            with self.assertRaises(api.GitHubAPIError):
                api.fetch_json('/test', provider='api', method='PATCH', body={})
            self.assertEqual(http.call_count, 1)

    def test_http_date_retry_after_and_bounded_repeated_failures(self):
        with patch.object(api, '_http', return_value=(429, {'Retry-After':'Thu, 01 Jan 2099 00:00:00 GMT'}, '{}')) as http:
            with self.assertRaises(api.GitHubAPIError):
                api.fetch_json('/test', provider='api')
            self.assertEqual(http.call_count, 1)
