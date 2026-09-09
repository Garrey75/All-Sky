# All-Sky · OrgPi 天文拍摄系统

在 **Orange Pi**（橙派）上运行的无线天文摄影控制器，工作流对标 [ZWO ASIAIR](https://www.zwoastro.com/)：手机/平板浏览器里完成设备连接、预览、极轴、解析居中、导星、对焦、自动序列和多目标计划拍摄。

默认带完整 **硬件模拟器**，没有相机和赤道仪也能把整晚流程跑通。Orange Pi 上若已安装 [INDI](https://indilib.org/)，设置 `ALLSKY_INDI_HOST` 即可把赤道仪/相机切到真实设备。

## 功能对照

| ASIAIR | All-Sky OrgPi |
| --- | --- |
| 预览曝光 / 直方图 / BIN / 增益 | 有 |
| 极轴校准（全天解析） | 有，方位/高度误差与微调箭头 |
| 解析 + Sync + GoTo 居中 | 有 |
| 星图 / 目标库 | Messier + 常用 NGC + 亮星，今夜最佳 |
| 多星导星曲线 | 有（模拟 PHD 风格 RMS） |
| 辅助对焦 / 自动对焦 V 曲线 | 有 |
| Autorun 序列 | LIGHT + 滤镜轮 + 抖动 |
| PLAN 多目标 | 今夜高度排序后依次拍摄 |
| 实时叠加 | 有 |
| 行星短曝光 | 有 |
| 滤镜轮 / 电调焦 / 4 路 12V | 有（模拟电源口） |
| 相册 FITS | 写入 `data/images/` |
| INDI 赤道仪/相机 | 可选 |

## 快速开始

```bash
# 后端
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m pytest
cd ..

# 前端
cd frontend
npm install
npm run build
cd ..

# 同时提供 API 与界面（构建后）
cd backend && python -m uvicorn app.main:app --host 0.0.0.0 --port 8080
# 打开 http://<orangepi-ip>:8080
```

开发时也可分开跑：后端 8080，前端 `npm run dev`（Vite 会把 `/api` 和 `/ws` 代理过去）。

## Orange Pi 部署

在 Armbian / Orange Pi OS（Ubuntu）上：

```bash
sudo bash deploy/orangepi/install.sh
```

脚本会安装 Python、构建前端、安装 systemd 服务 `allsky`，开机自启，默认监听 **8080**。

用 Docker：

```bash
docker compose up --build
```

真实设备：先在本机启动 INDI 服务（例如 `indiserver -v indi_simulator_ccd indi_simulator_telescope` 或对应厂商驱动），然后：

```bash
export ALLSKY_INDI_HOST=127.0.0.1
export ALLSKY_INDI_PORT=7624
```

## 推荐器材参数

界面里填写主镜焦距、口径、导星镜焦距，解析与导星像素比才准确。默认模拟套装：

- 主相机 OrgCam 2600MC（3.76 μm）
- 导星相机 120MM Mini
- 赤道仪 AM5 风格谐波
- EAF + 7 档滤镜轮

## 目录

```
backend/app/     FastAPI + 天文算法 + 模拟器
frontend/src/    移动优先 Web 控制台
deploy/orangepi/ systemd 安装
data/images/     拍摄的 FITS
```

## 许可证

项目代码以仓库 LICENSE 为准；Messier 坐标为公有领域星表数据。
