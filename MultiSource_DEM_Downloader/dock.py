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
from .worker import DownloadWorker

class DEMDock(QDockWidget):
    def __init__(self,plugin):
        self.plugin=plugin; self.t=lang_dict(); super().__init__(self.t['title']); self.setObjectName('DEMDownloaderDock'); self.setMinimumWidth(330)
        self.draw_rect=None; self.draw_crs=None; self.file_layer=None; self.worker=None; self.thread=None; self.temp_dir=None; self.pending=None; self._build(); self.refresh_layers(); self.source_changed()
    def _build(self):
        body=QWidget(); bl=QVBoxLayout(body); bl.setContentsMargins(0,0,0,0)
        scroll=QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.Shape.NoFrame)
        inner=QWidget(); inner.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum); root=QVBoxLayout(inner); root.setContentsMargins(8,6,8,6); root.setSpacing(4); root.setAlignment(Qt.AlignmentFlag.AlignTop)
        sec=CollapsibleSection(self.t['extent'],True); v=sec.content_layout
        self.bg=QButtonGroup(self); self.rb_current=QRadioButton(self.t['current']); self.rb_draw=QRadioButton(self.t['draw']); self.rb_layer=QRadioButton(self.t['layer']); self.rb_file=QRadioButton(self.t['file']); self.rb_draw.setChecked(True)
        for r in (self.rb_current,self.rb_draw,self.rb_layer,self.rb_file): self.bg.addButton(r);v.addWidget(r)
        h=QHBoxLayout(); self.layer_combo=QComboBox(); h.addWidget(self.layer_combo,1); self.selected=QCheckBox(self.t['selected']); h.addWidget(self.selected);v.addLayout(h)
        h=QHBoxLayout(); self.file_edit=QLineEdit(); self.file_edit.setPlaceholderText(self.t['placeholder']);h.addWidget(self.file_edit,1); b=QPushButton(self.t['choose']);b.clicked.connect(self.choose_file);h.addWidget(b);v.addLayout(h)
        self.draw_btn=QPushButton(self.t['draw_btn']);self.draw_btn.clicked.connect(self.begin_draw);v.addWidget(self.draw_btn)
        self.scope_info=QLabel(self.t['no_extent']);self.scope_info.setWordWrap(True);self.scope_info.setStyleSheet('QLabel{padding:6px;background:palette(base);border:1px solid palette(mid);border-radius:3px;}');v.addWidget(self.scope_info)
        c=QPushButton(self.t['clear']);c.clicked.connect(self.plugin.clear_extent);v.addWidget(c);root.addWidget(sec)
        sec=CollapsibleSection(self.t['source'],True);v=sec.content_layout
        self.source_combo=QComboBox();self.source_combo.addItems(SOURCES.keys());self.source_combo.currentTextChanged.connect(self.source_changed);v.addWidget(self.source_combo)
        self.source_info=QLabel();self.source_info.setWordWrap(True);v.addWidget(self.source_info)
        root.addWidget(sec)

        self.auth_sec=CollapsibleSection(self.t['auth'],True);v=self.auth_sec.content_layout
        self.auth_note=QLabel();self.auth_note.setWordWrap(True);self.auth_note.setStyleSheet('QLabel{padding:6px;background:palette(alternate-base);border-radius:4px;}');v.addWidget(self.auth_note)
        h=QHBoxLayout();h.addWidget(QLabel(self.t['auth_service']));self.auth_service=QLabel('OpenTopography');self.auth_service.setStyleSheet('font-weight:600;');h.addWidget(self.auth_service,1);v.addLayout(h)
        h=QHBoxLayout();self.key_edit=QLineEdit();self.key_edit.setEchoMode(QLineEdit.EchoMode.Password);self.key_edit.setPlaceholderText(self.t['api_key']);h.addWidget(self.key_edit,1);self.show_key=QCheckBox(self.t['show_key']);h.addWidget(self.show_key);v.addLayout(h)
        h=QHBoxLayout();self.user_edit=QLineEdit();self.user_edit.setPlaceholderText(self.t['username']);self.pass_edit=QLineEdit();self.pass_edit.setPlaceholderText(self.t['password']);self.pass_edit.setEchoMode(QLineEdit.EchoMode.Password);h.addWidget(self.user_edit,1);h.addWidget(self.pass_edit,1);v.addLayout(h)
        h=QHBoxLayout();self.auth_hint=QLabel(self.t['api_note']);self.auth_hint.setStyleSheet('color:palette(mid);');h.addWidget(self.auth_hint,1);self.clear_auth_btn=QPushButton(self.t['clear_auth']);self.clear_auth_btn.clicked.connect(self.clear_auth);h.addWidget(self.clear_auth_btn);v.addLayout(h)
        self.earthdata_actions=QWidget(); ah=QHBoxLayout(self.earthdata_actions); ah.setContentsMargins(0,0,0,0)
        self.earth_login_btn=QPushButton(self.t['earthdata_login']); self.earth_login_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl('https://urs.earthdata.nasa.gov/')))
        self.earth_apps_btn=QPushButton(self.t['earthdata_apps']); self.earth_apps_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl('https://urs.earthdata.nasa.gov/profile')))
        self.test_auth_btn=QPushButton(self.t['test_auth']); self.test_auth_btn.clicked.connect(self.test_earthdata_auth)
        ah.addWidget(self.earth_login_btn); ah.addWidget(self.earth_apps_btn); ah.addWidget(self.test_auth_btn); v.addWidget(self.earthdata_actions)
        self.network_opts=QWidget(); nh=QVBoxLayout(self.network_opts); nh.setContentsMargins(0,0,0,0); nh.setSpacing(4)
        ph=QHBoxLayout(); ph.addWidget(QLabel(self.t['proxy'])); self.proxy_edit=QLineEdit(); self.proxy_edit.setPlaceholderText(self.t['proxy_hint']); ph.addWidget(self.proxy_edit,1); nh.addLayout(ph)
        self.skip_ssl=QCheckBox(self.t['skip_ssl']); self.skip_ssl.setChecked(False); self.skip_ssl.setStyleSheet('color:#9A6700;'); nh.addWidget(self.skip_ssl)
        self.network_note=QLabel(self.t['network_note']); self.network_note.setWordWrap(True); self.network_note.setStyleSheet('color:palette(mid);'); nh.addWidget(self.network_note)
        v.addWidget(self.network_opts)
        self.show_key.toggled.connect(self._toggle_credentials_visibility)
        root.addWidget(self.auth_sec)

        sec=CollapsibleSection(self.t['output'],True);v=sec.content_layout
        h=QHBoxLayout();self.out_edit=QLineEdit();h.addWidget(self.out_edit,1);b=QPushButton(self.t['browse']);b.clicked.connect(self.choose_out);h.addWidget(b);v.addLayout(h)
        self.cb_clip=QCheckBox(self.t['clip']);self.cb_clip.setChecked(True);self.cb_load=QCheckBox(self.t['load']);self.cb_load.setChecked(True);self.cb_keep=QCheckBox(self.t['keep']);self.cb_hill=QCheckBox(self.t['hillshade'])
        for x in (self.cb_clip,self.cb_load,self.cb_keep,self.cb_hill):v.addWidget(x)
        root.addWidget(sec)
        sec=CollapsibleSection(self.t['basemap'],False);v=sec.content_layout
        h=QHBoxLayout();self.base_combo=QComboBox();self.base_combo.addItems(BASEMAPS.keys());h.addWidget(self.base_combo,1);b=QPushButton(self.t['add_basemap']);b.clicked.connect(self.add_basemap);h.addWidget(b);v.addLayout(h)
        self.cb_grid=QCheckBox(self.t['grid']);self.cb_grid.toggled.connect(self.toggle_grid);v.addWidget(self.cb_grid);root.addWidget(sec)
        root.addStretch(1)
        scroll.setWidget(inner); scroll.setAlignment(Qt.AlignmentFlag.AlignTop); bl.addWidget(scroll,1)
        self.progress=QProgressBar();self.progress.setRange(0,100);bl.addWidget(self.progress)
        self.status=QLabel(self.t['ready']);self.status.setWordWrap(True);bl.addWidget(self.status)
        h=QHBoxLayout();self.check_btn=QPushButton(self.t['check']);self.down_btn=QPushButton(self.t['download']);self.cancel_btn=QPushButton(self.t['cancel']);self.cancel_btn.setEnabled(False);self.check_btn.clicked.connect(self.check_data);self.down_btn.clicked.connect(self.download);self.cancel_btn.clicked.connect(self.cancel_download);h.addWidget(self.check_btn);h.addWidget(self.down_btn);h.addWidget(self.cancel_btn);bl.addLayout(h)
        self.setWidget(body)
    def refresh_layers(self):
        self.layer_combo.clear()
        for lyr in QgsProject.instance().mapLayers().values():
            if isinstance(lyr,QgsVectorLayer) and lyr.isValid() and QgsWkbTypes.geometryType(lyr.wkbType())==Qgis.GeometryType.Polygon:self.layer_combo.addItem(lyr.name(),lyr.id())
    def source_changed(self):
        s=SOURCES[self.source_combo.currentText()]
        self.source_info.setText(f"{s['res']} | {s['type']} | {s['coverage']}")
        auth = s.get('auth', 'none')
        self.auth_sec.setVisible(auth != 'none')
        self.earthdata_actions.setVisible(auth == 'earthdata')
        self.network_opts.setVisible(auth in ('earthdata','jaxa'))
        if auth == 'api_key':
            self.auth_service.setText('API')
            self.auth_note.setText(self.t['auth_ot'])
            self.key_edit.setVisible(True); self.show_key.setVisible(True)
            self.user_edit.setVisible(False); self.pass_edit.setVisible(False)
            self.key_edit.setEnabled(True); self.show_key.setEnabled(True)
            self.key_edit.setPlaceholderText(self.t['api_key'])
        elif auth == 'earthdata':
            self.auth_service.setText('NASA Earthdata Login')
            self.auth_note.setText(self.t['auth_nasa'])
            self.key_edit.setVisible(False); self.show_key.setVisible(True)
            self.user_edit.setVisible(True); self.pass_edit.setVisible(True)
            self.user_edit.setPlaceholderText('Earthdata Username')
            self.pass_edit.setPlaceholderText('Earthdata Password')
            self.show_key.setEnabled(True)
        elif auth == 'jaxa':
            self.auth_service.setText('JAXA / EORC')
            self.auth_note.setText(self.t['auth_jaxa'])
            self.key_edit.setVisible(False); self.show_key.setVisible(True)
            self.user_edit.setVisible(True); self.pass_edit.setVisible(True)
            self.user_edit.setPlaceholderText('JAXA ID')
            self.pass_edit.setPlaceholderText('JAXA Password')
            self.show_key.setEnabled(True)
        else:
            self.auth_note.setText(self.t['auth_public'])
            self.key_edit.setEnabled(False); self.show_key.setEnabled(False)
            self.key_edit.setVisible(False); self.show_key.setVisible(False)
            self.user_edit.setVisible(False); self.pass_edit.setVisible(False)

    def _toggle_credentials_visibility(self,on):
        mode = QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password
        self.key_edit.setEchoMode(mode)
        self.pass_edit.setEchoMode(mode)

    def test_earthdata_auth(self):
        if SOURCES[self.source_combo.currentText()].get('auth') != 'earthdata': return
        username=self.user_edit.text().strip(); password=self.pass_edit.text().strip()
        if not username or not password: QMessageBox.warning(self,self.t['title'],self.t['need_earthdata']); return
        r=self.get_extent_wgs84()
        if r is None: QMessageBox.warning(self,self.t['title'],self.t['no_extent']); return
        src=dict(SOURCES[self.source_combo.currentText()])
        worker=DownloadWorker(src,(r.xMinimum(),r.yMinimum(),r.xMaximum(),r.yMaximum()),tempfile.mkdtemp(prefix='dem_auth_'),'',[],username,password,self.proxy_edit.text().strip(),not self.skip_ssl.isChecked())
        try:
            links=worker._cmr_data_links()
            if not links: raise RuntimeError('CMR did not return a downloadable granule link.')
            session=worker._earthdata_session(username,password)
            with session.get(links[0], stream=True, allow_redirects=True, timeout=(20,45), headers={'Range':'bytes=0-1023','Accept':'*/*'}) as resp:
                if resp.status_code in (401,403): raise RuntimeError('Earthdata rejected the credentials or LP DAAC authorization')
                resp.raise_for_status(); ctype=(resp.headers.get('Content-Type') or '').lower(); final_url=resp.url.lower(); sample=next(resp.iter_content(chunk_size=1024),b'')
                if 'text/html' in ctype or 'urs.earthdata.nasa.gov' in final_url: raise RuntimeError('login redirect was returned instead of data')
                if not sample: raise RuntimeError('empty data response')
            QMessageBox.information(self,self.t['title'],self.t['auth_ok'])
        except Exception as exc: QMessageBox.warning(self,self.t['title'],self.t['auth_fail']+str(exc))
        finally:
            try: shutil.rmtree(worker.temp_dir,ignore_errors=True)
            except Exception as cleanup_exc: QgsMessageLog.logMessage(str(cleanup_exc),LOG_TAG,Qgis.Info)

    def clear_auth(self):
        self.key_edit.clear(); self.user_edit.clear(); self.pass_edit.clear(); self.show_key.setChecked(False)
    def choose_file(self):
        p,_=QFileDialog.getOpenFileName(self,self.t['choose'],'','Vector (*.shp *.gpkg *.geojson);;All files (*.*)')
        if not p:return
        lyr=QgsVectorLayer(p,Path(p).stem,'ogr')
        if not lyr.isValid() or QgsWkbTypes.geometryType(lyr.wkbType())!=Qgis.GeometryType.Polygon:QMessageBox.warning(self,self.t['title'],'Polygon vector data required.');return
        self.file_layer=lyr;self.file_edit.setText(p);self.rb_file.setChecked(True);self.update_scope()
    def choose_out(self):
        p=QFileDialog.getExistingDirectory(self,self.t['browse'])
        if p:self.out_edit.setText(p)
    def begin_draw(self): self.rb_draw.setChecked(True);self.plugin.start_draw()
    def set_drawn(self,rect,crs): self.draw_rect=rect;self.draw_crs=crs;self.rb_draw.setChecked(True);self.update_scope()
    def get_extent_wgs84(self):
        if self.rb_current.isChecked(): r=self.plugin.iface.mapCanvas().extent();crs=self.plugin.iface.mapCanvas().mapSettings().destinationCrs()
        elif self.rb_draw.isChecked():
            if self.draw_rect is None:return None
            r=self.draw_rect;crs=self.draw_crs
        elif self.rb_layer.isChecked():
            lid=self.layer_combo.currentData();lyr=QgsProject.instance().mapLayer(lid) if lid else None
            if not lyr:return None
            if self.selected.isChecked() and lyr.selectedFeatureCount()>0:
                geoms=[f.geometry() for f in lyr.selectedFeatures() if f.hasGeometry()]
                if not geoms:return None
                geom=QgsGeometry.unaryUnion(geoms);r=geom.boundingBox()
            else:r=lyr.extent()
            crs=lyr.crs()
        else:
            if self.file_layer is None:return None
            r=self.file_layer.extent();crs=self.file_layer.crs()
        dst=QgsCoordinateReferenceSystem('EPSG:4326');tr=QgsCoordinateTransform(crs,dst,QgsProject.instance());return tr.transformBoundingBox(r)
    def get_mask_layer(self):
        if self.rb_layer.isChecked():
            lid=self.layer_combo.currentData();return QgsProject.instance().mapLayer(lid) if lid else None
        if self.rb_file.isChecked():return self.file_layer
        return None
    def update_scope(self):
        r=self.get_extent_wgs84()
        if r is None:self.scope_info.setText(self.t['no_extent']);return
        tiles=self._tile_names(r); preview=', '.join(tiles[:10])+(' …' if len(tiles)>10 else '')
        self.scope_info.setText(f"{self.t['extent_wgs']}: {r.xMinimum():.5f}, {r.yMinimum():.5f}, {r.xMaximum():.5f}, {r.yMaximum():.5f}\n{self.t['tiles']} ({len(tiles)}): {preview}")
    def _tile_names(self,r):
        out=[];x0=math.floor(r.xMinimum());x1=math.ceil(r.xMaximum());y0=math.floor(r.yMinimum());y1=math.ceil(r.yMaximum())
        for y in range(y0,y1):
            for x in range(x0,x1):out.append(self._tile_id(y,x))
        return out
    @staticmethod
    def _tile_id(lat,lon):return f"{'N' if lat>=0 else 'S'}{abs(lat):02d}_{'E' if lon>=0 else 'W'}{abs(lon):03d}"
    def check_data(self):
        r=self.get_extent_wgs84()
        if r is None:QMessageBox.warning(self,self.t['title'],self.t['no_extent']);return
        s=SOURCES[self.source_combo.currentText()];n=len(self._tile_names(r));msg=f"{self.source_combo.currentText()}\n{s['res']} | {s['type']} | {s['coverage']}\n{self.t['tiles']}: {n}"
        if s.get('auth')=='api_key' and not self.key_edit.text().strip():msg+='\n\n'+self.t['need_key']
        if s.get('auth')=='earthdata' and (not self.user_edit.text().strip() or not self.pass_edit.text().strip()):msg+='\n\n'+self.t['need_earthdata']
        if s.get('auth')=='jaxa' and (not self.user_edit.text().strip() or not self.pass_edit.text().strip()):msg+='\n\n'+self.t['need_jaxa']
        QMessageBox.information(self,self.t['check'],msg)
    def download(self):
        r=self.get_extent_wgs84(); outdir=self.out_edit.text().strip()
        if r is None: QMessageBox.warning(self,self.t['title'],self.t['no_extent']); return
        if not outdir: QMessageBox.warning(self,self.t['title'],self.t['no_output']); return
        srcname=self.source_combo.currentText(); src=dict(SOURCES[srcname]); key=self.key_edit.text().strip(); username=self.user_edit.text().strip(); password=self.pass_edit.text().strip()
        if src.get('auth')=='api_key' and not key: QMessageBox.warning(self,self.t['title'],self.t['need_key']); return
        if src.get('auth')=='earthdata' and (not username or not password): QMessageBox.warning(self,self.t['title'],self.t['need_earthdata']); return
        if src.get('auth')=='jaxa' and (not username or not password): QMessageBox.warning(self,self.t['title'],self.t['need_jaxa']); return
        os.makedirs(outdir,exist_ok=True); temp=Path(tempfile.mkdtemp(prefix='dem_downloader_')); self.temp_dir=temp; self.pending={'extent':r,'outdir':outdir,'srcname':srcname,'keep':self.cb_keep.isChecked()}; ids=self._tile_names(r)
        self.down_btn.setEnabled(False); self.check_btn.setEnabled(False); self.cancel_btn.setEnabled(True); self.progress.setValue(0); self.status.setText('Preparing download…'); self.thread=QThread(self)
        self.worker=DownloadWorker(src,(r.xMinimum(),r.yMinimum(),r.xMaximum(),r.yMaximum()),str(temp),key,ids,username,password,self.proxy_edit.text().strip(),not self.skip_ssl.isChecked()); self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run); self.worker.progress.connect(self.progress.setValue); self.worker.status.connect(self.status.setText); self.worker.warning.connect(lambda m: QgsMessageLog.logMessage(m,LOG_TAG,Qgis.Warning)); self.worker.finished.connect(self._download_finished); self.worker.failed.connect(self._download_failed); self.worker.finished.connect(self.thread.quit); self.worker.failed.connect(self.thread.quit); self.thread.finished.connect(self._thread_finished); self.thread.start()

    def cancel_download(self):
        if self.worker is not None:self.status.setText('Cancelling…');self.cancel_btn.setEnabled(False);self.worker.cancel()
    def _download_finished(self,result):
        try:
            files=result.get('files',[])
            if not files:raise RuntimeError('No DEM files were downloaded.')
            self.progress.setValue(78); self.status.setText('Mosaicking / preparing output…')
            if len(files)==1: raw=files[0]
            else:
                raw=str(self.temp_dir/'mosaic.vrt');processing.run('gdal:buildvirtualraster',{'INPUT':files,'RESOLUTION':0,'SEPARATE':False,'PROJ_DIFFERENCE':False,'ADD_ALPHA':False,'ASSIGN_CRS':None,'RESAMPLING':0,'SRC_NODATA':None,'EXTRA':'','OUTPUT':raw})
            p=self.pending; r=p['extent']; final=Path(p['outdir'])/(self._safe_name(p['srcname'])+'.tif');self.progress.setValue(84);self.status.setText('Clipping / preparing output…');self._finalize(raw,final,r);self.progress.setValue(94)
            if self.cb_hill.isChecked():self.status.setText('Creating hillshade…');self._hillshade(final)
            if self.cb_load.isChecked():
                lyr=QgsRasterLayer(str(final),final.stem)
                if lyr.isValid():QgsProject.instance().addMapLayer(lyr)
            self.progress.setValue(100);self.status.setText(self.t['done']);QMessageBox.information(self,self.t['title'],self.t['done'])
        except Exception as exc:self._show_failure(str(exc))
        finally:self._cleanup_temp()
    def _download_failed(self,message):self._show_failure(message);self._cleanup_temp()
    def _show_failure(self,message):QgsMessageLog.logMessage(message,LOG_TAG,Qgis.Critical);self.status.setText(message);QMessageBox.critical(self,self.t['failed'],message)
    def _cleanup_temp(self):
        keep=bool(self.pending and self.pending.get('keep'))
        if self.temp_dir is not None and not keep:shutil.rmtree(self.temp_dir,ignore_errors=True)
        self.temp_dir=None
    def _thread_finished(self):
        self.down_btn.setEnabled(True);self.check_btn.setEnabled(True);self.cancel_btn.setEnabled(False)
        if self.worker is not None:self.worker.deleteLater()
        if self.thread is not None:self.thread.deleteLater()
        self.worker=None;self.thread=None
    def _finalize(self,raw,final,r):
        mask=self.get_mask_layer()
        if self.cb_clip.isChecked() and mask is not None:
            params={'INPUT':raw,'MASK':mask,'SOURCE_CRS':None,'TARGET_CRS':QgsCoordinateReferenceSystem('EPSG:4326'),'TARGET_EXTENT':None,'NODATA':-9999,'ALPHA_BAND':False,'CROP_TO_CUTLINE':True,'KEEP_RESOLUTION':True,'SET_RESOLUTION':False,'X_RESOLUTION':None,'Y_RESOLUTION':None,'MULTITHREADING':True,'OPTIONS':'COMPRESS=DEFLATE|TILED=YES','DATA_TYPE':0,'EXTRA':'','OUTPUT':str(final)};processing.run('gdal:cliprasterbymasklayer',params)
        else:
            ext=f'{r.xMinimum()},{r.xMaximum()},{r.yMinimum()},{r.yMaximum()} [EPSG:4326]';processing.run('gdal:cliprasterbyextent',{'INPUT':raw,'PROJWIN':ext,'NODATA':-9999,'OPTIONS':'COMPRESS=DEFLATE|TILED=YES','DATA_TYPE':0,'EXTRA':'','OUTPUT':str(final)})
    def _hillshade(self,dem):
        out=dem.with_name(dem.stem+'_hillshade.tif');processing.run('gdal:hillshade',{'INPUT':str(dem),'BAND':1,'Z_FACTOR':1.0,'SCALE':1.0,'AZIMUTH':315.0,'ALTITUDE':45.0,'COMPUTE_EDGES':True,'ZEVENBERGEN':False,'MULTIDIRECTIONAL':False,'OPTIONS':'COMPRESS=DEFLATE|TILED=YES','EXTRA':'','OUTPUT':str(out)})
        if self.cb_load.isChecked():
            lyr=QgsRasterLayer(str(out),out.stem)
            if lyr.isValid():QgsProject.instance().addMapLayer(lyr)
    @staticmethod
    def _safe_name(s):return ''.join(c if c.isalnum() or c in '-_' else '_' for c in s).strip('_')
    def add_basemap(self):
        name=self.base_combo.currentText()
        if any(l.name()==name for l in QgsProject.instance().mapLayers().values()):return
        url,z=BASEMAPS[name];uri=f'type=xyz&url={urllib.parse.quote(url, safe=":/{ }[]")}&zmax={z}&zmin=0';lyr=QgsRasterLayer(uri,name,'wms')
        if lyr.isValid():QgsProject.instance().addMapLayer(lyr,False);QgsProject.instance().layerTreeRoot().insertLayer(0,lyr)
    def toggle_grid(self,on):
        old=[l for l in QgsProject.instance().mapLayers().values() if l.name()=='DEM 1° Grid']
        for l in old:QgsProject.instance().removeMapLayer(l.id())
        if not on:return
        r=self.get_extent_wgs84()
        if r is None:return
        vl=QgsVectorLayer('Polygon?crs=EPSG:4326&field=tile:string(12)','DEM 1° Grid','memory');pr=vl.dataProvider();features=[]
        from qgis.core import QgsFeature
        for y in range(math.floor(r.yMinimum()),math.ceil(r.yMaximum())):
            for x in range(math.floor(r.xMinimum()),math.ceil(r.xMaximum())):
                f=QgsFeature(vl.fields());f['tile']=self._tile_id(y,x);f.setGeometry(QgsGeometry.fromRect(QgsRectangle(x,y,x+1,y+1)));features.append(f)
        pr.addFeatures(features);vl.updateExtents();QgsProject.instance().addMapLayer(vl)
