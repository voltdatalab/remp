#!/usr/bin/env python3
"""Offline contract checks; integration remains an explicit separate opt-in."""
import json,pathlib,subprocess,unittest
ROOT=pathlib.Path(__file__).resolve().parents[2]
DOCKERFILE=ROOT/'caprover/docker/zookeeper.Dockerfile'
ENTRY=ROOT/'caprover/scripts/zookeeper-entrypoint.sh'
DEF=ROOT/'caprover/apps/st-remp-zookeeper/captain-definition'
class Contract(unittest.TestCase):
 def test_method3_definition_builds_repo_file(self):
  d=json.loads(DEF.read_text());self.assertEqual(d,{'schemaVersion':2,'dockerfilePath':'./caprover/docker/zookeeper.Dockerfile'});self.assertTrue((ROOT/d['dockerfilePath']).is_file())
 def test_parent_pinned_to_audited_digest(self):
  self.assertIn('FROM wurstmeister/zookeeper@sha256:7a7fd44a72104bfbd24a77844bad5fabc86485b036f988ea927d1780782a6680',DOCKERFILE.read_text())
 def test_startup_parent_bytes_guarded(self):
  s=DOCKERFILE.read_text();self.assertIn('b795ec48daa49c1acf67fb23617f23a54b60de6ddf651c0f24546604561e9a87',s);self.assertIn('sha256sum -c -',s)
 def test_no_ssh_in_executable_entrypoint(self):
  lines=[l for l in ENTRY.read_text().splitlines() if l.strip() and not l.lstrip().startswith('#')];self.assertFalse(any('sshd' in l for l in lines));self.assertEqual(lines[-1],'exec /opt/zookeeper-3.4.13/bin/zkServer.sh start-foreground')
 def test_exec_form_cmd_uses_own_wrapper(self):
  self.assertIn('CMD ["/bin/bash", "/usr/local/bin/remp-zookeeper-entrypoint.sh"]',DOCKERFILE.read_text())
 def test_configuration_adjustments_preserved(self):
  s=ENTRY.read_text();self.assertIn('log4j.appender.ROLLINGFILE.MaxBackupIndex',s);self.assertIn("'s|#autopurge|autopurge|g'",s);self.assertIn('"$ZK_HOME/conf/zoo.cfg"',s)
 def test_shell_syntax(self):
  r=subprocess.run(['bash','-n',str(ENTRY)],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr)
 def test_no_dependency_install_or_new_volume_contract(self):
  s=DOCKERFILE.read_text();self.assertFalse(any(l.strip().startswith(('VOLUME ','EXPOSE ','ENTRYPOINT ')) for l in s.splitlines()));self.assertNotIn('apt-get',s);self.assertNotIn('apk ',s)
class FixtureProtocolContract(unittest.TestCase):
 def setUp(self):
  import importlib.util
  path=ROOT/'caprover/scripts/zookeeper-fixture-client.py'
  spec=importlib.util.spec_from_file_location('fixture_protocol',path)
  assert spec is not None and spec.loader is not None
  self.client=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.client)
 def test_length_prefixed_buffer(self):
  self.assertEqual(self.client._buffer(b'abc'),b'\x00\x00\x00\x03abc')
 def test_scope_refuses_real_paths_before_network(self):
  from unittest.mock import patch
  with patch.object(self.client.socket,'create_connection') as connect:
   with self.assertRaises(ValueError):self.client.verify('127.0.0.1','get','/brokers','fixture-'+'a'*16)
   connect.assert_not_called()
 def test_oversized_and_negative_frames_refused(self):
  import struct
  class Socket:
   def __init__(self,n):self.value=struct.pack('>i',n)
   def recv(self,n):v=self.value[:n];self.value=self.value[n:];return v
  for n in (-1,0,1024*1024+1):
   with self.assertRaises(RuntimeError):self.client._frame(Socket(n))
if __name__=='__main__':unittest.main(verbosity=2)
