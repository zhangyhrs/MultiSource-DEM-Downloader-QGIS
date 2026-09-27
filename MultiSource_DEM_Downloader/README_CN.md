<div align="center">

# Multi-Source DEM Downloader for QGIS

**在 QGIS 中直接下载、拼接和裁剪多源 DEM/DSM 数据**

[🇺🇸 English](./README.md) · [**🇨🇳 中文**](./README_CN.md)

<img src="https://img.shields.io/badge/QGIS-3.x-589632?style=flat-square&logo=qgis&logoColor=white" />
<img src="https://img.shields.io/badge/Version-1.0.0-1565C0?style=flat-square" />
<img src="https://img.shields.io/badge/Python-PyQGIS-3776AB?style=flat-square&logo=python&logoColor=white" />
<img src="https://img.shields.io/badge/DEM-Multi--Source-00838F?style=flat-square" />

</div>

---

## 项目简介

**Multi-Source DEM Downloader（多源 DEM 下载器）** 是一款面向 QGIS 的多源高程数据下载插件，可根据研究区直接获取常用全球 DEM/DSM 数据，并完成下载、拼接、裁剪和加载，减少在多个数据网站之间切换及后续重复处理。

插件同时支持公开数据源和需要认证的官方数据服务，并根据所选数据源动态显示认证方式。账号信息默认仅保留在当前插件会话中。

## 数据源

| 数据集 | 分辨率 | 数据来源 | 认证方式 |
|---|---:|---|---|
| Copernicus DEM GLO-30 | 30 m | 公共云瓦片 | 无 |
| Copernicus DEM GLO-90 | 90 m | 公共云瓦片 | 无 |
| SRTM 1 Arc-Second | 约 30 m | NASA Earthdata / LP DAAC | Earthdata Login |
| SRTM 3 Arc-Second | 约 90 m | NASA Earthdata / LP DAAC | Earthdata Login |
| NASADEM | 约 30 m | NASA Earthdata / LP DAAC | Earthdata Login |
| ALOS AW3D30 | 约 30 m DSM | JAXA / EORC | JAXA ID + Password |

> 各平台的数据开放方式、认证规则和接口可能调整。插件遵循数据提供方的账号、许可和访问控制要求，不绕过认证或授权限制。

## 主要功能

- 使用当前地图范围作为研究区。
- 在 QGIS 地图窗口中直接绘制矩形范围。
- 使用当前面图层或选中要素确定范围。
- 支持外部 SHP / GPKG / GeoJSON。
- 自动计算涉及的 1° DEM 瓦片。
- 后台下载并显示进度，可取消任务。
- 针对国际数据服务提供自动重试和可选 HTTP/HTTPS 代理。
- 自动拼接并裁剪到研究区。
- 下载完成后自动加载到 QGIS。
- 可选择保留原始下载文件。
- 可选生成山体阴影。
- 可显示 1° × 1° DEM 格网。
- 采用与 QGIS 风格协调的紧凑折叠式界面。

## 账号与认证

### NASA Earthdata

SRTM 和 NASADEM 使用 **NASA Earthdata Login**。需要免费注册 Earthdata 账号，并根据实际数据服务完成 LP DAAC 相关应用授权。

### JAXA AW3D30

ALOS AW3D30 使用 JAXA/EORC 注册后提供的 ID 和 Password。针对访问 JAXA 服务器时可能出现的连接不稳定问题，插件提供重试和代理设置。

### 凭据处理

插件不会在源代码中写入用户账号、密码或密钥，默认也不会将认证信息保存到配置文件，只在当前插件会话中使用。

## 安装方法

### QGIS 官方插件库

正式发布后，可通过 **QGIS → 插件 → 管理并安装插件** 搜索安装。

### ZIP 安装

1. 下载插件 ZIP。
2. 打开 QGIS。
3. 进入 **插件 → 管理并安装插件 → 从 ZIP 安装**。
4. 选择 ZIP 文件并安装。
5. 在 QGIS 中打开 **Multi-Source DEM Downloader v1.0.0**。

## 项目链接

- GitHub：https://github.com/zhangyhrs/MultiSource-DEM-Downloader-QGIS
- Issues：https://github.com/zhangyhrs/MultiSource-DEM-Downloader-QGIS/issues
- 作者主页：https://github.com/zhangyhrs

---

## 相关平台

<table align="center">
  <tr>
    <th width="33%">微信公众号<br>测绘地信</th>
    <th width="33%">微信小程序<br>测绘地信</th>
    <th width="33%">知识星球<br>测绘地理信息共享中心</th>
  </tr>
  <tr>
    <td align="center"><img src="https://raw.githubusercontent.com/zhangyhrs/GeoStar-Selector-QGIS/main/assets/wechat-official-account.png" height="150"></td>
    <td align="center"><img src="https://raw.githubusercontent.com/zhangyhrs/GeoStar-Selector-QGIS/main/assets/wechat-mini-program.jpg" height="150"></td>
    <td align="center"><img src="https://raw.githubusercontent.com/zhangyhrs/GeoStar-Selector-QGIS/main/assets/knowledge-planet.jpg" height="150"></td>
  </tr>
</table>

<div align="center">

[![GitHub](https://img.shields.io/badge/GitHub-@zhangyhrs-181717?style=flat-square&logo=github&logoColor=white)](https://github.com/zhangyhrs)

</div>
