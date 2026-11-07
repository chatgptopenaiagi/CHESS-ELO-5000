"""Build Git-bound source, development, backend and sanitized evidence packages."""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import zipfile

ROOT=Path(__file__).resolve().parents[1]
TAG='v0.1.0-dev.1-chess-elo-5000'
GIT=r'C:\Program Files\Git\cmd\git.exe'

def sha(data):return hashlib.sha256(data).hexdigest()
def git(*args):return subprocess.check_output([GIT,*args],cwd=ROOT)

def secrets():
    result=[]
    for path in (ROOT/'runtime'/'private').glob('*.json'):
        try:value=json.loads(path.read_text(encoding='utf-8-sig'))
        except (ValueError,OSError):continue
        def visit(item,key=''):
            if isinstance(item,dict):
                for k,v in item.items():visit(v,k)
            elif isinstance(item,list):
                for v in item:visit(v,key)
            elif isinstance(item,str) and len(item)>=16 and re.search('password|secret|token',key,re.I):result.append(item.encode())
        visit(value)
    return result

def scan(entries,needles):
    for name,data in entries.items():
        if any(secret in data for secret in needles):raise ValueError('Private credential detected in '+name)
        if re.search(rb'gh[pousr]_[A-Za-z0-9]{30,}|sk-proj-[A-Za-z0-9_-]{30,}',data):raise ValueError('Credential-shaped token detected in '+name)
        if name.lower().endswith('.zip'):
            with zipfile.ZipFile(io.BytesIO(data)) as nested:scan({n:nested.read(n) for n in nested.namelist() if not n.endswith('/')},needles)

