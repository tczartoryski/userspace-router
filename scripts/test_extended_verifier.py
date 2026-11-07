"""Synthetic evidence-verifier tests only; these do not send any packets."""
import json
import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from extended import verify
from traffic import DROP_REASONS

class ExtendedVerifierTests(unittest.TestCase):
    def fixture(self, root):
        observations=[dict(payload=p,peer=['198.51.100.1',port],ttl=63)
                      for p,port in zip(('client-a','client-b','expire','reallocated'),(40000,40001,40000,40001))]
        (root/'server.jsonl').write_text('\n'.join(map(json.dumps,observations)))
        (root/'client-negative.json').write_text('{"timed_out":true}')
        counters=dict(received=13,forwarded=7,active=1,expired=3,io_drops=0,**{r:0 for r in DROP_REASONS})
        counters.update(Capacity=1,Policy=1,Filter=4)
        line=' '.join(f'{k}={v}' for k,v in counters.items())
        (root/'router.log').write_text(line+'\n')
        return line

    def test_accepts_complete_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.fixture(root)
            with contextlib.redirect_stdout(io.StringIO()):
                verify(root)
            self.assertTrue(json.loads((root/'PASS.json').read_text())['real_kernel_udp'])

    def test_rejects_stale_malformed_and_wrong_final_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);good=self.fixture(root)
            for bad in (good+' Filter=4',good.replace('Capacity=1','Capacity=0'),good.replace('expired=3','expired=2'),good+' Unknown=0','fatal error'):
                (root/'router.log').write_text(good+'\n'+bad+'\n')
                with self.assertRaises((AssertionError,ValueError)):
                    verify(root)
                self.assertFalse((root/'PASS.json').exists())

if __name__ == '__main__': unittest.main()
