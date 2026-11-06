#!/usr/bin/env python3
"""Opt-in, bounded disposable ZooKeeper/Kafka rehearsal. Never targets a service.

Uses only UUID-labelled fixture containers, fresh named volumes and one internal
bridge. No published ports, host mounts, production networks or volume reuse.
"""
import argparse,datetime,json,os,pathlib,re,shutil,subprocess,sys,time,uuid
BASE='wurstmeister/zookeeper@sha256:7a7fd44a72104bfbd24a77844bad5fabc86485b036f988ea927d1780782a6680'
KAFKA='wurstmeister/kafka@sha256:2d4bbf9cc83d9854d36582987da5f939fb9255fb128d18e3cf2c6ad825a32751'
LABEL='org.nucleo.ssh-audit.fixture'

def main():
 p=argparse.ArgumentParser();p.add_argument('--allow-isolated-docker-tests',action='store_true',required=True);p.add_argument('--engine-name',required=True);p.add_argument('--candidate',required=True);p.add_argument('--report',required=True);a=p.parse_args()
 assert not os.environ.get('DOCKER_HOST') and not os.environ.get('DOCKER_CONTEXT'),'unexpected_docker_override'
 assert re.fullmatch(r'nucleo-local/zookeeper-no-ssh:[a-z0-9.-]+',a.candidate),'candidate_tag_not_allowlisted'
 reportpath=pathlib.Path(a.report).resolve();assert not reportpath.exists(),'report_exists';reportpath.parent.mkdir(parents=True,exist_ok=True)
 started=time.monotonic();deadline=started+420;token=uuid.uuid4().hex[:16];prefix='nucleo-ssh-fixture-'+token;checks=[];owned={'containers':[],'volumes':[],'networks':[]};report={'fixture':token,'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'checks':checks,'production_data_used':False,'image':a.candidate}
 def cli(args,input=None,timeout=20,check=True,cleanup=False):
  if not cleanup:
   left=deadline-time.monotonic();assert left>0,'whole_run_deadline';timeout=min(timeout,max(1,left))
  r=subprocess.run(['docker',*args],input=input,capture_output=True,text=True,timeout=timeout)
  if check and r.returncode:raise RuntimeError('docker_'+args[0]+'_failed_exit_'+str(r.returncode)+':'+r.stdout[-1200:]+r.stderr[-600:])
  return r
 def inspect(kind,name):return json.loads(cli([kind,'inspect',name]).stdout)[0]
 def ok(name,condition,detail=None):
  checks.append({'name':name,'passed':bool(condition),**({'detail':detail} if detail is not None else {})});assert condition,name
 def own(kind,name):
  d=inspect(kind,name);labels=d.get('Labels') if kind!='container' else d['Config'].get('Labels');assert labels and labels.get(LABEL)==token,'fixture_ownership_mismatch';return d
 def volume(suffix):
  n=prefix+'-'+suffix;assert cli(['volume','inspect',n],check=False).returncode!=0
  # Record intent before creation, so ambiguous acknowledgement is cleaned by label.
  owned['volumes'].append(n);cli(['volume','create','--label',LABEL+'='+token,n]);own('volume',n);return n
 def create(suffix,image,network,mounts,aliases=(),env=(),caps=False):
  name=prefix+'-'+suffix;assert cli(['container','inspect',name],check=False).returncode!=0;owned['containers'].append(name)
  cmd=['create','--name',name,'--label',LABEL+'='+token,'--network',network,'--memory','768m' if suffix=='kafka' else '512m','--memory-swap','768m' if suffix=='kafka' else '512m','--cpus','1','--pids-limit','160','--security-opt','no-new-privileges','--log-opt','max-size=2m','--log-opt','max-file=1']
  if caps:
   cmd+=['--cap-drop','ALL']
   # The audited parent ships conf files owned by UID 501. Its root startup
   # edits them; production grants this default capability already.
   if suffix in ('zk','restored'):cmd+=['--cap-add','DAC_OVERRIDE']
  for alias in aliases:cmd+=['--network-alias',alias]
  for src,dst in mounts:
   assert src in owned['volumes'];own('volume',src);cmd+=['--mount','type=volume,source='+src+',target='+dst]
  for e in env:cmd+=['--env',e]
  cmd+=[image];cli(cmd);d=own('container',name)
  assert not d['HostConfig'].get('PortBindings') and not d['HostConfig']['Privileged'];assert not d['HostConfig'].get('Binds');assert set(d['NetworkSettings']['Networks'])=={network}
  assert all(m['Type']=='volume' and (m.get('Name') in owned['volumes'] or network=='none') for m in d.get('Mounts',[]))
  cli(['start',name]);return name
 def execute(name,args,input=None,timeout=15,check=True):own('container',name);return cli(['exec','-i',name,*args],input=input,timeout=timeout,check=check)
 def monitor(name):
  r=execute(name,['/bin/bash','-c','exec 3<>/dev/tcp/127.0.0.1/2181 || exit 3; printf mntr >&3; while IFS= read -r -t 2 line <&3 || [ -n "$line" ]; do printf "%s\\n" "$line"; line=; done'],check=False)
  return dict(l.split('\t',1) for l in r.stdout.splitlines() if '\t' in l and l.startswith('zk_'))
 def ready(name):
  end=min(deadline,time.monotonic()+50)
  while time.monotonic()<end:
   if own('container',name)['State']['Running']:
    m=monitor(name)
    if m.get('zk_server_state')=='standalone':return m
   else:break
   time.sleep(1)
  raise RuntimeError('zookeeper_not_ready')
 def names(name):
  r=cli(['top',name,'-eo','pid,comm']);return [l.split(None,1)[1].strip() for l in r.stdout.splitlines()[1:] if len(l.split(None,1))==2]
 def has_listener22(name):
  r=execute(name,['/bin/bash','-c','for f in /proc/net/tcp /proc/net/tcp6; do while IFS= read -r line; do printf "%s\\n" "$line"; done < "$f"; done'])
  return any(len(q)>3 and q[1].endswith(':0016') and q[3]=='0A' for q in (l.split() for l in r.stdout.splitlines()))
 def fixture_client(name,mode,node,marker):
  import importlib.util
  d=own('container',name);net=own('network',network)
  assert net['Internal'] and net['Driver']=='bridge' and set(d['NetworkSettings']['Networks'])=={network}
  host=d['NetworkSettings']['Networks'][network]['IPAddress'];assert host
  source=pathlib.Path(__file__).resolve().parent/'zookeeper-fixture-client.py'
  spec=importlib.util.spec_from_file_location('zookeeper_fixture_client',source)
  assert spec is not None and spec.loader is not None,'fixture_client_loader_missing'
  module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
  return module.verify(host,mode,node,marker)
 def remove_container(name):
  d=own('container',name);cli(['rm','--force','--volumes',d['Id']],cleanup=True);assert cli(['container','inspect',d['Id']],check=False,cleanup=True).returncode!=0
 def clean():
  errors=[]
  for kind,cmd in [('containers','container'),('volumes','volume'),('networks','network')]:
   for name in reversed(owned[kind]):
    try:
     r=cli([cmd,'inspect',name],check=False,cleanup=True)
     if r.returncode:continue
     d=json.loads(r.stdout)[0];labels=d['Config'].get('Labels') if cmd=='container' else d.get('Labels');assert labels and labels.get(LABEL)==token,'foreign_resource_refused'
     cli((['rm','--force','--volumes',d['Id']] if cmd=='container' else [cmd,'rm',name]),cleanup=True)
     assert cli([cmd,'inspect',name],check=False,cleanup=True).returncode!=0
    except Exception as e:errors.append({'resource':name,'reason':type(e).__name__})
  # A failed inspect is not proof of absence (the daemon may be unavailable).
  # Require three successful independent list reads with this invocation label.
  for args in (['ps','-aq'],['volume','ls','-q'],['network','ls','-q']):
   try:
    r=cli([*args,'--filter','label='+LABEL+'='+token],check=False,cleanup=True)
    if r.returncode or r.stdout.strip():errors.append({'resource':args[0],'reason':'absence_not_verified'})
   except Exception as e:errors.append({'resource':args[0],'reason':type(e).__name__})
  report['cleanup']={'verified_absent':not errors,'errors':errors,'resource_counts':{k:len(set(v)) for k,v in owned.items()}}
  return not errors
 try:
  info=json.loads(cli(['info','--format','{{json .}}']).stdout);ok('engine_identity',info['Name']==a.engine_name)
  available=int(next(l.split()[1] for l in pathlib.Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:')))*1024
  ok('resource_headroom',available>=8*1024**3 and shutil.disk_usage(reportpath.parent).free>=20*1024**3)
  base=inspect('image',BASE);cand=inspect('image',a.candidate);kimg=inspect('image',KAFKA)
  ok('base_and_kafka_match_production',base['Id']=='sha256:3f43f72cb2832e7a5fbed7f7dbcd0c43004357974d8f32555d101bd53e81e74f' and kimg['Id']=='sha256:a692873757c06a38279b6141e7f1cfb886afca37abb62415c542425ec53ba0bf')
  report['candidate_image_id']=cand['Id'];ok('candidate_retains_base_layers',cand['RootFS']['Layers'][:len(base['RootFS']['Layers'])]==base['RootFS']['Layers']);ok('candidate_skips_ssh_cmd',not cand['Config'].get('Entrypoint') and cand['Config']['Cmd']==['/bin/bash','/usr/local/bin/remp-zookeeper-entrypoint.sh'])
  # RED/control: demonstrate that the unmodified pinned image starts sshd.
  baseline=create('control',BASE,'none',[],env=['JVMFLAGS=-Xms64m -Xmx256m','JMXDISABLE=true']);ready(baseline)
  ok('red_original_image_starts_sshd_and_listener',any('sshd' in n for n in names(baseline)) and has_listener22(baseline));remove_container(baseline)
  network=prefix+'-net';owned['networks'].append(network);cli(['network','create','--driver','bridge','--internal','--label',LABEL+'='+token,network]);n=own('network',network);ok('isolated_internal_bridge',n['Internal'] and n['Driver']=='bridge' and not n.get('Ingress'))
  data=volume('data');conf=volume('conf');kdata=volume('kafka-data');mounts=[(data,'/opt/zookeeper-3.4.13/data'),(conf,'/opt/zookeeper-3.4.13/conf')]
  zk=create('zk',a.candidate,network,mounts,aliases=['zk'],env=['JVMFLAGS=-Xms64m -Xmx256m','JMXDISABLE=true'],caps=True);m=ready(zk);ok('candidate_zookeeper_3413_ready',m.get('zk_version','').startswith('3.4.13-'));ok('candidate_no_sshd_process_or_listener',not any('sshd' in n for n in names(zk)) and not has_listener22(zk))
  r=execute(zk,['/bin/bash','-c','IFS= read -r comm < /proc/1/comm; printf "%s\\n" "$comm"']);ok('java_is_pid1',r.stdout.strip()=='java')
  marker='fixture-'+token;node='/nucleo-hardening-'+token
  ok('fixture_znode_create_and_read',fixture_client(zk,'create',node,marker))
  # A non-default persistent configuration marker must survive replacement too.
  execute(zk,['/bin/bash','-c','printf "\\n# nucleo-fixture-config-preservation\\n" >> "$ZK_HOME/conf/zoo.cfg"'])
  kafka=create('kafka',KAFKA,network,[(kdata,'/kafka')],aliases=['kafka'],env=['KAFKA_ZOOKEEPER_CONNECT=zk:2181','KAFKA_ADVERTISED_LISTENERS=PLAINTEXT://kafka:9092','KAFKA_LISTENERS=PLAINTEXT://0.0.0.0:9092','KAFKA_BROKER_ID=1','KAFKA_LOG_DIRS=/kafka/logs','KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR=1','KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR=1','KAFKA_TRANSACTION_STATE_LOG_MIN_ISR=1','KAFKA_HEAP_OPTS=-Xms128m -Xmx256m','KAFKA_AUTO_CREATE_TOPICS_ENABLE=false'],caps=True)
  end=min(deadline,time.monotonic()+80)
  while time.monotonic()<end:
   r=execute(kafka,['/opt/kafka/bin/kafka-broker-api-versions.sh','--bootstrap-server','kafka:9092'],check=False,timeout=12)
   if r.returncode==0:break
   if not own('container',kafka)['State']['Running']:raise RuntimeError('kafka_exited')
   time.sleep(2)
  ok('kafka_281_connects_to_candidate',r.returncode==0)
  topic='fixture-'+token
  execute(kafka,['/opt/kafka/bin/kafka-topics.sh','--bootstrap-server','kafka:9092','--create','--topic',topic,'--partitions','1','--replication-factor','1'],timeout=20)
  execute(kafka,['/opt/kafka/bin/kafka-console-producer.sh','--broker-list','kafka:9092','--topic',topic],input=marker+'\n',timeout=20)
  r=execute(kafka,['/opt/kafka/bin/kafka-console-consumer.sh','--bootstrap-server','kafka:9092','--topic',topic,'--from-beginning','--max-messages','1','--timeout-ms','10000'],timeout=20);ok('kafka_fixture_produce_consume',marker in r.stdout.splitlines())
  own('container',zk);t=time.monotonic();cli(['stop','--time','20',zk],timeout=25);d=own('container',zk);ok('graceful_sigterm_no_kill_or_oom',not d['State']['Running'] and d['State']['ExitCode'] in (0,143) and not d['State']['OOMKilled'],{'exit':d['State']['ExitCode'],'seconds':round(time.monotonic()-t,3)})
  remove_container(zk)
  zk=create('zk',a.candidate,network,mounts,aliases=['zk'],env=['JVMFLAGS=-Xms64m -Xmx256m','JMXDISABLE=true'],caps=True);ready(zk)
  ok('fixture_data_survives_replacement',fixture_client(zk,'get',node,marker))
  r=execute(zk,['/bin/bash','-c','while IFS= read -r line; do case "$line" in "# nucleo-fixture-config-preservation") printf preserved;; esac; done < "$ZK_HOME/conf/zoo.cfg"']);ok('fixture_config_survives_replacement',r.stdout=='preserved');ok('replacement_still_has_no_ssh',not any('sshd' in n for n in names(zk)) and not has_listener22(zk))
  r=execute(kafka,['/opt/kafka/bin/kafka-console-consumer.sh','--bootstrap-server','kafka:9092','--topic',topic,'--from-beginning','--max-messages','1','--timeout-ms','15000'],timeout=25);ok('kafka_recovers_after_zookeeper_replacement',marker in r.stdout.splitlines())
  report['result']='PASS'
 except Exception as e:
  report['result']='FAIL';report['error']={'class':type(e).__name__,'message':str(e)[:1000]}
  for name in owned['containers']:
   try:
    own('container',name);report.setdefault('fixture_log_tails',{})[name]=cli(['logs','--tail','35',name],check=False,cleanup=True).stderr[-5000:]
   except Exception:pass
 finally:
  if not clean():report['result']='FAIL'
  report['duration_seconds']=round(time.monotonic()-started,3);report['check_count']=len(checks);report['passed_checks']=sum(c['passed'] for c in checks)
  fd=os.open(reportpath,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
  with os.fdopen(fd,'w') as f:json.dump(report,f,indent=2)
  print(json.dumps(report,ensure_ascii=False))
 return 0 if report['result']=='PASS' else 1
if __name__=='__main__':sys.exit(main())
