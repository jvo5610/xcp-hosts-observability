#!/usr/bin/env python3
"""Fett-only local OTLP repair; stdlib and Python 3.6 compatible.

--check makes no changes. --apply reads {authorization_b64: ...} from stdin.
--rollback DIR restores only this helper's three modified files after hash guards.
No credential, complete configuration, or journal payload is printed.
"""
import argparse
import base64
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile

CONFIG=Path('/etc/otelcol-contrib/config.yaml')
ENV=Path('/etc/otelcol-contrib/solo-otlp.env')
DROPIN=Path('/etc/systemd/system/otelcol-contrib.service.d/20-solo-otlp.conf')
DROPIN_TEXT='[Service]\nEnvironmentFile=/etc/otelcol-contrib/solo-otlp.env\n'
ENDPOINT='http://100.111.88.68:30418'

def digest(data):return hashlib.sha256(data).hexdigest()
def run(args,env=None,timeout=120):
    p=subprocess.run(args,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                     universal_newlines=True,timeout=timeout)
    if p.returncode:raise RuntimeError('Command failed (output suppressed): '+args[0])
    return p.stdout
def block(text,name):
    lines=text.splitlines(True)
    found=[i for i,l in enumerate(lines) if re.match(r'^\s*'+re.escape(name)+r':\s*$',l.rstrip())]
    if len(found)!=1:raise RuntimeError('Expected exactly one exporter block: '+name)
    start=found[0];level=len(lines[start])-len(lines[start].lstrip());end=start+1
    while end<len(lines):
        line=lines[end]
        if line.strip() and not line.lstrip().startswith('#') and len(line)-len(line.lstrip())<=level:break
        end+=1
    return lines,start,end,level
def desired(text):
    lines,start,end,level=block(text,'otlphttp/local');part=lines[start:end]
    field=' '*(level+2);header=' '*(level+4)
    positions=[i for i,l in enumerate(part) if l.startswith(field+'endpoint:')]
    if len(positions)!=1:raise RuntimeError('Expected one local endpoint')
    part[positions[0]]=field+'endpoint: '+ENDPOINT+'\n'
    auth=[i for i,l in enumerate(part) if l.startswith(header+'Authorization:')]
    wanted=header+'Authorization: "Basic ${env:SOLO_OTLP_AUTH_B64}"\n'
    if len(auth)>1:raise RuntimeError('Ambiguous local auth headers')
    if auth:part[auth[0]]=wanted
    else:
        headers=[i for i,l in enumerate(part) if l.startswith(field+'headers:')]
        if len(headers)>1:raise RuntimeError('Ambiguous local headers')
        if headers:part.insert(headers[0]+1,wanted)
        else:part.extend([field+'headers:\n',wanted])
    updated=''.join(lines[:start]+part+lines[end:])
    # Preserve the unrelated Cloud exporter byte-for-byte.
    old,a,b,_=block(text,'prometheusremotewrite/grafana_cloud')
    new,x,y,_=block(updated,'prometheusremotewrite/grafana_cloud')
    if old[a:b]!=new[x:y]:raise RuntimeError('Unrelated Cloud exporter changed')
    return updated
def atomic(path,data,mode):
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='.otlp-',dir=str(path.parent))
    with os.fdopen(fd,'wb') as f:f.write(data)
    os.chmod(name,mode);os.replace(name,str(path))
def restart():
    run(['systemctl','daemon-reload'])
    run(['systemctl','restart','otelcol-contrib'],timeout=120)
    run(['systemctl','is-active','--quiet','otelcol-contrib'])
def restore(folder,manifest):
    for record in manifest['files']:
        p=Path(record['path'])
        if p not in [CONFIG,ENV,DROPIN] or not p.exists() or digest(p.read_bytes())!=record['after_sha256']:
            raise RuntimeError('Rollback hash/path guard failed; no changes made')
    for record in manifest['files']:
        p=Path(record['path'])
        if record['existed']:atomic(p,(folder/record['backup']).read_bytes(),record['mode'])
        else:p.unlink()
    restart()

