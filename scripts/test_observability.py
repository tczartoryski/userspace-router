"""Strict aggregate/privacy validation; fixtures are not runtime evidence."""
import copy
import unittest
from dashboard import validate_snapshot, DROP_NAMES


def core(received=0):
    return dict(received=received,forwarded=received,expired=0,active=min(received,1),drops=dict.fromkeys(DROP_NAMES,0))


def queue(channel=2,processing=True):
    return dict(capacity=channel+int(processing),channel_capacity=channel,admitted=0,completed=0,
                occupancy=0,high_water=0,dropped=0,shutdown_drops=0)


def fixture():
    return dict(schema=2,unix_seconds=100,uptime_seconds=1,monotonic_ns=1_000_000_000,running=True,
                interfaces=['tun-in','tun-out'],backend='tun-poll',mode='workers',monitoring=True,event_sample_every=0,
                io_drops=0,tx=dict(packets=0,ip_bytes=0,would_block=0),dispatcher=core(),output=queue(processing=False),
                workers=[dict(id=i,ports=[40000+i*2,40001+i*2],capacity=2,observed_ns=0,core=core(),input=queue(),events=[]) for i in range(2)],
                rates=dict(interval_ns=None,tx_pps=None,tx_ip_mbps=None,core_forwarded_pps=None))


class ObservabilityTests(unittest.TestCase):
    def test_actual_state_fixture_and_final_conservation(self):
        d=fixture(); validate_snapshot(d)
        d['workers'][0]['core']=core(1);d['workers'][0]['input'].update(admitted=1,completed=1,high_water=1)
        d['output'].update(admitted=1,completed=1,high_water=1);d['tx'].update(packets=1,ip_bytes=64)
        d['running']=False;validate_snapshot(d)
        d['rates']=dict(interval_ns=500_000_000,tx_pps=2.0,tx_ip_mbps=.001024,core_forwarded_pps=2.0)
        validate_snapshot(d)

    def test_reject_malformed_missing_skewed_and_private_fields(self):
        changes=[lambda d:d.pop('tx'),lambda d:d.update(schema=True),
                 lambda d:d['workers'][0]['core'].update(received=1),
                 lambda d:d['workers'][0]['input'].update(occupancy=4),
                 lambda d:d['workers'][0]['input'].update(admitted=1),
                 lambda d:d['workers'][1].update(ports=[40001,40002]),
                 lambda d:d['workers'][0].update(capacity=3),
                 lambda d:d['workers'][0].update(observed_ns=2_000_000_000),
                 lambda d:d['workers'][0]['core'].update(active=3),
                 lambda d:d['tx'].update(packets=1),lambda d:d.update(io_drops=1),
                 lambda d:d['rates'].update(tx_pps=123),
                 lambda d:d.update(payload='private'),lambda d:d['workers'][0].update(mappings=[]),
                 lambda d:d['workers'][0]['input'].update(path='private'),
                 lambda d:d['workers'][0].update(id=True)]
        for mutate in changes:
            d=fixture();mutate(d)
            with self.assertRaises((ValueError,KeyError,TypeError)):validate_snapshot(d)

    def test_optional_events_are_bounded_and_never_accept_tuples(self):
        d=fixture();d['event_sample_every']=1
        w=d['workers'][0];w['core']=core(1);w['input'].update(admitted=1,completed=1,high_water=1)
        w['observed_ns']=10
        event=dict(monotonic_ns=10,direction='Inside',reason='Forward',bytes=64)
        w['events']=[event];validate_snapshot(d)
        for change in (lambda e:e.update(src='10.0.0.2'),lambda e:e.update(payload='x'),
                       lambda e:e.update(reason='<script>'),lambda e:e.update(bytes=65536),
                       lambda e:e.update(monotonic_ns=11)):
            bad=copy.deepcopy(d);change(bad['workers'][0]['events'][0])
            with self.assertRaises(ValueError):validate_snapshot(bad)
        bad=copy.deepcopy(d);bad['event_sample_every']=0
        with self.assertRaises(ValueError):validate_snapshot(bad)
        bad=copy.deepcopy(d);bad['workers'][0]['events']=[event]*65
        with self.assertRaises(ValueError):validate_snapshot(bad)

    def test_nonfinite_rates_and_false_units_are_rejected(self):
        for rate in (float('nan'),float('inf'),-1,True):
            d=fixture();d['rates']=dict(interval_ns=1,tx_pps=rate,tx_ip_mbps=0,core_forwarded_pps=0)
            with self.assertRaises(ValueError):validate_snapshot(d)
        d=fixture();d['uptime_seconds']=2
        with self.assertRaises(ValueError):validate_snapshot(d)
