"""Pure fixture, bounds and lifecycle checks. No guest/network/root operations."""
import copy
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import worker_acceptance as acceptance


def server_fixture():
    return dict(records=[dict(stage='local' if i==0 else 'owner',token=i,peer=['198.51.100.1',40000+2*i]) for i in range(4)]+[dict(stage='reallocate',token=0,peer=['198.51.100.1',40001])],
                wrong_address_sent=3,wrong_port_sent=3,late_sent=1,overload_seen=10)


class WorkerAcceptanceTests(unittest.TestCase):
    def test_fixture_hash_selects_four_same_port_owners_and_local_overflow(self):
        addresses,extra=acceptance.clients()
        self.assertEqual([acceptance.owner(a) for a in addresses],[0,1,2,3])
        self.assertEqual(acceptance.owner(extra),0)
        self.assertNotIn(extra,addresses)
        self.assertTrue(all(a.startswith('10.0.0.') for a in addresses+[extra]))

    def test_payload_validation_is_exact_and_bounded(self):
        for stage in acceptance.STAGES:
            data=acceptance.payload(stage,32767)
            self.assertEqual(acceptance.decode(data),(stage,32767))
        for bad in (b'bad',b'URV2A|overload|32768',b'URV2A|private|1',b'URV2A|owner|01',b'x'*65):
            with self.assertRaises(ValueError):acceptance.decode(bad)

    def test_observed_port_ownership_negative_receipts_and_actual_attacks_required(self):
        acceptance.verify_receipts(server_fixture())
        changes=[lambda d:d['records'][1]['peer'].__setitem__(1,40000),
                 lambda d:d['records'].pop(2),lambda d:d.update(wrong_address_sent=0),
                 lambda d:d.update(wrong_port_sent=0),lambda d:d.update(late_sent=0),
                 lambda d:d['records'].append(dict(stage='denied',token=0,peer=['198.51.100.1',40001]))]
        for mutate in changes:
            d=copy.deepcopy(server_fixture());mutate(d)
            with self.assertRaises(ValueError):acceptance.verify_receipts(d)

    def test_gate_and_partial_setup_failure_always_cleanup(self):
        with patch.dict('os.environ',{'UDP_ROUTER_ISOLATED_LINUX':'NO'}):
            with self.assertRaises(ValueError):acceptance.main()
        operations=[]
        class Lab:
            def __init__(self,*_):pass
            def setup(self,_):operations.append('setup');raise subprocess.CalledProcessError(1,['fixture'])
            def cleanup(self):operations.append('cleanup')
        with tempfile.TemporaryDirectory() as tmp,patch.object(acceptance,'Lab',Lab):
            with self.assertRaises(subprocess.CalledProcessError):acceptance.collect('unused',Path(tmp)/'unused.json')
        self.assertEqual(operations,['setup','cleanup'])
