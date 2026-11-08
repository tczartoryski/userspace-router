import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock
import live_v2_demo as live
import read_snapshot

class LiveTests(unittest.TestCase):
    def test_payload_and_gate(self):
        self.assertEqual(live.STATE,Path("/tmp/udp-router-v2-live"))
        self.assertEqual(read_snapshot.LIVE_SNAPSHOT,live.STATE/"snapshot.json")
        with patch("sys.argv",["read_snapshot.py","--v2-live"]),patch.object(read_snapshot,"read",return_value=b"{}") as reader,patch.object(read_snapshot.sys,"stdout",Mock()):
            read_snapshot.main()
            reader.assert_called_once_with(live.STATE/"snapshot.json")
        self.assertEqual(live.decode(live.payload(12,3)),(12,3))
        for data in (b'bad',b'LIVEV2|2000|0',b'LIVEV2|1|4',b'LIVEV2|01|2'):
            with self.assertRaises(ValueError):live.decode(data)
        with patch.dict('os.environ',{'UDP_ROUTER_ISOLATED_LINUX':'NO'}):
            with self.assertRaises(ValueError):live.main()

    def test_refuse_existing_state_without_touching_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            state=Path(tmp)/'owned';state.mkdir();marker=state/'unrelated';marker.write_text('keep')
            with patch.object(live,'STATE',state):
                with self.assertRaises(FileExistsError):live.collect('unused','unused')
            self.assertEqual(marker.read_text(),'keep')

    def test_partial_setup_cleans_only_created_state_and_atomic_phase(self):
        calls=[];self_test=self
        class Lab:
            def __init__(self,*_):pass
            def setup(self,_):
                self_test.assertEqual(state.stat().st_mode&0o777,0o700)
                self_test.assertEqual(state.stat().st_uid,os.geteuid())
                raise OSError('injected setup failure')
            def cleanup(self):calls.append('cleanup')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);state=root/'state'
            with patch.object(live,'STATE',state),patch.object(live,'Lab',Lab):
                with self.assertRaises(OSError):live.collect('unused',root/'unused')
            self.assertFalse(state.exists());self.assertEqual(calls,['cleanup'])
            live.phase(root,'current');live.phase(root,'stale');self.assertEqual((root/'phase').read_text(),'stale')

    def test_reader_rejects_nonprivate_symlink_and_fifo_without_blocking(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=root/'snapshot.json';path.write_bytes(b'{}');path.chmod(0o600)
            self.assertEqual(read_snapshot.read(path),b'{}')
            path.chmod(0o644)
            with self.assertRaises(ValueError):read_snapshot.read(path)
            path.unlink();path.symlink_to('/dev/null')
            with self.assertRaises(OSError):read_snapshot.read(path)
            path.unlink();os.mkfifo(path,0o600)
            with self.assertRaises(ValueError):read_snapshot.read(path)

    def test_retained_successful_capture_inventory_hashes_and_bounds(self):
        import hashlib
        import json
        import struct
        import package
        root=package.ROOT/'docs/qa/v2-live'
        capture=json.loads((root/'capture.json').read_text())
        self.assertEqual(capture['kind'],'ACTUAL-LIVE-BROWSER-SAMPLED')
        self.assertEqual(capture['target_fps'],1)
        frames=capture['frames'];self.assertEqual(len(frames),44)
        self.assertEqual([f['index'] for f in frames],list(range(44)))
        elapsed=[f['elapsed_ms'] for f in frames]
        self.assertTrue(all(0<=n<46000 for n in elapsed))
        self.assertTrue(all(a<b for a,b in zip(elapsed,elapsed[1:])))
        for frame in frames:
            name=f"docs/qa/v2-live/frames/{frame['index']:04d}.png"
            raw=(package.ROOT/name).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(),frame['sha256'],name)
            self.assertEqual(raw[:8],b'\x89PNG\r\n\x1a\n')
            self.assertEqual(struct.unpack('>II',raw[16:24]),(1440,1300))
            self.assertIn(name,package.FILES);self.assertIn(name,package.BINARY_FILES)
        self.assertEqual({f['state']['status'] for f in frames},{'Connecting to runtime…','OFFLINE','CURRENT','STALE'})
        for index,status,ms in ((3,'CURRENT',3579),(19,'STALE',19568),(21,'CURRENT',21565),(33,'OFFLINE',33588)):
            self.assertEqual((frames[index]['state']['status'],frames[index]['elapsed_ms']),(status,ms))
        movie=root/'live-v2.mp4';self.assertIn('docs/qa/v2-live/live-v2.mp4',package.BINARY_FILES)
        self.assertTrue(300000<movie.stat().st_size<600000)
        self.assertEqual(movie.read_bytes()[4:8],b'ftyp')
        self.assertEqual({p.relative_to(package.ROOT).as_posix() for p in root.rglob('*') if p.is_file()},set(package.LIVE_FILES))

    def test_retained_live_final_conservation_and_private_schema(self):
        import json
        import package
        from dashboard import validate_snapshot
        observations=json.loads((package.ROOT/'docs/qa/v2-live/observations.json').read_text())
        self.assertEqual(observations['kind'],'REAL-LINUX-LIVE-DEMO')
        client=observations['client'];offered=client['offered_by_phase'];received=client['verified_echoes_by_send_phase']
        self.assertEqual(offered,dict(current=444,stale=116,resume=444,offline=148))
        self.assertEqual(received,dict(current=444,stale=116,resume=443,offline=0))
        self.assertEqual(sum(received.values()),observations['server']['actual_echoes'])
        snapshots=observations['snapshots']
        for snapshot in snapshots.values():validate_snapshot(snapshot)
        final=snapshots['offline'];self.assertFalse(final['running'])
        self.assertEqual(final['tx']['packets'],2*observations['server']['actual_echoes'])
        self.assertEqual(sum(w['core']['forwarded'] for w in final['workers']),final['tx']['packets'])
        for queue in [final['output']]+[w['input'] for w in final['workers']]:
            self.assertEqual(queue['occupancy'],0)
            self.assertEqual(queue['admitted'],queue['completed']+queue['shutdown_drops'])
            self.assertLessEqual(queue['high_water'],queue['capacity'])
        self.assertLess(snapshots['current']['monotonic_ns'],snapshots['resumed']['monotonic_ns'])
        self.assertLess(snapshots['resumed']['monotonic_ns'],final['monotonic_ns'])
