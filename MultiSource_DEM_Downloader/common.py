# -*- coding: utf-8 -*-
import math
import os
import tempfile
import json
import time
import shutil
import http.cookiejar
import urllib.parse
import urllib.request
import urllib.error

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import re
import zipfile
import tarfile
from pathlib import Path

from qgis.PyQt.QtCore import Qt, QLocale, QObject, QThread, pyqtSignal, pyqtSlot, QUrl
from qgis.PyQt.QtGui import QColor, QIcon, QDesktopServices
from qgis.PyQt.QtWidgets import (
    QAction, QButtonGroup, QCheckBox, QComboBox, QDockWidget, QFileDialog,
    QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QProgressBar,
    QPushButton, QRadioButton, QScrollArea, QSizePolicy, QToolButton,
    QVBoxLayout, QWidget
)
from qgis.core import (
    Qgis, QgsCoordinateReferenceSystem, QgsCoordinateTransform,
    QgsGeometry, QgsMessageLog, QgsProject, QgsRasterLayer, QgsRectangle,
    QgsVectorLayer, QgsWkbTypes
)
from qgis.gui import QgsMapToolEmitPoint, QgsRubberBand
import processing

PLUGIN_DIR = os.path.dirname(__file__)
PLUGIN_VERSION = '1.0.0'
ICON_PATH = os.path.join(PLUGIN_DIR, 'icon.png')
LOG_TAG = 'DEM Downloader'

BASEMAPS = {
    'Esri World Imagery': ('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', 19),
    'OpenStreetMap Standard': ('https://tile.openstreetmap.org/{z}/{x}/{y}.png', 19),
    'OpenTopoMap': ('https://a.tile.opentopomap.org/{z}/{x}/{y}.png', 17),
}

SOURCES = {
    'Copernicus DEM GLO-30': {'kind':'aws', 'bucket':'copernicus-dem-30m', 'arcsec':'10', 'res':'30 m', 'type':'DSM', 'coverage':'Global land (public AWS)', 'auth':'none'},
    'Copernicus DEM GLO-90': {'kind':'aws', 'bucket':'copernicus-dem-90m', 'arcsec':'30', 'res':'90 m', 'type':'DSM', 'coverage':'Global land (public AWS)', 'auth':'none'},
    'SRTM 1 Arc-Second V003 (NASA Earthdata)': {'kind':'nasa', 'short_name':'SRTMGL1', 'version':'003', 'res':'30 m', 'type':'DEM', 'coverage':'~60°N–56°S', 'auth':'earthdata'},
    'NASADEM 1 Arc-Second V001 (NASA Earthdata)': {'kind':'nasa', 'short_name':'NASADEM_HGT', 'version':'001', 'res':'30 m', 'type':'DEM', 'coverage':'~60°N–56°S', 'auth':'earthdata'},
    'ALOS AW3D30 (JAXA Official)': {'kind':'jaxa', 'res':'30 m', 'type':'DSM', 'coverage':'Global land (~82°N–82°S)', 'auth':'jaxa'},
    'SRTM 3 Arc-Second V003 (NASA Earthdata)': {'kind':'nasa', 'short_name':'SRTMGL3', 'version':'003', 'res':'90 m', 'type':'DEM', 'coverage':'~60°N–56°S', 'auth':'earthdata'},
}

