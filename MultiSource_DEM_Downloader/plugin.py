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
from qgis.PyQt.QtWidgets import (QAction, QButtonGroup, QCheckBox, QComboBox, QDockWidget, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QProgressBar, QPushButton, QRadioButton, QScrollArea, QSizePolicy, QToolButton, QVBoxLayout, QWidget)
from qgis.core import (Qgis, QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsGeometry, QgsMessageLog, QgsProject, QgsRasterLayer, QgsRectangle, QgsVectorLayer, QgsWkbTypes)
from qgis.gui import QgsMapToolEmitPoint, QgsRubberBand
import processing
from .common import *
from .dock import DEMDock

class DEMDownloaderPlugin:
    def __init__(self,iface):self.iface=iface;self.action=None;self.dock=None;self.maptool=None;self.permanent_rubber=None
    def initGui(self):
        icon_path=os.path.join(PLUGIN_DIR,'icon.svg')
        self.action=QAction(QIcon(icon_path),'Multi-Source DEM Downloader v1.0.0',self.iface.mainWindow());self.action.triggered.connect(self.show);self.iface.addPluginToRasterMenu('&Multi-Source DEM Downloader',self.action);self.iface.addToolBarIcon(self.action)
    def unload(self):
        if self.action:self.iface.removePluginRasterMenu('&Multi-Source DEM Downloader',self.action);self.iface.removeToolBarIcon(self.action)
        if self.dock:self.iface.removeDockWidget(self.dock)
        self.clear_extent()
    def show(self):
        if self.dock is None:self.dock=DEMDock(self);self.iface.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea,self.dock)
        self.dock.refresh_layers();self.dock.show();self.dock.raise_()
    def start_draw(self):
        self.show();self.maptool=RectTool(self.iface.mapCanvas(),self._drawn);self.iface.mapCanvas().setMapTool(self.maptool);self.dock.status.setText(self.dock.t['draw'])
    def _drawn(self,rect,crs):
        self.clear_extent();self.dock.draw_rect=rect;self.dock.draw_crs=crs;self.permanent_rubber=QgsRubberBand(self.iface.mapCanvas(),Qgis.GeometryType.Polygon);self.permanent_rubber.setStrokeColor(QColor(0,120,215,230));self.permanent_rubber.setFillColor(QColor(0,120,215,35));self.permanent_rubber.setWidth(2);self.permanent_rubber.setToGeometry(QgsGeometry.fromRect(rect),None);self.dock.update_scope();self.dock.status.setText(self.dock.t['ready'])
    def clear_extent(self):
        if self.permanent_rubber is not None:
            self.iface.mapCanvas().scene().removeItem(self.permanent_rubber);self.permanent_rubber=None
        if self.dock is not None:self.dock.draw_rect=None;self.dock.draw_crs=None;self.dock.update_scope()
