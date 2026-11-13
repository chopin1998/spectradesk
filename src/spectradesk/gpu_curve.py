"""OpenGL spectrum shaders and GPU-only ping-pong phosphor history."""
import ctypes as C
import math
import time
import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore,QtGui,QtOpenGL
from pyqtgraph.Qt import OpenGLHelpers,OpenGLConstants as GL
from pyqtgraph.graphicsItems.PlotCurveItem import OpenGLState

_native_gl=C.CDLL('libGL.so.1')
_native_gl.glGetIntegerv.argtypes=[C.c_uint,C.POINTER(C.c_int)]
_native_gl.glGetIntegerv.restype=None
_native_gl.glReadPixels.argtypes=[C.c_int,C.c_int,C.c_int,C.c_int,C.c_uint,C.c_uint,C.c_void_p]
_native_gl.glReadPixels.restype=None
def framebuffer_binding():
    value=C.c_int();_native_gl.glGetIntegerv(0x8CA6,C.byref(value));return value.value

GL_FRAMEBUFFER=0x8D40
GL_TEXTURE0=0x84C0
GL_TEXTURE_2D=0x0DE1

VERT='''#version 140
in vec4 a_position;
uniform mat4 u_mvp;
uniform float u_origin;
out float wavelength;
void main(){wavelength=a_position.x+u_origin;gl_Position=u_mvp*a_position;}
'''
FRAG='''#version 140
in float wavelength;
uniform vec4 u_color;
uniform int u_rainbow;
out vec4 fragColor;
vec3 rainbow(float t){
 if(t<0.15)return mix(vec3(144,104,233),vec3(101,136,255),clamp(t/0.15,0.,1.))/255.;
 if(t<0.25)return mix(vec3(101,136,255),vec3(72,213,236),(t-.15)/.10)/255.;
 if(t<0.375)return mix(vec3(72,213,236),vec3(120,229,157),(t-.25)/.125)/255.;
 if(t<0.5)return mix(vec3(120,229,157),vec3(229,228,114),(t-.375)/.125)/255.;
 if(t<0.625)return mix(vec3(229,228,114),vec3(243,170,103),(t-.5)/.125)/255.;
 if(t<0.8)return mix(vec3(243,170,103),vec3(237,110,117),(t-.625)/.175)/255.;
 return mix(vec3(237,110,117),vec3(174,85,107),clamp((t-.8)/.2,0.,1.))/255.;
}
void main(){fragColor=vec4(u_rainbow==1?rainbow((wavelength-380.)/400.):u_color.rgb,u_color.a);}
'''

SDF_VERT='''#version 140
in vec4 a_pos_normal;
in float a_edge;
uniform mat4 u_mvp;
uniform vec2 u_viewport;
uniform float u_half_width;
uniform float u_origin;
out float wavelength;
out float v_edge;
void main(){
 wavelength=a_pos_normal.x+u_origin;
 vec4 clip=u_mvp*vec4(a_pos_normal.xy,0.0,1.0);
 vec2 offset_px=vec2(a_pos_normal.z,-a_pos_normal.w)*u_half_width;
 clip.xy+=(offset_px/u_viewport)*2.0*clip.w;
 gl_Position=clip;
 v_edge=a_edge;
}
'''
SDF_FRAG='''#version 140
in float wavelength;
in float v_edge;
uniform vec4 u_color;
uniform int u_rainbow;
uniform int u_glow;
out vec4 fragColor;
vec3 rainbow(float t){
 if(t<0.15)return mix(vec3(144,104,233),vec3(101,136,255),clamp(t/0.15,0.,1.))/255.;
 if(t<0.25)return mix(vec3(101,136,255),vec3(72,213,236),(t-.15)/.10)/255.;
 if(t<0.375)return mix(vec3(72,213,236),vec3(120,229,157),(t-.25)/.125)/255.;
 if(t<0.5)return mix(vec3(120,229,157),vec3(229,228,114),(t-.375)/.125)/255.;
 if(t<0.625)return mix(vec3(229,228,114),vec3(243,170,103),(t-.5)/.125)/255.;
 if(t<0.8)return mix(vec3(243,170,103),vec3(237,110,117),(t-.625)/.175)/255.;
 return mix(vec3(237,110,117),vec3(174,85,107),clamp((t-.8)/.2,0.,1.))/255.;
}
void main(){
 vec3 base=u_rainbow==1?rainbow((wavelength-380.)/400.):u_color.rgb;
 float d=abs(v_edge);
 float core=1.0-smoothstep(0.0,0.75,d);
 if(u_glow==1){
  float halo=exp(-3.8*d*d);
  vec3 col=mix(base,vec3(0.88,1.0,0.95),core*0.32);
  fragColor=vec4(col,u_color.a*clamp(core*0.88+halo*0.38,0.,1.));
 }else{
  fragColor=vec4(base,u_color.a*core);
 }
}
'''
QUAD_VERT='''#version 140
in vec4 a_position;
out vec2 uv;
void main(){gl_Position=a_position;uv=a_position.xy*.5+.5;}
'''
QUAD_FRAG='''#version 140
uniform sampler2D u_texture;
uniform float u_decay;
in vec2 uv;
out vec4 fragColor;
void main(){fragColor=texture(u_texture,uv)*u_decay;}
'''

