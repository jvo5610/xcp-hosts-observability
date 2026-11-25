#!/usr/bin/env python3
"""Fett-only chrony repair: two reachable IP sources, slew only, no clock step."""
import argparse,datetime,hashlib,json,os,re,socket,subprocess,tempfile,time
from pathlib import Path
CONFIG=Path('/etc/chrony.conf')
def digest(b):return hashlib.sha256(b).hexdigest()
def run(args,timeout=40):
    p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,universal_newlines=True,timeout=timeout)
    if p.returncode:raise RuntimeError('Command failed: '+args[0]+' (output suppressed)')
    return p.stdout
def atomic(path,body,mode):
    fd,name=tempfile.mkstemp(prefix='.ntp-',dir=str(path.parent))
    with os.fdopen(fd,'w') as f:f.write(body)
    os.chmod(name,mode);os.replace(name,str(path))
def desired(text):
    if re.search(r'^\s*(include|confdir|sourcedir)\b',text,re.M):
        raise RuntimeError('Unexpected included configuration; review before changing')
    retained=[l for l in text.splitlines(True) if not re.match(r'^\s*(server|pool|peer|makestep|initstepslew|maxslewrate)\b',l,re.I) and not l.startswith('# Fett managed sources;')]
    return ''.join(retained).rstrip()+'\n\n# Fett managed sources; no stepping, maximum slew 0.5%.\nserver 192.168.4.1 iburst\nserver 162.159.200.1 iburst\nmaxslewrate 5000\n'
def main():
    p=argparse.ArgumentParser();p.add_argument('--apply',action='store_true');args=p.parse_args()
    if os.geteuid()!=0 or socket.gethostname()!='fett':raise RuntimeError('Root on exact hostname fett required')
    os.umask(0o077);before=CONFIG.read_text();after=desired(before)
    # Do not allow service startup flags that can force a time step.
    command=run(['ps','-C','chronyd','-o','args=']).split()
    if any(a in ['-s','-q'] for a in command):raise RuntimeError('Unsafe chronyd startup flag; no changes made')
    if not args.apply:
        print(json.dumps({'change_needed':after!=before,'sources':['192.168.4.1','162.159.200.1'],'maxslewrate_ppm':5000,'automatic_steps':False}));return
    if before==after:
        print(json.dumps({'changed':False}));return
    folder=Path('/root/fett-ntp-recovery-'+datetime.datetime.utcnow().strftime('%Y%m%dT%H%M%SZ'));folder.mkdir(mode=0o700)
    atomic(folder/'chrony.conf.before',before,0o600)
    # Isolate every validator state file; -Q only measures and never adjusts time.
    transient=''.join(l for l in after.splitlines(True) if not re.match(r'^\s*(driftfile|pidfile|dumpdir|logdir|rtcsync|rtcfile|bindcmdaddress|cmdport|port|user)\b',l))
    transient+='\nuser root\nport 0\ncmdport 0\npidfile '+str(folder/'validate.pid')+'\nbindcmdaddress '+str(folder/'validate.sock')+'\ndriftfile '+str(folder/'validate.drift')+'\n'
    atomic(folder/'chrony.validate.conf',transient,0o600)
    run(['/usr/sbin/chronyd','-Q','-t','15','-f',str(folder/'chrony.validate.conf')],timeout=25)
    atomic(folder/'metadata.json',json.dumps({'before_sha256':digest(before.encode()),'after_sha256':digest(after.encode()),'step_disabled':True,'maxslewrate_ppm':5000}),0o600)
    wall,mono=time.time(),time.monotonic()
    atomic(CONFIG,after,CONFIG.stat().st_mode&0o777)
    run(['systemctl','restart','chronyd']);run(['systemctl','is-active','--quiet','chronyd'])
    largest_jump=0
    for _ in range(20):
        time.sleep(1);w,m=time.time(),time.monotonic();largest_jump=max(largest_jump,abs((w-wall)-(m-mono)));wall,mono=w,m
    if largest_jump>0.1:raise RuntimeError('Clock continuity check failed; do not perform a manual time step')
    print(json.dumps({'changed':True,'validation_Q':True,'chronyd_active':True,'backup':str(folder),'max_clock_discontinuity_seconds':round(largest_jump,6),'sources':['192.168.4.1','162.159.200.1'],'maxslewrate_ppm':5000,'automatic_steps':False}))
if __name__=='__main__':
    try:main()
    except Exception as e:print('NTP_RECOVERY_FAILED: '+str(e),file=__import__('sys').stderr);__import__('sys').exit(1)
