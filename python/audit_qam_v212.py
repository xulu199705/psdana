"""Check frozen bytes, completed test evidence and executable API examples."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from qam_gen import ROOT

def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT)
def run():
    protected=[p for p in git('ls-files','data','go/psd','go/csvio','go/go.mod','go/go.sum',
        'python/psd/core.py','python/psd/power.py','python/psd/csvio.py','python/psd/iqio.py').decode().splitlines()]
    request=''.join(f'HEAD:{p}\n' for p in protected).encode()
    data=subprocess.run(['git','cat-file','--batch'],input=request,capture_output=True,check=True,cwd=ROOT).stdout
    offset=0;changed=[];hashes=[]
    for path in protected:
        end=data.index(b'\n',offset);header=data[offset:end].split();size=int(header[-1]);baseline=data[end+1:end+1+size];offset=end+size+2
        actual=(ROOT/path).read_bytes()
        if actual!=baseline:changed.append(path)
        hashes.append(dict(path=path,sha256=hashlib.sha256(actual).hexdigest()))
    assert not changed,changed
    python_log=(ROOT/'.cache/v212/python-final.txt').read_text()
    summary=python_log.strip().splitlines()[-1];assert re.search(r'\d+ passed',summary) and 'failed' not in summary and 'error' not in summary
    go_log=(ROOT/'.cache/v212/go-final.txt').read_text();assert 'FAIL' not in go_log and 'ok' in go_log
    for package in ('csvio','psd','qam','tests'):assert re.search(r'/'+package+r'\s',go_log),package
    # Execute every Python fenced code example in a fresh namespace.
    os.environ['MPLBACKEND']='Agg';sys.path.insert(0,str(ROOT/'python'));os.chdir(ROOT)
    blocks=re.findall(r'```python\n(.*?)```',(ROOT/'python/API.md').read_text(encoding='utf-8'),re.S)
    for number,code in enumerate(blocks):
        exec(compile(code,f'python/API.md example {number+1}','exec'),{'__name__':'__api_example__'})
        import matplotlib.pyplot as plt
        plt.close('all')
    assert len(blocks)==6
    # Go documentation fragments are compiled/executed with explicit imports
    # and prepared recoveredSymbols/iq where documented as caller input.
    snippets=re.findall(r'```go\n(.*?)```',(ROOT/'go/API.md').read_text(encoding='utf-8'),re.S)
    outputs=[];tmp=ROOT/'.cache/v212'
    for number,code in enumerate(snippets):
        if code.startswith('package main'):source=code
        else:
            imports=[]
            for marker,pkg in [('fmt.','fmt'),('json.','encoding/json'),('strings.','strings'),('csvio.','github.com/xulu199705/psdana/go/csvio'),('psd.','github.com/xulu199705/psdana/go/psd'),('qam.','github.com/xulu199705/psdana/go/qam')]:
                if marker in code:imports.append(pkg)
            prepare=''
            if 'recoveredSymbols' in code:prepare='recoveredSymbols, _ := qam.GenerateConstellation(64)\n'
            if 'AnalyzeQAM(iq,' in code:
                if 'github.com/xulu199705/psdana/go/csvio' not in imports:imports.append('github.com/xulu199705/psdana/go/csvio')
                prepare='cc:=csvio.DefaultConfig();cc.SampleFormat="q15";d,e:=csvio.ReadCSV("../data/generated/qam/Q13_32768_q15.csv",cc);if e!=nil{return e};iq:=d.Complex\n'
            source='package main\nimport (\n'+''.join(json.dumps(p)+'\n' for p in imports)+')\nfunc run()error{\n'+prepare+code+'\nreturn nil\n}\nfunc main(){if e:=run();e!=nil{panic(e)}}\n'
        target=tmp/f'api_go_{number+1}.go';target.write_text(source,encoding='utf-8')
        p=subprocess.run(['go','run',str(target)],cwd=ROOT/'go',capture_output=True,text=True)
        assert p.returncode==0,(number,p.stderr);outputs.append(p.stdout.strip())
    result=dict(status='PASS',baseline_head=git('rev-parse','HEAD').decode().strip(),tags=git('tag','--list').decode().splitlines(),
        protected_file_count=len(protected),protected_files_changed=changed,protected_files=hashes,
        python_final_summary=summary,go_final_output=go_log,python_api_examples=len(blocks),go_api_examples=len(snippets),go_api_outputs=outputs,
        unrelated_untracked_files=['web/design.md'] if (ROOT/'web/design.md').exists() else [],
        scope='all HEAD-tracked data plus PSD/Power/CSV/packed-IQ/modules; Foundation changes explicitly limited to slicer and EVM-only scoring')
    (ROOT/'go/reports/v2.1.2_audit.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print('Frozen byte checks and API examples PASS',len(protected),len(blocks),len(snippets))

if __name__=='__main__':run()
