"""Pure MICRO aggregation/schema tests; no executable or network launched."""
import copy
import json
import unittest
from benchmark import aggregate, parse, CASES


def fixture():
    keys = [('timestamp',0,0)] + [(c,s,f) for c in sorted(CASES-{'timestamp'}) for s in (64,128,512,1400) for f in (1,64,512)]
    return [dict(schema=1,kind='MICRO',case=c,size=s,flows=f,n=8,p50_ns=2,p95_ns=3,
                 p99_ns=4,sum_ns=16,wall_ns=20,cpu_ns=None,rss_bytes=None) for c,s,f in keys]


class BenchmarkTests(unittest.TestCase):
    def test_aggregation(self):
        result = aggregate([1,2,3])
        self.assertEqual(result, dict(median=2,minimum=1,maximum=3,cv=.5))
        self.assertEqual(aggregate([0,0,0])['cv'],0)
        for bad in ([],[1,2],[1,2,True],[1,2,-1],[1,2,float('nan')],[1,2,float('inf')]):
            with self.assertRaises(ValueError): aggregate(bad)

    def test_parse_and_invalid_metrics(self):
        encode = lambda rows: '\n'.join(json.dumps(r) for r in rows)
        self.assertEqual(len(parse(encode(fixture()),8)),49); self.assertEqual(parse(encode(fixture()),8), parse(encode(list(reversed(fixture()))),8))
        for key,value in [('n',True),('n',7),('sum_ns',-1),('p50_ns',float('nan')),
                          ('p95_ns',1),('wall_ns',0),('cpu_ns',3),('rss_bytes',0),('schema',True)]:
            rows = copy.deepcopy(fixture()); rows[0][key] = value
            with self.assertRaises(ValueError): parse(encode(rows),8)
        for rows in (fixture()[:-1],fixture()+fixture()[:1],fixture()[:-1]+fixture()[:1]):
            with self.assertRaises(ValueError): parse(encode(rows),8)
        with self.assertRaises(ValueError): parse('not JSON',8)
