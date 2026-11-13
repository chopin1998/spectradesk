import os
from pathlib import Path
import subprocess
import sys
import pytest


@pytest.mark.skipif(os.environ.get('SPECTRADESK_TEST_OPENGL')!='1',reason='Requires a real desktop OpenGL context; opt in explicitly')
@pytest.mark.parametrize('api',['desktop','es'])
def test_real_gpu_pixels_and_history(api):
    root=Path(__file__).parents[1]
    env=dict(os.environ,QT_QPA_PLATFORM='xcb',PYTHONDONTWRITEBYTECODE='1',SPECTRADESK_TEST_GL_API=api)
    if api=='es':env['QT_XCB_GL_INTEGRATION']='xcb_egl'
    result=subprocess.run([sys.executable,str(root/'tools/verify_gpu_rendering.py')],cwd=root,env=env,capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr


@pytest.mark.skipif(os.environ.get('SPECTRADESK_TEST_OPENGL')!='1',reason='Requires a real desktop OpenGL context')
def test_shared_workbench_gpu_views():
    root=Path(__file__).parents[1]
    result=subprocess.run([sys.executable,str(root/'tools/verify_workbench_gpu.py')],cwd=root,env=dict(os.environ,QT_QPA_PLATFORM='xcb'),capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr


@pytest.mark.parametrize('es,version', [(False,(3,1)), (False,(2,1)), (True,(3,0))])
def test_shader_smoothstep_has_defined_edges(es, version):
    # Reversed constant edges are undefined by GLSL, even if one driver renders them.
    import re
    from types import SimpleNamespace
    from spectradesk.gpu_curve import shader_sources
    context=SimpleNamespace(isOpenGLES=lambda:es,
        format=lambda:SimpleNamespace(version=lambda:version))
    calls=[]
    for source in shader_sources(context):
        calls.extend(re.findall(r'smoothstep\(\s*([0-9.]+)\s*,\s*([0-9.]+)\s*,',source))
    assert calls, 'No smoothstep coverage'
    for low,high in calls:
        assert float(low)<float(high), f'Undefined GLSL smoothstep edges: {low}, {high}'
