# 绘图实验

实验分支：`experiment/gpu-rendering`。稳定基线：`836bb95`。

## 运行

```sh
./run.sh --demo                           # 普通绘制，可选择“荧光余辉”
./run.sh --demo --renderer opengl          # OpenGL 单色实验
./run.sh --demo --renderer cached-image    # 曲线先缓存为图像的对照
```

OpenGL 目前只开放单色线，避免现有 pyqtgraph 的单色着色器破坏彩虹渐变。
荧光余辉在普通后端使用透明图像保存历史亮度；时间常数 0.55 秒，每次新光谱到达时衰减历史并叠加当前轨迹。停止采集后保持最后画面。坐标范围变化时清空历史，避免旧图错位。它是显示效果，不用于分析或导出；当前曲线仍保留全部 2048 个点。

## 对比方法

有桌面显示环境时运行：

```sh
uv run python tools/benchmark_renderers.py raster
uv run python tools/benchmark_renderers.py opengl
uv run python tools/benchmark_renderers.py cached-image
```

程序只使用模拟数据，不连接光谱仪，设置保存在临时目录。
每项先预热 12 帧，再测 50 帧，每帧改变数据并强制重绘；OpenGL 每帧执行 glFinish，确认 GPU 实际完成绘制，而不是只统计提交命令的时间。关闭 swap interval；因此该结果不是正常桌面垂直同步下的显示帧率。

2026-11-11，本机 NVIDIA RTX 2080 Ti / OpenGL 4.6 / NVIDIA 610.57.04，1180×760 窗口，2048 点、平滑 1、叠加原始曲线。以下为一次对比运行，单位 ms/帧：

| 单色线场景 | 普通 CPU 时间 / 实际耗时 | 图像缓存 CPU 时间 / 实际耗时 | OpenGL CPU 时间 / 实际耗时 |
| --- | --- | --- | --- |
| 主峰 | 5.98 / 4.59 | 6.11 / 4.71 | 2.53 / 2.55 |
| 暗场噪声 | 6.55 / 4.66 | 5.75 / 3.95 | 1.84 / 1.86 |

CPU 时间统计进程各线程合计，可能大于墙钟实际耗时。数据只说明本机本次模拟重绘的开销，不代表 USB 实机长时间采集的 CPU 降幅。之前 offscreen 的结果与真实桌面结果不能直接混用。

同次普通后端荧光余辉约 5.5–6.9 ms/帧，比无余辉效果更费资源。图像缓存使用 Qt 的 DeviceCoordinateCache；它能帮助重复展示不变的内容，但每帧数据变化时仍需重新生成缓存，收益有限。这不是对所有手写贴图实现的定论。

Vulkan 未实现或测试。下一步应先验证 OpenGL 单色的实机稳定性，再决定是否为彩虹和荧光余辉另做着色器；目前不改变默认后端。