def shader_sources(context):
    """Match GLSL syntax to the actual context, including Wayland/EGL ES."""
    if not context.isOpenGLES() and context.format().version()>=(3,1):
        return VERT,FRAG,QUAD_VERT,QUAD_FRAG,SDF_VERT,SDF_FRAG
    es=context.isOpenGLES()
    version='#version 100' if es else '#version 120'
    precision='\nprecision highp float;\nprecision highp int;' if es else ''
    def vertex(source):
        return (source.replace('#version 140',version+precision)
                .replace('in vec4 a_position','attribute vec4 a_position')
                .replace('in vec4 a_pos_normal','attribute vec4 a_pos_normal')
                .replace('in float a_edge','attribute float a_edge')
                .replace('out float wavelength','varying float wavelength')
                .replace('out float v_edge','varying float v_edge')
                .replace('out vec2 uv','varying vec2 uv'))
    def fragment(source):
        return (source.replace('#version 140',version+precision)
                .replace('in float wavelength','varying float wavelength')
                .replace('in float v_edge','varying float v_edge')
                .replace('in vec2 uv','varying vec2 uv')
                .replace('out vec4 fragColor;','')
                .replace('fragColor=','gl_FragColor=')
                .replace('texture(u_texture,uv)','texture2D(u_texture,uv)'))
    return vertex(VERT),fragment(FRAG),vertex(QUAD_VERT),fragment(QUAD_FRAG),vertex(SDF_VERT),fragment(SDF_FRAG)

def compile_program(widget,key,vert,frag,attrs=(('a_position',0),)):
    program=widget.retrieveProgram(key)
    if program is None:
        program=QtOpenGL.QOpenGLShaderProgram()
        for kind,source in [(QtOpenGL.QOpenGLShader.ShaderTypeBit.Vertex,vert),(QtOpenGL.QOpenGLShader.ShaderTypeBit.Fragment,frag)]:
            if not program.addShaderFromSourceCode(kind,source):raise RuntimeError(program.log())
        for name,idx in attrs:
            program.bindAttributeLocation(name,idx)
        if not program.link():raise RuntimeError(program.log())
        widget.storeProgram(key,program)
    return program

