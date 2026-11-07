"""Mocked orchestration only: no VM or live packet acceptance."""
import signal
import subprocess
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
import demo


class LifecycleTests(unittest.TestCase):
    def exercise(self, event=None, code=None, timeout=False, bad_path=False):
        handlers = {}
        operations = []
        stage = '/tmp/udp-router-demo-stage.Abc123def456'
        def install(sig, handler):
            old = handlers.get(sig, signal.SIG_DFL)
            handlers[sig] = handler
            return old
        def run(*args, **kwargs):
            operations.append(args)
            if args[0] == 'stop':
                self.assertEqual(handlers[signal.SIGINT], signal.SIG_IGN)
                self.assertEqual(handlers[signal.SIGTERM], signal.SIG_IGN)
            return SimpleNamespace(stdout='/tmp/unrelated' if bad_path else stage+'\n')
        child = Mock()
        child.poll.return_value = code
        def cleanup_wait(**kwargs):
            # Deterministic delivery of two more stop requests while reaping.
            for sig in (signal.SIGINT, signal.SIGINT, signal.SIGTERM):
                handler = handlers[sig]
                self.assertEqual(handler, signal.SIG_IGN)
                if callable(handler):
                    handler(sig, None)
            return 0
        child.wait.side_effect = [subprocess.TimeoutExpired('child', 15), subprocess.TimeoutExpired('child', 5), 0, 0] if timeout else cleanup_wait
        def sleep(_):
            handlers[event](event, None)
        with patch('demo.signal.signal', side_effect=install), patch('demo.run', side_effect=run), patch('demo.build'), patch('demo.subprocess.Popen', return_value=child) as popen, patch('demo.time.sleep', side_effect=sleep):
            if code is not None:
                with self.assertRaises(RuntimeError): demo.main()
            elif bad_path:
                with self.assertRaises(ValueError): demo.main()
            else:
                demo.main()
        self.assertEqual(operations[-1], ('stop','router-lab'))
        removals = [op for op in operations if 'rm' in op]
        self.assertEqual(removals, [] if bad_path else [('shell','router-lab','rm','-rf','--',stage)])
        self.assertFalse(any('/tmp/router-stage' in op or 'router/' in op for op in operations))
        if not bad_path:
            self.assertTrue(all(call.kwargs['start_new_session'] for call in popen.call_args_list))
        self.assertTrue(all(v == signal.SIG_DFL for v in handlers.values()))
        return child

    def test_ctrl_c_and_sigterm_cleanup(self):
        for sig in (signal.SIGINT, signal.SIGTERM):
            self.exercise(event=sig)

    def test_unexpected_success_and_failure_are_failures(self):
        for code in (0, 7): self.exercise(code=code)

    def test_timeout_escalation_and_cleanup_signal_mask(self):
        child = self.exercise(event=signal.SIGINT, timeout=True)
        child.terminate.assert_called_once()
        child.kill.assert_called_once()

    def test_copy_failure_still_cleans_unique_stage_and_stops(self):
        stage = '/tmp/udp-router-demo-stage.Abc123def456'
        calls = []
        def run(*args, **kwargs):
            calls.append(args)
            if args[0] == 'copy':
                raise subprocess.CalledProcessError(1, 'copy')
            return SimpleNamespace(stdout=stage)
        with patch('demo.run', side_effect=run), patch('demo.build'), patch('demo.signal.signal'):
            with self.assertRaises(subprocess.CalledProcessError): demo.main()
        self.assertEqual(calls[-2:], [('shell','router-lab','rm','-rf','--',stage), ('stop','router-lab')])

    def test_cleanup_failure_still_stops_vm(self):
        calls = []
        def run(*args, **kwargs):
            calls.append(args)
            if 'rm' in args:
                raise subprocess.CalledProcessError(1, 'rm')
            return SimpleNamespace(stdout='/tmp/udp-router-demo-stage.Abc123def456')
        child = Mock(); child.poll.return_value = 0
        with patch('demo.run', side_effect=run), patch('demo.build'), patch('demo.subprocess.Popen', return_value=child), patch('demo.signal.signal'):
            with self.assertRaises(subprocess.CalledProcessError): demo.main()
        self.assertEqual(calls[-1], ('stop','router-lab'))

    def test_untrusted_stage_never_removed(self):
        self.exercise(bad_path=True)


if __name__ == '__main__': unittest.main()
