import os
from pathlib import Path
import subprocess
import sys
import pytest


@pytest.mark.skipif(os.environ.get('SPECTRADESK_TEST_OPENGL')!='1',reason='Requires a real desktop OpenGL context; opt in explicitly')
def test_real_gpu_pixels_and_history():
    root=Path(__file__).parents[1]
    env=dict(os.environ,QT_QPA_PLATFORM='xcb',PYTHONDONTWRITEBYTECODE='1')
    result=subprocess.run([sys.executable,str(root/'tools/verify_gpu_rendering.py')],cwd=root,env=env,capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr
