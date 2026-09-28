# Mac 净化器伴侣

免费开源的原生 macOS 菜单栏工具：监测 Mac 状态，手动调节小米净化器风量，或按 CPU 温度自动联动。

**[下载最新版 → Releases](https://github.com/rockythink/mac-purifier-companion/releases)**

<img width="1292" height="1426" alt="CleanShot 2026-09-20 at 10 39 58@2x" src="https://github.com/user-attachments/assets/f73ad9b7-2e98-48d9-8e2c-5227568c6f44" />
<img width="2184" height="1624" alt="CleanShot 2026-09-20 at 10 41 25@2x" src="https://github.com/user-attachments/assets/d589c1d3-81c2-4426-9578-09e7dd980650" />


## 本分支：空气净化器 3（MIoT）

基于 rockythink 的原项目，保留 GPL-3.0-only 许可证和上游历史。

- 新增 `zhimi.airpurifier.ma4` 的本地 MIoT 接入，继续使用米家扫码配对。
- 最爱档位按机型显示：ma4 为 0–14，旧协议机型仍为 0–17；0 不是关机。
- 统一模式值，支持恢复接管前的自动、睡眠、最爱或手动三档模式。
- HA 或米家改变受监测的开关、模式、最爱档位后，沿用原有暂停接管机制。
- 已通过 76 项 Python 测试；ma4 的实机配对、调档和转速回读仍待验证。
- 本分支暂未发布安装包。下方上游 Releases 不含本次适配。

### Home Assistant 方案评估

目前查看到的 ma4 HA 实体提供开关、四种模式及三档风速，没有暴露最爱档位与 RPM。标准 fan 接口不能直接替代本应用的精细调档与转速回读，因此本次先补 MIoT 直连，不修改 HA 配置。

HA 后端可后续独立实现：通过 REST/WebSocket 控制实体，凭据放入系统钥匙串；仅展示实体实际支持的能力，缺少 RPM 时显示未提供，不能用百分比伪造转速。若要实现精细最爱档位，需先核查 HA 集成是否能提供对应属性或服务。

已有 HA 自动化可能改变设备状态；检测到受监测状态变化时本应用暂停，不自动抢回控制。两次轮询间的短暂变化或写入相同值无法据此识别。

## 功能

- **菜单栏实时状态**：CPU 温度、负载、内存、风扇转速，净化器实测 RPM
- **手动控制**：按机型 0–14 / 0–17 档最爱模式直调，支持静音/均衡/散热模板及个人预设
- **自动联动**：CPU 温度超过阈值且持续满足条件后自动调节净化器档位，降温后恢复
- **联动对照图**：CPU 温度与净化器转速共享时间轴，直观看清联动效果
- **历史趋势**：本机 30 天温度、负载、内存、风扇、净化器转速记录
- **实物设备图**：Mac 与净化器显示真实产品照片，非线条图标
- **不配对也能用**：仅监测 Mac 本机状态，无需连接米家

## 平台

- Apple Silicon / macOS 14+
- 已实机验证：Apple M4 / macOS 27 + 小米空气净化器 2 (`zhimi.airpurifier.m1`)
- 其他旧版 miIO 协议净化器为 SDK 候选范围，未逐一实机验证

## 安装

1. 从 [Releases](https://github.com/rockythink/mac-purifier-companion/releases) 下载 `.dmg`
2. 拖入「应用程序」，从「应用程序」启动
3. 可选：用 `SHA256SUMS` 校验文件完整性

应用显示名为 **Mac 净化器伴侣**；Bundle ID 和安装路径保留 `MacFanLink`，不影响使用。

## 从源码构建

```bash
# 需要：macOS 14+、Swift 6.3、uv、macmon 0.8.2、Python 3.12（uv 可自动管理）
git clone https://github.com/rockythink/mac-purifier-companion.git
cd mac-purifier-companion
bash scripts/build_app.sh        # 产出 dist/MacFanLink.app
bash scripts/package_distribution.sh  # 产出 DMG + 源码包
```

## 详细文档

完整的功能规格、安全边界、隐私说明、兼容性范围见 [REQUIREMENTS.md](REQUIREMENTS.md)。

## 许可证

[GPL-3.0-only](LICENSE)。第三方组件、图片和商标的权利见 [第三方声明](Resources/ThirdPartyNotices.txt)。