class SpectrumState(OpenGLState):
    def __init__(self,widget):
        super().__init__(widget)
        self.targets=[];self.history_key=None;self.last_time=None;self.serial=-1
        self.quad_vao=QtOpenGL.QOpenGLVertexArrayObject(widget)
        self.quad_vbo=QtOpenGL.QOpenGLBuffer(QtOpenGL.QOpenGLBuffer.Type.VertexBuffer)
        self.sdf_vao=QtOpenGL.QOpenGLVertexArrayObject(widget)
        self.sdf_vbo=QtOpenGL.QOpenGLBuffer(QtOpenGL.QOpenGLBuffer.Type.VertexBuffer)
    def setup(self,context):
        if self.context is context:return
        if self.context is not None:
            self.context.aboutToBeDestroyed.disconnect(self.cleanup)
            self.cleanup()
        widget=self.parent()
        vert,frag,quad_vert,quad_frag,sdf_vert,sdf_frag=shader_sources(context)
        program=compile_program(widget,'SpectraDeskSpectrum',vert,frag)
        compile_program(widget,'SpectraDeskTexture',quad_vert,quad_frag)
        sdf_prog=compile_program(widget,'SpectraDeskSdf',sdf_vert,sdf_frag,(('a_pos_normal',0),('a_edge',1)))
        self.m_vao.create();self.m_vbo.create();self.m_vao.bind();self.m_vbo.bind()
        program.enableAttributeArray(0);program.setAttributeBuffer(0,GL.GL_FLOAT,0,2)
        self.m_vbo.release();self.m_vao.release()
        self.sdf_vao.create();self.sdf_vbo.create();self.sdf_vao.bind();self.sdf_vbo.bind()
        sdf_prog.enableAttributeArray(0);sdf_prog.setAttributeBuffer(0,GL.GL_FLOAT,0,4,20)
        sdf_prog.enableAttributeArray(1);sdf_prog.setAttributeBuffer(1,GL.GL_FLOAT,16,1,20)
        self.sdf_vbo.release();self.sdf_vao.release()
        self.quad_vao.create();self.quad_vbo.create();self.quad_vao.bind();self.quad_vbo.bind()
        vertices=np.array([[-1,-1],[1,-1],[-1,1],[1,1]],dtype=np.float32)
        self.quad_vbo.allocate(vertices,vertices.nbytes)
        quad=widget.retrieveProgram('SpectraDeskTexture')
        quad.enableAttributeArray(0);quad.setAttributeBuffer(0,GL.GL_FLOAT,0,2)
        self.quad_vbo.release();self.quad_vao.release()
        self.context=context;context.aboutToBeDestroyed.connect(self.cleanup)
    def cleanup(self):
        widget=self.parent();widget.makeCurrent()
        self.targets=[];self.history_key=None;self.last_time=None;self.serial=-1
        self.quad_vao.destroy();self.quad_vbo.destroy()
        self.sdf_vao.destroy();self.sdf_vbo.destroy()
        super().cleanup()

class ProgramProxy:
    def __init__(self,widget):self.widget=widget
    def __getattr__(self,name):return getattr(self.widget,name)
    def retrieveProgram(self,key):
        return self.widget.retrieveProgram('SpectraDeskSpectrum' if key=='PlotCurveItem' else key)