ZH = {
'title':'Multi-Source DEM Downloader v1.0.0','extent':'下载范围','current':'当前地图范围','draw':'地图绘制范围','layer':'当前面图层','file':'外部矢量文件','selected':'仅使用选中要素',
'choose':'选择…','draw_btn':'地图绘制范围','clear':'清除绘制范围','source':'DEM 数据源','api_key':'API Key','show_key':'显示','source_info':'数据说明','auth':'账号与认证','auth_service':'认证服务','username':'用户名 / ID','password':'密码','clear_auth':'清除认证信息','auth_public':'当前数据源为公开数据，无需账号或 API Key。','auth_ot':'该数据源需要 API Key。','auth_nasa':'SRTM / NASADEM 使用 NASA Earthdata 官方数据源，请填写 Earthdata Login 用户名和密码。','auth_jaxa':'ALOS AW3D30 使用 JAXA 官方账号下载，请填写注册后邮件中提供的 ID 和 Password。',
'output':'输出','browse':'浏览…','clip':'自动裁剪到研究区','load':'下载后自动加载到 QGIS','keep':'保留原始下载文件','hillshade':'同时生成山体阴影',
'basemap':'底图','add_basemap':'添加底图','grid':'显示 1°×1° DEM 格网','check':'检查数据','download':'开始下载','ready':'就绪','no_extent':'请先设置有效的下载范围。',
'no_output':'请选择输出目录。','need_key':'该数据源需要 API Key。','need_userpass':'该数据源需要用户名和密码。','need_earthdata':'NASA Earthdata 数据源需要 Earthdata Login 用户名和密码。','need_jaxa':'ALOS AW3D30 需要 JAXA 用户名（ID）和密码。','too_many':'研究范围涉及 {n} 个瓦片，范围过大，请缩小研究区。','done':'处理完成。',
'failed':'处理失败','cancel':'取消下载','placeholder':'请选择 SHP / GPKG / GeoJSON','tiles':'涉及瓦片','extent_wgs':'WGS84范围','official':'官方/公开数据源','api_note':'认证信息仅保存在当前插件会话中，不写入源代码或配置文件。','earthdata_login':'打开 Earthdata Login','earthdata_apps':'应用授权','test_auth':'测试账号','auth_ok':'Earthdata 认证测试成功。','auth_fail':'Earthdata 认证测试失败：','proxy':'HTTP 代理','proxy_hint':'可选，如 http://127.0.0.1:7890（JAXA 连接超时时建议填写）','skip_ssl':'跳过 SSL 证书验证（仅证书验证失败时使用）','network_note':'网络选项仅用于 NASA/JAXA 请求；默认严格验证 SSL。',
}
EN = {
'title':'Multi-Source DEM Downloader v1.0.0','extent':'Download extent','current':'Current map extent','draw':'Draw rectangle on map','layer':'Polygon layer','file':'External vector file','selected':'Selected features only',
'choose':'Choose…','draw_btn':'Draw extent','clear':'Clear drawn extent','source':'DEM source','api_key':'API Key','show_key':'Show','source_info':'Data information','auth':'Account & Authentication','auth_service':'Authentication service','username':'Username / ID','password':'Password','clear_auth':'Clear credentials','auth_public':'This source is public and does not require an account or API key.','auth_ot':'This source requires an API Key.','auth_nasa':'SRTM / NASADEM use the official NASA Earthdata source. Enter your Earthdata Login username and password.','auth_jaxa':'ALOS AW3D30 uses the official JAXA account service. Enter the ID and Password sent after registration.',
'output':'Output','browse':'Browse…','clip':'Clip to study area','load':'Add output to QGIS','keep':'Keep raw downloads','hillshade':'Create hillshade',
'basemap':'Basemap','add_basemap':'Add basemap','grid':'Show 1°×1° DEM grid','check':'Check data','download':'Download','ready':'Ready','no_extent':'Please define a valid download extent.',
'no_output':'Select an output folder.','need_key':'This source requires an API Key.','need_userpass':'This source requires a username and password.','need_earthdata':'NASA Earthdata requires an Earthdata Login username and password.','need_jaxa':'ALOS AW3D30 requires a JAXA User ID and Password.','too_many':'The study area intersects {n} tiles. Please reduce the extent.','done':'Completed.',
'failed':'Failed','cancel':'Cancel','placeholder':'Select SHP / GPKG / GeoJSON','tiles':'Tiles','extent_wgs':'WGS84 extent','official':'Official/public data source','api_note':'Credentials are kept only for the current plugin session and are not written to source or settings.','earthdata_login':'Open Earthdata Login','earthdata_apps':'Authorized Apps','test_auth':'Test account','auth_ok':'Earthdata authentication test succeeded.','auth_fail':'Earthdata authentication test failed: ','proxy':'HTTP proxy','proxy_hint':'Optional, e.g. http://127.0.0.1:7890','skip_ssl':'Skip SSL certificate verification (only for certificate errors)','network_note':'Network options apply only to NASA/JAXA requests; SSL verification is enabled by default.',
}

def lang_dict():
    try:
        loc = QgsProject.instance().readEntry('locale','/userLocale','')[0]
    except Exception as exc:
        QgsMessageLog.logMessage(str(exc), LOG_TAG, Qgis.Info)
        loc = ''
    if not loc: loc = QLocale.system().name()
    return ZH if str(loc).lower().startswith('zh') else EN

