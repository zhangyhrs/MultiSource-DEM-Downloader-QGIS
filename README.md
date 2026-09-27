<div align="center">

# Multi-Source DEM Downloader for QGIS

**Download, mosaic and clip multi-source DEM/DSM datasets directly in QGIS**

[**🇺🇸 English**](./README.md) · [🇨🇳 中文](./README_CN.md)

<img src="https://img.shields.io/badge/QGIS-3.x-589632?style=flat-square&logo=qgis&logoColor=white" />
<img src="https://img.shields.io/badge/Version-1.0.0-1565C0?style=flat-square" />
<img src="https://img.shields.io/badge/Python-PyQGIS-3776AB?style=flat-square&logo=python&logoColor=white" />
<img src="https://img.shields.io/badge/DEM-Multi--Source-00838F?style=flat-square" />

</div>

---

## Overview

**Multi-Source DEM Downloader** is a QGIS plugin for obtaining global DEM/DSM data directly by study area. It integrates several commonly used elevation products into one compact QGIS dock, reducing the need to switch between multiple download websites and then manually mosaic, clip and reload data.

The plugin supports public cloud datasets as well as authenticated official services. Authentication fields are shown dynamically according to the selected source, and credentials are kept only in the current plugin session.

## Supported datasets

| Dataset | Resolution | Provider / access | Authentication |
|---|---:|---|---|
| Copernicus DEM GLO-30 | 30 m | Public cloud tiles | None |
| Copernicus DEM GLO-90 | 90 m | Public cloud tiles | None |
| SRTM 1 Arc-Second | ~30 m | NASA Earthdata / LP DAAC | Earthdata Login |
| SRTM 3 Arc-Second | ~90 m | NASA Earthdata / LP DAAC | Earthdata Login |
| NASADEM | ~30 m | NASA Earthdata / LP DAAC | Earthdata Login |
| ALOS AW3D30 | ~30 m DSM | JAXA / EORC | JAXA ID + Password |

> Availability, authentication rules and provider endpoints may change. The plugin follows provider access controls and does not bypass licensing or authentication requirements.

## Features

- AOI from current map extent.
- Interactive rectangle drawing directly on the QGIS map canvas.
- AOI from the active polygon layer or selected features.
- External SHP / GPKG / GeoJSON extent input.
- Automatic 1° tile calculation and coverage preview.
- Background download with progress and cancel support.
- Network retry and optional HTTP/HTTPS proxy for unstable international connections.
- Automatic mosaicking and clipping to the study area.
- Automatic loading of the result into QGIS.
- Optional retention of original downloaded files.
- Optional hillshade generation.
- Optional 1° × 1° DEM grid display.
- Compact collapsible interface styled to match QGIS.

## Authentication

### NASA Earthdata

SRTM and NASADEM use **NASA Earthdata Login** credentials. A free Earthdata account is required, and the corresponding LP DAAC application may need to be authorized before programmatic download.

### JAXA AW3D30

ALOS AW3D30 uses the account information provided after registration with JAXA/EORC. The plugin accepts the JAXA ID and password and includes retry/proxy options for unstable connections.

### Credential handling

Credentials are not hard-coded into the source code and are not written to the plugin configuration by default. They are retained only for the current plugin session.

## Installation

### QGIS Plugin Repository

After publication, install from **QGIS → Plugins → Manage and Install Plugins**.

### Manual installation

1. Download the plugin ZIP package.
2. Open QGIS.
3. Go to **Plugins → Manage and Install Plugins → Install from ZIP**.
4. Select the ZIP package.
5. Open **Multi-Source DEM Downloader v1.0.0** from the QGIS interface.

## Repository structure

```text
MultiSource_DEM_Downloader/
├── __init__.py
├── plugin.py
├── metadata.txt
├── icon.png
├── README.md
├── README_CN.md
├── CHANGELOG.md
└── LICENSE
```

## Links

- GitHub repository: https://github.com/zhangyhrs/MultiSource-DEM-Downloader-QGIS
- Issues: https://github.com/zhangyhrs/MultiSource-DEM-Downloader-QGIS/issues
- GitHub profile: https://github.com/zhangyhrs

---

## Connect

<table align="center">
  <tr>
    <th width="33%">WeChat Official Account<br>微信公众号：测绘地信</th>
    <th width="33%">WeChat Mini Program<br>微信小程序：测绘地信</th>
    <th width="33%">Knowledge Planet<br>知识星球：测绘地理信息共享中心</th>
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