def write_zip(path,entries,stamp):
    with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for name,data in sorted(entries.items()):
            info=zipfile.ZipInfo('CHESS-ELO-5000/'+name,date_time=stamp);info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o644<<16
            archive.writestr(info,data)
    with zipfile.ZipFile(path) as archive:
        assert archive.testzip() is None
        assert len(archive.namelist())==len(entries)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    commit=git('rev-parse','HEAD').decode().strip()
    if git('diff','--name-only','HEAD').strip():raise ValueError('Tracked source differs from the source commit; commit before building')
    names=[n.decode() for n in git('ls-files','-z').split(b'\0') if n]
    if not names:raise ValueError('No committed source files')
    source={name:git('show',commit+':'+name) for name in names}
    forbidden=('runtime/','.venv/','dist/','.git/')
    if any(name.startswith(forbidden) for name in source):raise ValueError('Operational state tracked in source')
    args.output.mkdir(parents=True,exist_ok=True)
    if any(args.output.glob('CHESS-ELO-5000-*.zip')):raise ValueError('Release output already has packages; use a new candidate directory')
    info={'product':'CHESS ELO 5000','version':'0.1.0-development','tag':TAG,'commit':commit,'dirty':False,
          'source_tree':git('rev-parse','HEAD^{tree}').decode().strip(),'source_files_sha256':{n:sha(v) for n,v in source.items()}}
    source['build-info.json']=json.dumps(info,indent=2).encode()
    timestamp=int(git('show','-s','--format=%ct','HEAD').decode());stamp=datetime.fromtimestamp(timestamp,timezone.utc).timetuple()[:6]
    engine_root=ROOT/'stockfish'/'stockfish'
    engine={str(p.relative_to(ROOT)).replace('\\','/'):p.read_bytes() for p in engine_root.rglob('*') if p.is_file()}
    executable='stockfish/stockfish/stockfish-windows-x86-64-universal.exe'
    if executable not in engine or sha(engine[executable]).upper()!='45BC8E4969147DB9C2EB533810637994619BFF0EACC81CCFD9854394901BCBD0':raise ValueError('Verified engine binding changed')
    corresponding={'third_party/stockfish19/'+n.removeprefix('stockfish/stockfish/'):v for n,v in engine.items() if not n.lower().endswith(('.exe','.dll','.obj','.o'))}
    wheels={'wheelhouse/'+p.name:p.read_bytes() for p in (ROOT/'runtime'/'wheelhouse').glob('*.whl')}
    if not wheels:raise ValueError('Offline runtime dependency wheels missing')
    # Build the native Joomla artifact from this exact, clean committed source.
    subprocess.run([r'C:\Program Files\PowerShell\7\pwsh.exe','-NoProfile','-File',str(ROOT/'scripts'/'Build-JoomlaChessPackage.ps1'),'-OutputDirectory',str(args.output)],cwd=ROOT,check=True,capture_output=True)
    joomla=args.output/'CHESS-ELO-5000-Joomla-Package.zip'
    browser_receipts=[]
    for receipt in (ROOT/'evidence'/'browser').glob('*-joomla-install/verification.json'):
        value=json.loads(receipt.read_text(encoding='utf-8-sig'))
        if value.get('status')=='PASS' and value.get('package_tested_sha256')==sha(joomla.read_bytes()):browser_receipts.append(str(receipt.relative_to(ROOT)))
    if not browser_receipts:raise ValueError('The exact deterministic native package has no passing real administrator browser installation receipt')
    verification={}
    for p in (ROOT/'evidence').rglob('*'):
        if not p.is_file() or 'private' in str(p.relative_to(ROOT/'evidence')).lower() or p.suffix.lower() not in ('.json','.xml','.png','.txt','.md','.pgn'):continue
        if p.name in ('environment-discovery.json',):continue
        verification['evidence/'+p.relative_to(ROOT/'evidence').as_posix()]=p.read_bytes()
    verification['build-info.json']=source['build-info.json']
    variants={
        'Source':{**source,**corresponding},
        'Development':{**source,**engine,**wheels,'dist/CHESS-ELO-5000-Joomla-Package.zip':joomla.read_bytes()},
        'Python-Backend':{**{n:v for n,v in source.items() if not n.startswith('joomla/')},**engine,**wheels},
        'Verification':verification}
    variants['Python-Backend']['PACKAGE-README.md']=b'# Python backend package\n\nRun Start-CHESS-ELO-5000.ps1 -Standalone. This package includes the complete Python/client source, offline Windows Python3.14 runtime dependency wheels, Stockfish19 executable and corresponding source. Native Joomla extension source is in the Source and Development packages.\n'
    needles=secrets();artifacts=[]
    # The native package uses Joomla's required root manifest (no enclosing product folder).
    with zipfile.ZipFile(joomla) as z:scan({n:z.read(n) for n in z.namelist() if not n.endswith('/')},needles)
    for name,entries in variants.items():
        scan(entries,needles);path=args.output/f'CHESS-ELO-5000-{name}.zip';write_zip(path,entries,stamp)
        data=path.read_bytes();artifacts.append({'name':path.name,'bytes':len(data),'sha256':sha(data),'entries':len(entries)})
    artifacts.append({'name':joomla.name,'bytes':joomla.stat().st_size,'sha256':sha(joomla.read_bytes()),'format':'Native Joomla package'})
    manifest={**{k:v for k,v in info.items() if k!='source_files_sha256'},'created_utc':datetime.now(timezone.utc).isoformat(),'artifacts':artifacts,
              'privacy_scan':{'known_local_credentials_scanned':len(needles),'credential_matches':0,'credential_pattern_matches':0},
              'engine_executable_sha256':sha(engine[executable]),'engine_corresponding_source_included':True,
              'offline_wheels_sha256':{n:sha(v) for n,v in wheels.items()},'acceptance':'CANDIDATE_REQUIRES_EXTRACTED_ACCEPTANCE_BEFORE_PUBLICATION'}
    manifest['joomla_exact_package_browser_receipts']=browser_receipts
    (args.output/'MANIFEST.json').write_text(json.dumps(manifest,indent=2),encoding='utf8')
    (args.output/'SHA256SUMS.txt').write_text('\n'.join(r['sha256']+'  '+r['name'] for r in artifacts)+'\n',encoding='utf8')
    print(json.dumps(manifest,indent=2))
if __name__=='__main__':main()