class CollapsibleSection(QWidget):
    toggled = pyqtSignal(bool)
    def __init__(self,title,expanded=True,parent=None):
        super().__init__(parent)
        self.setObjectName('CollapsibleSection')
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        lay=QVBoxLayout(self); lay.setContentsMargins(0,2,0,2); lay.setSpacing(0)
        self.header=QToolButton(self)
        self.header.setText('  ' + title)
        self.header.setCheckable(True)
        self.header.setChecked(expanded)
        self.header.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.header.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)
        self.header.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Fixed)
        self.header.setMinimumHeight(30)
        self.header.setCursor(Qt.CursorShape.PointingHandCursor)
        self.header.setStyleSheet("""
            QToolButton {
                border: 1px solid #B8C9A5;
                border-radius: 6px;
                padding: 5px 8px;
                font-weight: 600;
                text-align: left;
                color: #2F4F1F;
                background: #F3F8EE;
            }
            QToolButton:hover { background: #EAF3DF; }
            QToolButton:checked {
                color: white;
                background: #589632;
                border-color: #4D872B;
                border-bottom-left-radius: 0px;
                border-bottom-right-radius: 0px;
            }
            QToolButton:checked:hover { background: #4D872B; }
        """)
        lay.addWidget(self.header)
        self.content=QFrame(self)
        self.content.setFrameShape(QFrame.Shape.NoFrame)
        self.content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        self.content.setStyleSheet('QFrame{border:1px solid #B8C9A5;border-top:0;border-bottom-left-radius:6px;border-bottom-right-radius:6px;background:palette(base);}')
        self.content_layout=QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(10,8,10,8)
        self.content_layout.setSpacing(6)
        self.content.setVisible(expanded)
        self.content.setMaximumHeight(16777215 if expanded else 0)
        lay.addWidget(self.content)
        self.header.toggled.connect(self._toggle)
    def _toggle(self,on):
        self.content.setVisible(on)
        self.content.setMaximumHeight(16777215 if on else 0)
        self.header.setArrowType(Qt.ArrowType.DownArrow if on else Qt.ArrowType.RightArrow)
        self.updateGeometry(); self.adjustSize(); self.toggled.emit(on)

class RectTool(QgsMapToolEmitPoint):
    def __init__(self,canvas,callback):
        super().__init__(canvas); self.canvas=canvas; self.callback=callback; self.start=None
        self.rubber=QgsRubberBand(canvas,Qgis.GeometryType.Polygon); self.rubber.setStrokeColor(QColor(0,120,215,220)); self.rubber.setFillColor(QColor(0,120,215,35)); self.rubber.setWidth(2)
    def canvasPressEvent(self,e): self.start=self.toMapCoordinates(e.pos()); self._show(self.start,self.start)
    def canvasMoveEvent(self,e):
        if self.start is not None: self._show(self.start,self.toMapCoordinates(e.pos()))
    def canvasReleaseEvent(self,e):
        if self.start is None:return
        end=self.toMapCoordinates(e.pos()); r=QgsRectangle(self.start,end); self.start=None; self.rubber.reset(Qgis.GeometryType.Polygon)
        if r.width()>0 and r.height()>0:self.callback(r,self.canvas.mapSettings().destinationCrs())
    def _show(self,a,b): self.rubber.setToGeometry(QgsGeometry.fromRect(QgsRectangle(a,b)),None)


class EarthdataSession(requests.Session):
    """Requests session following NASA Earthdata Login redirect rules."""
    AUTH_HOST = 'urs.earthdata.nasa.gov'

    def __init__(self, username, password):
        super().__init__()
        self.auth = (username, password)
        self.headers.update({
            'User-Agent': f'DEM-Downloader-QGIS/{PLUGIN_VERSION}',
            'Accept': '*/*',
        })
        retry = Retry(
            total=4,
            connect=4,
            read=4,
            status=4,
            backoff_factor=1.0,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset(('GET', 'HEAD')),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry, pool_connections=4, pool_maxsize=4)
        self.mount('https://', adapter)
        self.mount('http://', adapter)

    def rebuild_auth(self, prepared_request, response):
        # NASA's documented pattern: retain credentials only when redirecting
        # to/from the Earthdata Login host, and strip them for unrelated hosts.
        headers = prepared_request.headers
        if 'Authorization' not in headers:
            return
        original = urllib.parse.urlparse(response.request.url).hostname
        redirect = urllib.parse.urlparse(prepared_request.url).hostname
        if (original != redirect and
                redirect != self.AUTH_HOST and
                original != self.AUTH_HOST):
            del headers['Authorization']
