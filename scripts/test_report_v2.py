import json
import unittest
import xml.etree.ElementTree as ET
import report_v2 as report

class ReportTests(unittest.TestCase):
    def test_stats_and_svg_are_deterministic_and_include_ranges(self):
        values=report.stats([1,2,9]);self.assertEqual(values['median'],2);self.assertEqual(values['maximum'],9)
        for bad in ([],[True],[float('nan')],[-1]):
            with self.assertRaises(ValueError):report.stats(bad)
        args=('Actual <test>','All repeats',[('cell',values,'#5eead4')],'echoes/s')
        self.assertEqual(report.svg(*args),report.svg(*args));ET.fromstring(report.svg(*args))

    def test_inventory_all_reviewed_e2e_repeats_and_long_matching(self):
        names=sorted(set(n for n in report.package.FILES if n.startswith('docs/benchmarks/') and n.endswith('.json')))
        long=[];cells=0
        for name in names:
            d=json.loads((report.ROOT/name).read_text())
            if d.get('kind')=='REAL-LINUX-E2E':
                for key,rows in report.groups(d):
                    self.assertEqual(len(rows),3);self.assertEqual({r['repeat'] for r in rows},{1,2,3});report.summarize(rows);cells+=1
                    if '/comparison-long/' in name:long.append((key[2],name.split('/')[-1].split('-')[0]))
        self.assertEqual(cells,94);self.assertEqual(set(long),{(size,p) for size in (64,128,512,1400) for p in ('before','after')})
