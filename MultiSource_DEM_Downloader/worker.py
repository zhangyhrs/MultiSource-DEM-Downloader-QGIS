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

class DownloadWorker(QObject):
    progress = pyqtSignal(int)
    status = pyqtSignal(str)
    warning = pyqtSignal(str)
    finished = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, source, extent, temp_dir, api_key, tile_ids, username="", password="", proxy="", verify_ssl=True):
        super().__init__()
        self.source = dict(source)
        self.extent = tuple(extent)
        self.temp_dir = Path(temp_dir)
        self.api_key = api_key
        self.username = username.strip()
        self.password = password.strip()
        self.tile_ids = list(tile_ids)
        self.proxy = (proxy or '').strip()
        self.verify_ssl = bool(verify_ssl)
        self._cancelled = False

    def _requests_verify(self):
        if not self.verify_ssl:
            return False
        try:
            import certifi
            ca = certifi.where()
            if ca and os.path.exists(ca):
                return ca
        except Exception as exc:
            QgsMessageLog.logMessage(f'certifi unavailable: {exc}', LOG_TAG, Qgis.Info)
        return True

    def _apply_network(self, session):
        session.verify = self._requests_verify()
        session.trust_env = True
        if self.proxy:
            session.proxies.update({'http': self.proxy, 'https': self.proxy})
        return session

    @pyqtSlot()
    def cancel(self):
        self._cancelled = True

    def _download_stream(self, url, dest, start_pct, end_pct, label, timeout):
        req = urllib.request.Request(url, headers={'User-Agent':f'DEM-Downloader-QGIS/{PLUGIN_VERSION}'})
        with urllib.request.urlopen(req, timeout=timeout) as resp, open(dest, 'wb') as f:
            total = int(resp.headers.get('Content-Length') or 0)
            done = 0
            while True:
                if self._cancelled:
                    raise RuntimeError('Download cancelled.')
                chunk = resp.read(1024 * 1024)
                if not chunk:
                    break
                f.write(chunk); done += len(chunk)
                if total > 0:
                    frac = min(1.0, done / total)
                    self.progress.emit(int(start_pct + (end_pct - start_pct) * frac))
                    self.status.emit(f'{label}  {done/1048576:.1f}/{total/1048576:.1f} MB')
        return resp.headers.get('Content-Type','').lower()

    @pyqtSlot()
    def run(self):
        try:
            if self.source['kind'] == 'aws':
                result = self._download_aws()
            elif self.source['kind'] == 'ot':
                result = self._download_ot()
            elif self.source['kind'] == 'nasa':
                result = self._download_nasa()
            elif self.source['kind'] == 'jaxa':
                result = self._download_jaxa()
            else:
                raise RuntimeError('Unsupported DEM source type.')
            self.finished.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))

    def _download_aws(self):
        ids = self.tile_ids
        if len(ids) > 80:
            raise RuntimeError(f'The study area intersects {len(ids)} tiles. Please reduce the extent.')
        files = []
        count = max(1, len(ids))
        for idx, tid in enumerate(ids, 1):
            if self._cancelled:
                raise RuntimeError('Download cancelled.')
            lat_part, lon_part = tid.split('_', 1)
            tile = f"Copernicus_DSM_COG_{self.source['arcsec']}_{lat_part}_00_{lon_part}_00_DEM"
            url = f"https://{self.source['bucket']}.s3.eu-central-1.amazonaws.com/{tile}/{tile}.tif"
            dest = self.temp_dir / f'{tile}.tif'
            start = int((idx-1) * 75 / count); end = int(idx * 75 / count)
            self.status.emit(f'Downloading tile {idx}/{len(ids)}: {tid}')
            try:
                self._download_stream(url, dest, start, end, f'{tid}', 120)
                if dest.exists() and dest.stat().st_size > 1024:
                    files.append(str(dest))
                else:
                    if dest.exists(): dest.unlink()
                    self.warning.emit(f'{tid}: downloaded file is empty or invalid.')
            except Exception as exc:
                if dest.exists(): dest.unlink()
                self.warning.emit(f'{tid}: {exc}')
        if not files:
            raise RuntimeError('No downloadable Copernicus DEM tiles were found for this extent. Check the QGIS message log for HTTP errors.')
        self.progress.emit(75)
        return {'kind':'files', 'files':files}

    def _download_ot(self):
        xmin, ymin, xmax, ymax = self.extent
        if not self.api_key or not self.api_key.strip():
            raise RuntimeError('OpenTopography API Key is required for this data source.')
        params = {'demtype': self.source['demtype'], 'south': f'{ymin:.8f}', 'north': f'{ymax:.8f}', 'west': f'{xmin:.8f}', 'east': f'{xmax:.8f}', 'outputFormat': 'GTiff', 'API_Key': self.api_key.strip()}
        url = 'https://portal.opentopography.org/API/globaldem?' + urllib.parse.urlencode(params)
        dest = self.temp_dir / f"{self.source['demtype']}.tif"
        self.status.emit(f"Requesting OpenTopography {self.source['demtype']}…")
        req = urllib.request.Request(url, headers={'User-Agent': f'DEM-Downloader-QGIS/{PLUGIN_VERSION}', 'Accept': '*/*'})
        try:
            with urllib.request.urlopen(req, timeout=240) as resp, open(dest, 'wb') as f:
                total = int(resp.headers.get('Content-Length') or 0); done = 0
                while True:
                    if self._cancelled: raise RuntimeError('Download cancelled.')
                    chunk = resp.read(1024 * 1024)
                    if not chunk: break
                    f.write(chunk); done += len(chunk)
                    if total > 0:
                        frac = min(1.0, done / total)
                        self.progress.emit(int(5 + 70 * frac)); self.status.emit(f'OpenTopography  {done/1048576:.1f}/{total/1048576:.1f} MB')
        except urllib.error.HTTPError as exc:
            body = ''
            try: body = exc.read().decode('utf-8', errors='replace')[:1500]
            except Exception as read_exc: QgsMessageLog.logMessage(str(read_exc), LOG_TAG, Qgis.Info)
            raise RuntimeError(f'OpenTopography HTTP {exc.code}: {body.strip() or str(exc)}') from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f'Cannot connect to OpenTopography: {exc.reason}') from exc
        if not dest.exists() or dest.stat().st_size < 1024: raise RuntimeError('OpenTopography returned an empty or invalid file.')
        with open(dest, 'rb') as f: head = f.read(4)
        if head not in (b'II*\x00', b'MM\x00*'):
            try: msg = dest.read_text(encoding='utf-8', errors='replace')[:1500]
            except Exception as read_exc:
                QgsMessageLog.logMessage(str(read_exc), LOG_TAG, Qgis.Info); msg = 'The response is not a valid GeoTIFF.'
            try: dest.unlink()
            except Exception as unlink_exc: QgsMessageLog.logMessage(str(unlink_exc), LOG_TAG, Qgis.Info)
            raise RuntimeError(f'OpenTopography did not return a GeoTIFF: {msg}')
        self.progress.emit(75)
        return {'kind':'files', 'files':[str(dest)]}

    def _earthdata_session(self, username, password):
        return self._apply_network(EarthdataSession(username, password))

    def _cmr_data_links(self):
        xmin, ymin, xmax, ymax = self.extent
        params = {'short_name': self.source['short_name'], 'version': self.source['version'], 'bounding_box': f'{xmin:.8f},{ymin:.8f},{xmax:.8f},{ymax:.8f}', 'page_size': '2000'}
        url = 'https://cmr.earthdata.nasa.gov/search/granules.json'
        try:
            sess = self._apply_network(requests.Session())
            retry = Retry(total=3, connect=3, read=3, status=3, backoff_factor=1.5, status_forcelist=(429, 500, 502, 503, 504), allowed_methods=frozenset(('GET','HEAD')), raise_on_status=False)
            sess.mount('https://', HTTPAdapter(max_retries=retry)); sess.mount('http://', HTTPAdapter(max_retries=retry))
            resp = sess.get(url, params=params, timeout=(20, 60), headers={'User-Agent': f'DEM-Downloader-QGIS/{PLUGIN_VERSION}', 'Accept': 'application/json', 'Connection': 'close'})
            resp.raise_for_status(); payload = resp.json()
        except requests.RequestException as exc:
            raise RuntimeError(f'NASA CMR search failed: {exc}') from exc
        except ValueError as exc:
            raise RuntimeError('NASA CMR returned an invalid JSON response.') from exc
        entries = payload.get('feed', {}).get('entry', [])
        if not entries: raise RuntimeError('NASA CMR did not find any granules for this extent.')
        links = []
        for entry in entries:
            candidates = []
            for link in entry.get('links', []):
                href = str(link.get('href') or ''); rel = str(link.get('rel') or '').lower(); title = str(link.get('title') or '').lower()
                if not href.startswith('https://'): continue
                low_href = href.lower()
                if any(x in low_href for x in ('opendap', '/s3credentials', '.xml', '.html')): continue
                if 'browse' in rel or 'browse' in title or 'service' in rel: continue
                path = urllib.parse.urlparse(href).path.lower(); is_data_file = path.endswith(('.zip', '.hgt', '.tif', '.tiff', '.hdf', '.h5'))
                if is_data_file and ('data#' in rel or 'download' in title or 'data.lpdaac.earthdatacloud.nasa.gov' in low_href): candidates.append(href)
            candidates.sort(key=lambda u: ('data.lpdaac.earthdatacloud.nasa.gov' not in u.lower(), not urllib.parse.urlparse(u).path.lower().endswith(('.zip', '.hgt', '.tif', '.tiff')), len(u)))
            if candidates: links.append(candidates[0])
        out=[]; seen=set()
        for u in links:
            if u not in seen: seen.add(u); out.append(u)
        if not out: raise RuntimeError('NASA CMR returned granules but no downloadable data links.')
        return out

    def _download_with_session(self, session, url, dest, start_pct, end_pct, label, retries=3):
        last = None
        for attempt in range(1, retries + 1):
            if self._cancelled: raise RuntimeError('Download cancelled.')
            part = Path(str(dest) + '.part')
            try:
                if part.exists(): part.unlink()
                with session.get(url, stream=True, allow_redirects=True, timeout=(30, 240), headers={'Accept': '*/*'}) as resp:
                    if resp.status_code in (401, 403): raise RuntimeError('NASA Earthdata authentication failed. Verify the username/password and LP DAAC Data Pool authorization.')
                    resp.raise_for_status(); ctype = (resp.headers.get('Content-Type') or '').lower(); final_url = resp.url.lower()
                    if '/s3credentials' in final_url: raise RuntimeError('NASA returned an S3 credentials service instead of a DEM granule file.')
                    if 'text/html' in ctype or 'urs.earthdata.nasa.gov' in final_url:
                        preview = next(resp.iter_content(chunk_size=2048), b'').decode('utf-8', errors='ignore').lower()
                        if ('earthdata login' in preview or 'sign in' in preview or 'urs.earthdata.nasa.gov' in final_url): raise RuntimeError('Earthdata Login was not completed. Verify the username/password and LP DAAC Data Pool authorization.')
                        raise RuntimeError('NASA returned an HTML page instead of a DEM data file.')
                    total = int(resp.headers.get('Content-Length') or 0); done = 0
                    with open(part, 'wb') as f:
                        for chunk in resp.iter_content(chunk_size=1024 * 1024):
                            if self._cancelled: raise RuntimeError('Download cancelled.')
                            if not chunk: continue
                            f.write(chunk); done += len(chunk)
                            if total > 0:
                                frac = min(1.0, done / total); self.progress.emit(int(start_pct + (end_pct - start_pct) * frac)); self.status.emit(f'{label}  {done/1048576:.1f}/{total/1048576:.1f} MB')
                if not part.exists() or part.stat().st_size < 256: raise RuntimeError('Downloaded file is empty or invalid.')
                os.replace(part, dest); return
            except requests.RequestException as exc: last = exc
            except RuntimeError: raise
            except Exception as exc: last = exc
            try:
                if part.exists(): part.unlink()
            except OSError: pass
            if attempt < retries:
                self.status.emit(f'{label}: retry {attempt}/{retries - 1}…'); time.sleep(min(2 ** attempt, 6))
        raise RuntimeError(f'Failed to download {label}: {last}')

    def _extract_nasa_elevation(self, archive):
        outputs = []
        if zipfile.is_zipfile(archive):
            with zipfile.ZipFile(archive) as zf:
                for name in zf.namelist():
                    low = name.lower()
                    if not (low.endswith('.hgt') or low.endswith('_hgt.tif') or low.endswith('.tif')): continue
                    if any(x in low for x in ('_swb', '_num', '_inc', '_img', '_err')): continue
                    out = self.temp_dir / Path(name).name
                    with zf.open(name) as src, open(out, 'wb') as dst: shutil.copyfileobj(src, dst, length=1024 * 1024)
                    if out.stat().st_size > 256: outputs.append(str(out))
        return outputs

    def _download_nasa(self):
        if not self.username or not self.password: raise RuntimeError('NASA Earthdata Login username and password are required.')
        self.status.emit(f"Searching NASA CMR for {self.source['short_name']}…"); links = self._cmr_data_links()
        if len(links) > 200: raise RuntimeError(f'NASA CMR returned {len(links)} granules. Please reduce the study area.')
        session = self._earthdata_session(self.username, self.password); files=[]; count=max(1,len(links))
        for i,url in enumerate(links,1):
            if self._cancelled: raise RuntimeError('Download cancelled.')
            name=Path(urllib.parse.urlparse(url).path).name or f'nasa_{i}.bin'; dest=self.temp_dir/name
            self._download_with_session(session,url,dest,int((i-1)*75/count),int(i*75/count),name)
            if zipfile.is_zipfile(dest): files.extend(self._extract_nasa_elevation(dest))
            elif dest.suffix.lower() in ('.hgt','.tif','.tiff'): files.append(str(dest))
            else:
                with open(dest,'rb') as f: magic=f.read(4)
                if magic.startswith(b'PK'): files.extend(self._extract_nasa_elevation(dest))
        if not files: raise RuntimeError('NASA downloads completed, but no elevation raster files were found in the returned granules.')
        self.progress.emit(75); return {'kind':'files','files':files}

    @staticmethod
    def _parse_tile_id(tid):
        lat_s, lon_s = tid.split('_', 1); lat=int(lat_s[1:])*(1 if lat_s[0]=='N' else -1); lon=int(lon_s[1:])*(1 if lon_s[0]=='E' else -1); return lat,lon

    @staticmethod
    def _coord_token(lat, lon):
        return f"{'N' if lat >= 0 else 'S'}{abs(int(lat)):03d}{'E' if lon >= 0 else 'W'}{abs(int(lon)):03d}"

    @staticmethod
    def _jaxa_page_coord(v,is_lat=True):
        hemi=('n' if v>=0 else 's') if is_lat else ('e' if v>=0 else 'w'); return f'{hemi}{abs(int(v)):03d}'

    @classmethod
    def _jaxa_region_page(cls,lat,lon):
        if lat>=80: south,north=80,90
        elif lat>=50: south,north=50,80
        elif lat>=20: south,north=20,50
        elif lat>=-10: south,north=-10,20
        elif lat>=-40: south,north=-40,-10
        elif lat>=-70: south,north=-70,-40
        else: south,north=-90,-70
        west=math.floor(lon/30.0)*30; west=max(-180,min(150,west)); east=west+30
        name=cls._jaxa_page_coord(south,True)+cls._jaxa_page_coord(west,False)+'_'+cls._jaxa_page_coord(north,True)+cls._jaxa_page_coord(east,False)+'.htm'
        return 'https://www.eorc.jaxa.jp/ALOS/en/aw3d30/data/html_v2404/'+name

    @staticmethod
    def _html_links(text,base_url):
        links=set(); pattern=r"(?:href|src)\s*=\s*[\"']([^\"']+)[\"']"
        for match in re.finditer(pattern,text,re.I): links.add(urllib.parse.urljoin(base_url,match.group(1)))
        for match in re.finditer(r"https?://[^\s\"'<>]+",text,re.I): links.add(match.group(0))
        return sorted(links)

    def _jaxa_session(self):
        session=self._apply_network(requests.Session())
        retry=Retry(total=2,connect=0,read=0,status=2,backoff_factor=1.0,status_forcelist=(429,500,502,503,504),allowed_methods=frozenset(['GET','HEAD']),raise_on_status=False)
        session.mount('https://',HTTPAdapter(max_retries=retry,pool_connections=2,pool_maxsize=2)); session.mount('http://',HTTPAdapter(max_retries=retry,pool_connections=2,pool_maxsize=2))
        session.auth=(self.username.strip(),self.password.strip()); session.headers.update({'User-Agent':f'DEM-Downloader-QGIS/{PLUGIN_VERSION}','Accept':'text/html,application/xhtml+xml,application/zip,application/gzip,*/*;q=0.8','Accept-Encoding':'identity','Connection':'close'})
        if self.proxy:self.status.emit(f'JAXA network: proxy {self.proxy}')
        elif not self.verify_ssl:self.status.emit('JAXA network: SSL verification disabled')
        return session

    def _jaxa_get_text(self,session,url):
        last=None
        for attempt in range(1,4):
            if self._cancelled: raise RuntimeError('Download cancelled.')
            try:
                r=session.get(url,timeout=(20,45),allow_redirects=True,headers={'Connection':'close'})
                if r.status_code in (401,403): raise RuntimeError('JAXA authentication failed. Check the ID and Password sent by JAXA. If several attempts failed, wait at least 20 minutes before retrying.')
                if r.status_code>=400: raise RuntimeError(f'JAXA HTTP {r.status_code}: {url}')
                return r.text,r.url
            except RuntimeError: raise
            except requests.RequestException as exc:
                last=exc
                if attempt<3:
                    wait=2**attempt; self.warning.emit(f'JAXA page connection failed ({type(exc).__name__}: {exc}). Retrying {attempt+1}/3 in {wait}s…'); time.sleep(wait)
        hint='' if self.proxy else ' If JAXA is slow or blocked on the current network, configure an HTTP proxy in the authentication section.'
        raise RuntimeError(f'Cannot connect to JAXA page after 3 attempts: {last}.{hint}')

    def _download_jaxa_file(self,session,url,dest,start_pct,end_pct,label):
        part=Path(str(dest)+'.part'); max_attempts=5; last_exc=None
        for attempt in range(1,max_attempts+1):
            if self._cancelled: raise RuntimeError('Download cancelled.')
            existing=part.stat().st_size if part.exists() else 0; headers={}
            if existing>0: headers['Range']=f'bytes={existing}-'
            try:
                with session.get(url,headers=headers,timeout=(20,90),stream=True,allow_redirects=True) as r:
                    if r.status_code in (401,403): raise RuntimeError('JAXA authentication was rejected while downloading AW3D30.')
                    if r.status_code==416 and existing>0: part.replace(dest); return
                    if r.status_code>=400: raise RuntimeError(f'JAXA HTTP {r.status_code}: {url}')
                    resumed=existing>0 and r.status_code==206
                    if existing>0 and not resumed:
                        existing=0
                        try: part.unlink()
                        except OSError: pass
                    remain=int(r.headers.get('Content-Length') or 0); total=existing+remain if resumed else remain; done=existing; mode='ab' if resumed else 'wb'; last_tick=time.monotonic(); last_done=done
                    if resumed:self.status.emit(f'{label}  resuming at {done/1048576:.1f} MB (attempt {attempt}/{max_attempts})')
                    with open(part,mode) as f:
                        first=(done==0)
                        for chunk in r.iter_content(chunk_size=256*1024):
                            if self._cancelled: raise RuntimeError('Download cancelled.')
                            if not chunk: continue
                            if first:
                                first=False; probe=chunk[:512].lower()
                                if b'<html' in probe or b'<!doctype html' in probe: raise RuntimeError('JAXA returned an HTML page instead of an AW3D30 archive. Check the account or download endpoint.')
                            f.write(chunk); done+=len(chunk); now=time.monotonic(); pct=0.0
                            if total>0:
                                frac=min(1.0,done/total); self.progress.emit(max(1,int(round(start_pct+(end_pct-start_pct)*frac)))); pct=frac*100.0
                            if now-last_tick>=0.8:
                                dt=max(0.001,now-last_tick); speed=(done-last_done)/dt/1048576.0
                                if total>0:
                                    remain_mb=max(0.0,(total-done)/1048576.0); eta=remain_mb/speed if speed>0.01 else 0.0; eta_txt=f'  ETA {eta/60:.1f} min' if eta>0 else ''
                                    self.status.emit(f'{label}  {done/1048576:.1f}/{total/1048576:.1f} MB ({pct:.1f}%)  {speed:.2f} MB/s{eta_txt}')
                                else:self.status.emit(f'{label}  {done/1048576:.1f} MB  {speed:.2f} MB/s')
                                last_tick=now; last_done=done
                if not part.exists() or part.stat().st_size<1024: raise RuntimeError('Downloaded JAXA archive is empty or too small.')
                part.replace(dest); self.status.emit(f'{label}  download completed ({dest.stat().st_size/1048576:.1f} MB)'); return
            except RuntimeError: raise
            except (requests.RequestException,OSError) as exc:
                last_exc=exc
                if attempt>=max_attempts: break
                kept=part.stat().st_size/1048576.0 if part.exists() else 0.0; self.warning.emit(f'JAXA connection interrupted ({exc}). Keeping {kept:.1f} MB and retrying {attempt+1}/{max_attempts}…'+('' if self.proxy else ' (可在账号与认证中配置 HTTP 代理)')); time.sleep(min(2*attempt,8))
        raise RuntimeError(f'JAXA download failed after {max_attempts} attempts. Last error: {last_exc}')

    def _extract_jaxa_dsm(self,archive,requested_tokens):
        outputs=[]
        def wanted(name):
            up=name.upper(); return up.endswith(('.TIF','.TIFF')) and '_DSM' in up and any(tok in up for tok in requested_tokens)
        if zipfile.is_zipfile(archive):
            with zipfile.ZipFile(archive) as zf:
                for name in zf.namelist():
                    if wanted(name):
                        out=self.temp_dir/Path(name).name
                        with zf.open(name) as src,open(out,'wb') as dst: shutil.copyfileobj(src,dst,1024*1024)
                        outputs.append(str(out))
        elif tarfile.is_tarfile(archive):
            with tarfile.open(archive,'r:*') as tf:
                for member in tf.getmembers():
                    if member.isfile() and wanted(member.name):
                        src=tf.extractfile(member)
                        if src is None: continue
                        out=self.temp_dir/Path(member.name).name
                        with src,open(out,'wb') as dst: shutil.copyfileobj(src,dst,1024*1024)
                        outputs.append(str(out))
        return outputs

    @staticmethod
    def _jaxa_coord5(v,is_lat=True):
        hemi=('N' if v>=0 else 'S') if is_lat else ('E' if v>=0 else 'W'); return f'{hemi}{abs(int(v)):03d}'

    @classmethod
    def _jaxa_archive_name(cls,lat,lon):
        south=math.floor(lat/5.0)*5; west=math.floor(lon/5.0)*5; north=south+5; east=west+5
        return cls._jaxa_coord5(south,True)+cls._jaxa_coord5(west,False)+'_'+cls._jaxa_coord5(north,True)+cls._jaxa_coord5(east,False)+'.zip'

    @classmethod
    def _jaxa_direct_archive_urls(cls,lat,lon):
        south5=math.floor(lat/5.0)*5; west5=math.floor(lon/5.0)*5; group=cls._coord_token(south5,west5); tile=cls._coord_token(lat,lon); pack=cls._jaxa_archive_name(lat,lon); base='https://www.eorc.jaxa.jp/ALOS/aw3d30/data/release_v2012/'
        return [base+group+'/'+tile+'.zip',base+pack,'https://www.eorc.jaxa.jp/ALOS/en/aw3d30/data/release_v2012/'+group+'/'+tile+'.zip','https://www.eorc.jaxa.jp/ALOS/en/aw3d30/data/release_v2012/'+pack]

    @staticmethod
    def _jaxa_embedded_links(text,base_url):
        found=set()
        if not text:return found
        pats=[r"(?:href|src)\s*=\s*[\"']([^\"']+)[\"']",r"[\"']([^\"']+?\.(?:zip|tar\.gz|tgz|tar|js|xml|json|txt)(?:\?[^\"']*)?)[\"']",r"(https?://[^\s\"'<>]+?\.(?:zip|tar\.gz|tgz|tar|js|xml|json|txt)(?:\?[^\s\"'<>]*)?)"]
        for pat in pats:
            for m in re.finditer(pat,text,flags=re.I):found.add(urllib.parse.urljoin(base_url,m.group(1).strip()))
        return found

    def _jaxa_resolve_current_archives(self,session,pages,requested_tokens,groups):
        archive_links=set();assets=[];seen=set()
        def score(url):
            compact=re.sub(r'[^a-z0-9]','',url.lower());direct=sum(1 for tok in requested_tokens if tok.lower() in compact);pack=sum(1 for name in groups if name.lower().replace('.zip','').replace('.tar.gz','') in compact);return direct*20+pack*10
        for page_url in pages:
            try:text,final_url=self._jaxa_get_text(session,page_url)
            except RuntimeError as exc:self.warning.emit(f'JAXA regional page skipped: {page_url} ({exc})');continue
            for link in self._jaxa_embedded_links(text,final_url):
                low=link.lower()
                if 'eorc.jaxa.jp/alos/' not in low:continue
                if any(ext in low for ext in ('.zip','.tar.gz','.tgz','.tar')):archive_links.add(link)
                elif any(ext in low for ext in ('.js','.xml','.json','.txt')):assets.append(link)
        for asset in assets[:24]:
            if asset in seen:continue
            seen.add(asset)
            try:text,final_url=self._jaxa_get_text(session,asset)
            except RuntimeError as exc:self.warning.emit(f'JAXA metadata asset skipped: {asset} ({exc})');continue
            for link in self._jaxa_embedded_links(text,final_url):
                low=link.lower()
                if 'eorc.jaxa.jp/alos/' in low and any(ext in low for ext in ('.zip','.tar.gz','.tgz','.tar')):archive_links.add(link)
        return sorted(archive_links,key=lambda u:(-score(u),u))

    def _download_jaxa(self):
        if not self.username or not self.password: raise RuntimeError('JAXA User ID and Password are required for ALOS AW3D30.')
        if len(self.tile_ids)>50: raise RuntimeError(f'The study area intersects {len(self.tile_ids)} AW3D30 tiles. Please reduce the extent.')
        session=self._jaxa_session(); requested_tokens={self._coord_token(*self._parse_tile_id(tid)) for tid in self.tile_ids}; groups={}
        for tid in self.tile_ids:
            lat,lon=self._parse_tile_id(tid); groups.setdefault(self._jaxa_archive_name(lat,lon),[]).append((lat,lon))
        files=[]; pages=sorted({self._jaxa_region_page(*self._parse_tile_id(tid)) for tid in self.tile_ids})
        self.status.emit('JAXA AW3D30 v1.0.0: resolving current v4.x download metadata…'); candidates=self._jaxa_resolve_current_archives(session,pages,requested_tokens,groups)
        if candidates:
            candidates=candidates[:max(8,len(requested_tokens)*4)]
            for idx,url in enumerate(candidates,1):
                if self._cancelled: raise RuntimeError('Download cancelled.')
                name=Path(urllib.parse.urlparse(url).path).name or f'aw3d30_{idx}.archive'; dest=self.temp_dir/name
                try:
                    self.status.emit(f'JAXA current archive {idx}/{len(candidates)}: {name}'); a=int((idx-1)*70/max(1,len(candidates)));b=int(idx*70/max(1,len(candidates)));self._download_jaxa_file(session,url,dest,a,b,name)
                    for f in self._extract_jaxa_dsm(dest,requested_tokens):
                        if f not in files:files.append(f)
                    if all(any(tok in Path(f).name.upper() for f in files) for tok in requested_tokens):self.progress.emit(75);return {'kind':'files','files':files}
                except Exception as exc:self.warning.emit(f'{name}: {exc}')
        self.status.emit('JAXA current metadata did not yield the requested DSM; trying legacy compatibility URLs…')
        for lat,lon in [self._parse_tile_id(tid) for tid in self.tile_ids]:
            token=self._coord_token(lat,lon)
            for url in self._jaxa_direct_archive_urls(lat,lon):
                name=Path(urllib.parse.urlparse(url).path).name or token+'.zip';dest=self.temp_dir/name
                try:
                    self._download_jaxa_file(session,url,dest,1,70,name);ex=self._extract_jaxa_dsm(dest,{token})
                    for f in ex:
                        if f not in files:files.append(f)
                    if ex:break
                except Exception as exc:self.warning.emit(f'{token}: {exc}')
        if files:self.progress.emit(75);return {'kind':'files','files':files}
        page_names=', '.join(Path(urllib.parse.urlparse(u).path).name for u in pages)
        raise RuntimeError('JAXA v1.0.0 could access the AW3D30 download site, but no current archive for the requested DSM tile could be resolved from the dynamic page metadata. Regional page(s): '+page_names+'.')
