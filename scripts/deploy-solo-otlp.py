#!/usr/bin/env python3
"""Run locally; only --apply reads SSM, and secrets travel over SSH stdin."""
import argparse
import base64
import json
from pathlib import Path
import subprocess

HOST='root@100.109.20.74'
KEY=str(Path.home()/'.ssh/id_rsa')
REMOTE='/root/solo-otlp-recovery/configure-solo-otlp.py'
def command(args,body=None):
    p=subprocess.run(args,input=body,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                     universal_newlines=True,timeout=180)
    if p.returncode:
        # Remote helper suppresses configuration/env/credential values.
        safe=[l for l in p.stderr.splitlines() if l.startswith('RECOVERY_FAILED:')]
        raise RuntimeError('; '.join(safe) or 'SSH/deployment failed; values suppressed')
    return p.stdout
def main():
    ap=argparse.ArgumentParser();g=ap.add_mutually_exclusive_group()
    g.add_argument('--apply',action='store_true');g.add_argument('--rollback')
    args=ap.parse_args()
    ssh=['ssh','-p','22','-i',KEY,'-o','BatchMode=yes',HOST]
    command(ssh+['umask 077; mkdir -p /root/solo-otlp-recovery; chmod 700 /root/solo-otlp-recovery'])
    helper=Path(__file__).with_name('configure-solo-otlp.py')
    command(['scp','-P','22','-i',KEY,'-o','BatchMode=yes',str(helper),HOST+':'+REMOTE])
    command(ssh+['chmod','600',REMOTE])
    action=['--check'];body=None
    if args.apply:
        import boto3
        result=boto3.client('ssm',region_name='us-east-1').get_parameter(
            Name='/observability/solo/otlp-gateway/authorization-b64',WithDecryption=True)
        token=result['Parameter']['Value']
        if b':' not in base64.b64decode(token,validate=True):raise RuntimeError('Invalid SSM credential encoding')
        body=json.dumps({'authorization_b64':token});action=['--apply']
    elif args.rollback:action=['--rollback',args.rollback]
    print(command(ssh+['python3',REMOTE]+action,body).strip())
if __name__=='__main__':main()
