from pathlib import Path
import subprocess


def test_javascript_syntax():
    root=Path(__file__).resolve().parents[1]
    proc=subprocess.run(['node','--check',str(root/'static/app.js')],capture_output=True,text=True)
    assert proc.returncode==0,proc.stderr
