"""SQLite online backup and checksum-verified restore into a new runtime only."""
import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['backup','restore']);p.add_argument('--runtime',required=True,type=Path);p.add_argument('--destination',required=True,type=Path);a=p.parse_args()
    if a.action=='backup':
        a.destination.mkdir(parents=True,exist_ok=True);files={}
        for source in a.runtime.glob('*.sqlite3'):
            target=a.destination/source.name
            if target.exists():raise ValueError('Refusing to overwrite an existing backup')
            with closing(sqlite3.connect(source)) as src,closing(sqlite3.connect(target)) as dst:
                src.backup(dst)
                assert dst.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            files[source.name]=digest(target)
        if not files:raise ValueError('No initialized chess databases to back up')
        (a.destination/'manifest.json').write_text(json.dumps({'schema_version':'chesselo5000.backup/1','files':files,'credentials_included':False},indent=2),encoding='utf8')
    else:
        if a.runtime.exists():raise ValueError('Restore requires a new destination')
        manifest=json.loads((a.destination/'manifest.json').read_text(encoding='utf8'))
        if manifest['schema_version']!='chesselo5000.backup/1':raise ValueError('Foreign backup schema')
        for name,expected in manifest['files'].items():
            if Path(name).name!=name or not name.endswith('.sqlite3'):raise ValueError('Unsafe backup path')
            if digest(a.destination/name)!=expected:raise ValueError('Backup checksum mismatch')
            with closing(sqlite3.connect(a.destination/name)) as db:
                if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Backup integrity check failed')
        a.runtime.mkdir(parents=True)
        for name in manifest['files']:(a.runtime/name).write_bytes((a.destination/name).read_bytes())
    print(json.dumps({'action':a.action,'status':'PASS','databases':list(files if a.action=='backup' else manifest['files'])}))

if __name__=='__main__':main()