def main():
    ap=argparse.ArgumentParser();g=ap.add_mutually_exclusive_group()
    g.add_argument('--check',action='store_true');g.add_argument('--apply',action='store_true')
    g.add_argument('--rollback');args=ap.parse_args();os.umask(0o077)
    if os.geteuid()!=0:raise RuntimeError('Run as root on Fett')
    if socket.gethostname()!='fett':raise RuntimeError('Fett-only hostname guard failed; no changes made')
    if args.rollback:
        folder=Path(args.rollback);manifest=json.loads((folder/'manifest.json').read_text())
        restore(folder,manifest);print(json.dumps({'rolled_back':True,'collector_active':True}));return
    original=CONFIG.read_text();updated=desired(original)
    if not args.apply:
        print(json.dumps({'check':True,'config_change_needed':updated!=original,
                          'endpoint':ENDPOINT,'credential_file_present':ENV.exists()}));return
    token=json.load(sys.stdin)['authorization_b64']
    if not re.fullmatch(r'[A-Za-z0-9+/]+={0,2}',token):raise RuntimeError('Invalid credential encoding')
    decoded=base64.b64decode(token,validate=True)
    if b':' not in decoded or b'\n' in decoded:raise RuntimeError('Invalid credential format')
    env_data=('SOLO_OTLP_AUTH_B64='+token+'\n').encode()
    wanted=[(CONFIG,updated.encode(),CONFIG.stat().st_mode&0o777),(ENV,env_data,0o600),(DROPIN,DROPIN_TEXT.encode(),0o644)]
    if all(p.exists() and p.read_bytes()==data and p.stat().st_mode&0o777==mode for p,data,mode in wanted):
        print(json.dumps({'changed':False,'endpoint':ENDPOINT}));return
    stamp=datetime.datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
    folder=Path('/root/solo-otlp-collector-recovery-'+stamp);folder.mkdir(mode=0o700)
    manifest={'files':[]}
    for index,(p,data,mode) in enumerate(wanted):
        existed=p.exists();record={'path':str(p),'existed':existed,'after_sha256':digest(data),'mode':p.stat().st_mode&0o777 if existed else mode,'backup':'before-'+str(index)}
        if existed:atomic(folder/record['backup'],p.read_bytes(),0o600)
        manifest['files'].append(record)
    # Back up the vendor unit for evidence; it is never modified/restored here.
    unit=Path('/usr/lib/systemd/system/otelcol-contrib.service')
    if unit.exists():atomic(folder/'vendor-unit.before',unit.read_bytes(),0o600)
    staged=folder/'config.staged';atomic(staged,updated.encode(),0o600)
    environment=os.environ.copy()
    for file in ['/etc/otelcol-contrib/grafana-cloud.env','/etc/otelcol-contrib/otelcol-contrib.conf']:
        for line in Path(file).read_text().splitlines():
            if not line.strip() or line.lstrip().startswith('#') or '=' not in line:continue
            key,value=line.split('=',1)
            if re.fullmatch(r'[A-Z][A-Z0-9_]*',key.strip()):environment[key.strip()]=' '.join(shlex.split(value))
    environment['SOLO_OTLP_AUTH_B64']=token
    run(['/usr/bin/otelcol-contrib','validate','--config='+str(staged)],env=environment)
    atomic(folder/'manifest.json',json.dumps(manifest,indent=2).encode(),0o600)
    for p,data,mode in wanted:atomic(p,data,mode)
    try:restart()
    except Exception:
        restore(folder,manifest)
        raise RuntimeError('New collector restart failed; prior files restored and collector restarted')
    print(json.dumps({'changed':True,'validated':True,'collector_active':True,
                      'backup':str(folder),'endpoint':ENDPOINT,'credentials_mode':'0600',
                      'cloud_exporter_preserved':True}))

if __name__=='__main__':
    try:main()
    except Exception as e:
        # Fixed messages only: no raw configuration, environment or subprocess output.
        print('RECOVERY_FAILED: '+str(e),file=sys.stderr);sys.exit(1)
