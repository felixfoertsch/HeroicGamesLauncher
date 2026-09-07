"""One-time, inspected CI-first reorganization with atomic expected-SHA leases."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

REPO = 'felixfoertsch/HeroicGamesLauncher'
BASE = '2cc01fe4c88703ed002eafa6eb0ca06bb43443fc'
EXPECTED = {'main': '86a81d655a01a8ff2b8e25ed300201cbeb014e6b',
            'feat/stack-game-copies': 'dee93826a6dcd97c40eadffd988df3c2cf5f528b',
            'fix/nile-amazon-login': '7e3b75410111cc2af3f4750f542871fe9bea68da'}

def cmd(*args):
    return subprocess.check_output(args, text=True).strip()

def git(*args):
    return cmd('git', *args)

assert os.environ['GITHUB_REPOSITORY'] == REPO
root = Path('reordered')
plan = json.loads((root/'plan.json').read_text())
assert plan['expected'] == EXPECTED and plan['base'] == BASE
assert hashlib.sha256((root/'candidates.bundle').read_bytes()).hexdigest() == (root/'bundle.sha256').read_text().strip()
git('bundle','verify',str(root/'candidates.bundle'))
git('fetch',str(root/'candidates.bundle'),'refs/reorder/main:refs/reorder/main','refs/reorder/stack:refs/reorder/stack','refs/reorder/nile:refs/reorder/nile')
for key in ('main','stack','nile'):
    assert re.fullmatch(r'[0-9a-f]{40}', plan[key])
    assert git('rev-parse',f'refs/reorder/{key}') == plan[key]
ci = plan['main']
assert git('rev-parse',ci+'^') == BASE
assert git('rev-list','--count',BASE+'..'+ci) == '1'
assert 'Downstream-CI: true' in git('show','-s','--format=%B',ci).splitlines()
for key in ('stack','nile'):
    assert git('rev-parse',plan[key]+'^') == ci
    assert git('rev-list','--count',ci+'..'+plan[key]) == '1'
infra = git('diff','--name-only',BASE,ci).splitlines()
assert all(p.startswith('.github/') or p in ('AGENTS.md','doc/downstream.md','doc/custom-builds.md') for p in infra), infra
for key in ('main','stack','nile'):
    assert not any('ci-reorder' in p or '__pycache__' in p for p in git('ls-tree','-r','--name-only',plan[key]).splitlines())
remote = dict((line.split()[1],line.split()[0]) for line in git('ls-remote','--refs','origin').splitlines())
assert remote['refs/heads/downstream-base'] == BASE
for branch, sha in EXPECTED.items():
    assert remote['refs/heads/'+branch] == sha, 'Concurrent branch update: '+branch
new = {'main':ci, 'feat/stack-game-copies':plan['stack'], 'fix/nile-amazon-login':plan['nile']}
args=['push','--atomic']
updates=[]
run=os.environ['GITHUB_RUN_ID']
for branch, old in EXPECTED.items():
    ref='refs/heads/'+branch
    args.append('--force-with-lease='+ref+':'+old)
    updates.append(new[branch]+':'+ref)
    backup='refs/tags/downstream-backup/ci-first-'+run+'-'+branch.replace('/','-')
    assert backup not in remote
    args.append('--force-with-lease='+backup+':')
    updates.append(old+':'+backup)
print(git(*args,'origin',*updates))
verified = dict((line.split()[1],line.split()[0]) for line in git('ls-remote','--refs','origin').splitlines())
for branch, sha in new.items():
    assert verified['refs/heads/'+branch] == sha
# No existing published tag may move or disappear during this reorganization.
for ref, old in remote.items():
    if ref.startswith('refs/tags/'):
        assert verified.get(ref) == old, ref
with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as f:
    f.write('## CI-first history promoted\n\n'+json.dumps(new,indent=2)+'\n')
# GITHUB_TOKEN pushes suppress push-triggered workflows. Dispatch explicitly only in that fallback.
if os.environ.get('HAS_PUSH_TOKEN') != 'true':
    for branch in new:
        cmd('gh','workflow','run','downstream.yml','--repo',REPO,'--ref',branch)