class GpuSpectrumCurve(pg.PlotCurveItem):
    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        self.curve=self # Same curve access as PlotDataItem for existing diagnostics.
        self.effect=0;self.serial=0;self.last_error=None
    def capture_viewport(self,widget):
        """Read the last painted Qt FBO without invoking grabFramebuffer's repaint."""
        if self.glstate is None:return QtGui.QImage()
        widget.makeCurrent();gl=widget.getFunctions();previous=framebuffer_binding()
        try:
            gl.glBindFramebuffer(GL_FRAMEBUFFER,self.glstate.output_fbo)
            ratio=widget.devicePixelRatioF();w=round(widget.width()*ratio);h=round(widget.height()*ratio)
            pixels=np.empty((h,w,4),dtype=np.uint8)
            _native_gl.glReadPixels(0,0,w,h,0x1908,0x1401,pixels.ctypes.data)
            pixels=pixels[::-1].copy()
            image=QtGui.QImage(pixels.data,w,h,w*4,QtGui.QImage.Format.Format_RGBA8888).copy()
            image.setDevicePixelRatio(ratio)
            return image
        finally:
            gl.glBindFramebuffer(GL_FRAMEBUFFER,previous);widget.doneCurrent()
    def setData(self,*args,**kwargs):
        super().setData(*args,**kwargs)
        self.serial=getattr(self,'serial',0)+1
    def setBrush(self,brush):
        # GPU shader supplies wavelength color; retain the fill opacity.
        if isinstance(brush,QtGui.QBrush) and brush.gradient() is not None:
            brush=pg.mkBrush(255,255,255,65)
        super().setBrush(brush)
    def paint(self,painter,option,widget):
        if self.xData is None or len(self.xData)<2:return
        if not isinstance(widget,OpenGLHelpers.GraphicsViewGLWidget):return super().paint(painter,option,widget)
        if self.glstate is None:
            self.glstate=SpectrumState(widget)
            self.sigPlotChanged.connect(self.glstate.verticesChanged)
        painter.beginNativePainting()
        self.glstate.output_fbo=framebuffer_binding()
        try:
            self.paintGL(widget)
            self.last_error=None
        except Exception as error:
            if self.last_error is None:
                import traceback
                traceback.print_exc()
            self.last_error=str(error)
        finally:
            widget.getFunctions().glBindFramebuffer(GL_FRAMEBUFFER,self.glstate.output_fbo)
            painter.endNativePainting()
    def draw_sdf_ribbon(self,widget,glow=False,color_override=None,half_width=2.8):
        if (view:=self.getViewBox()) is None:return
        state=self.glstate;state.setup(widget.context());gl=widget.getFunctions()
        prog=widget.retrieveProgram('SpectraDeskSdf');prog.bind()
        center=self.boundingRect().center();xc,yc=float(center.x()),float(center.y())
        proj=QtGui.QMatrix4x4();proj.ortho(widget.rect())
        tr=self.sceneTransform();tr.translate(xc,yc)
        mvp=proj*QtGui.QMatrix4x4(tr)
        vr=view.viewRange();vb_rect=view.sceneBoundingRect()
        vw=float(max(16.,vb_rect.width()));vh=float(max(16.,vb_rect.height()))
        x=np.asarray(self.xData,dtype=np.float32)-np.float32(xc)
        y=np.asarray(self.yData,dtype=np.float32)-np.float32(yc)
        finite=np.isfinite(x)&np.isfinite(y)
        if not np.all(finite):
            x=x[finite];y=y[finite]
        n=x.size
        if n<2:prog.release();return
        span_x=np.float32(max(abs(vr[0][1]-vr[0][0]),1e-9))
        span_y=np.float32(max(abs(vr[1][1]-vr[1][0]),1e-9))
        dx_px=np.empty(n,dtype=np.float32);dy_px=np.empty(n,dtype=np.float32)
        dx_px[:-1]=(x[1:]-x[:-1])*(np.float32(vw)/span_x);dx_px[-1]=dx_px[-2]
        dy_px[:-1]=(y[1:]-y[:-1])*(np.float32(vh)/span_y);dy_px[-1]=dy_px[-2]
        inv_len=np.float32(1.)/np.maximum(np.hypot(dx_px,dy_px),np.float32(1e-6))
        nx=-dy_px*inv_len;ny=dx_px*inv_len
        verts=np.empty((n*2,5),dtype=np.float32)
        verts[0::2,0]=x;verts[0::2,1]=y;verts[0::2,2]=nx;verts[0::2,3]=ny;verts[0::2,4]=1.
        verts[1::2,0]=x;verts[1::2,1]=y;verts[1::2,2]=-nx;verts[1::2,3]=-ny;verts[1::2,4]=-1.
        state.sdf_vao.bind();state.sdf_vbo.bind()
        state.sdf_vbo.allocate(verts,verts.nbytes)
        OpenGLHelpers.setUniformValue(prog,'u_mvp',mvp)
        OpenGLHelpers.setUniformValue(prog,'u_viewport',QtGui.QVector2D(float(max(1,widget.width())),float(max(1,widget.height()))))
        gl.glUniform1f(prog.uniformLocation('u_half_width'),float(half_width))
        gl.glUniform1f(prog.uniformLocation('u_origin'),float(xc))
        gl.glUniform1i(prog.uniformLocation('u_rainbow'),int(self.effect in (1,2)))
        gl.glUniform1i(prog.uniformLocation('u_glow'),int(glow))
        c=color_override or self.opts['pen'].color()
        OpenGLHelpers.setUniformValue(prog,'u_color',QtGui.QVector4D(c.redF(),c.greenF(),c.blueF(),c.alphaF()))
        gl.glDrawArrays(GL.GL_TRIANGLE_STRIP,0,verts.shape[0])
        state.sdf_vbo.release();state.sdf_vao.release();prog.release()
    def draw_spectrum(self,widget):
        state=self.glstate;state.setup(widget.context())
        program=widget.retrieveProgram('SpectraDeskSpectrum');program.bind()
        # Match the origin that the upstream VBO uploader chooses.
        origin=self.boundingRect().center().x() if state.render_cache is None else state.render_cache[0]
        widget.getFunctions().glUniform1f(program.uniformLocation('u_origin'),float(origin))
        widget.getFunctions().glUniform1i(program.uniformLocation('u_rainbow'),int(self.effect in (1,2)))
        super().paintGL(ProgramProxy(widget))
    def texture_quad(self,widget,texture,decay):
        state=self.glstate;gl=widget.getFunctions();program=widget.retrieveProgram('SpectraDeskTexture')
        program.bind();gl.glUniform1i(program.uniformLocation('u_texture'),7);gl.glUniform1f(program.uniformLocation('u_decay'),float(decay))
        gl.glActiveTexture(GL_TEXTURE0+7);gl.glBindTexture(GL_TEXTURE_2D,texture)
        if hasattr(gl,'glBindSampler'):gl.glBindSampler(7,0)
        gl.glTexParameteri(GL_TEXTURE_2D,0x2801,0x2601);gl.glTexParameteri(GL_TEXTURE_2D,0x2800,0x2601)
        gl.glTexParameteri(GL_TEXTURE_2D,0x2802,0x812F);gl.glTexParameteri(GL_TEXTURE_2D,0x2803,0x812F)
        state.quad_vao.bind();gl.glDrawArrays(GL.GL_TRIANGLE_STRIP,0,4);state.quad_vao.release()
        gl.glBindTexture(GL_TEXTURE_2D,0);gl.glActiveTexture(GL_TEXTURE0)
    def paintGL(self,widget):
        state=self.glstate;state.setup(widget.context())
        if self.effect!=3:
            state.history_key=None
            return self.draw_spectrum(widget)
        gl=widget.getFunctions();dpr=widget.devicePixelRatioF()
        size=QtCore.QSize(round(widget.width()*dpr),round(widget.height()*dpr))
        view=self.getViewBox();key=(size.width(),size.height(),tuple(view.viewRange()[0]),tuple(view.viewRange()[1]),view.sceneBoundingRect())
        changed=key!=state.history_key
        if not state.targets or state.targets[0].size()!=size:
            state.targets=[QtOpenGL.QOpenGLFramebufferObject(size) for _ in range(2)]
            if not all(f.isValid() for f in state.targets):raise RuntimeError('Cannot allocate phosphor framebuffer')
            changed=True
        if changed or state.serial!=self.serial:
            now=time.monotonic();previous,target=state.targets
            target.bind();gl.glViewport(0,0,size.width(),size.height())
            gl.glDisable(GL.GL_SCISSOR_TEST);gl.glDisable(GL.GL_BLEND)
            gl.glClearColor(0,0,0,0);gl.glClear(GL.GL_COLOR_BUFFER_BIT)
            if not changed and state.last_time is not None:
                self.texture_quad(widget,previous.texture(),math.exp(-(now-state.last_time)/.55))
            # Single-pass GPU SDF glow + bright core directly into the phosphor FBO texture
            color=QtGui.QColor('#8affce');color.setAlphaF(0.92)
            gl.glEnable(GL.GL_BLEND);gl.glBlendFunc(GL.GL_SRC_ALPHA,1)
            self.draw_sdf_ribbon(widget,glow=True,color_override=color,half_width=3.6)
            state.targets=[target,previous];state.serial=self.serial;state.history_key=key;state.last_time=now
        gl.glBindFramebuffer(GL_FRAMEBUFFER,self.glstate.output_fbo)
        gl.glViewport(0,0,size.width(),size.height());widget.setViewboxClip(view)
        gl.glEnable(GL.GL_BLEND);gl.glBlendFunc(1,GL.GL_ONE_MINUS_SRC_ALPHA)
        self.texture_quad(widget,state.targets[0].texture(),1.)
        gl.glDisable(GL.GL_BLEND)
