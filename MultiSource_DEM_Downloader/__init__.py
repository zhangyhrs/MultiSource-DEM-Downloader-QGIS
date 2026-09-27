# -*- coding: utf-8 -*-
def classFactory(iface):
    from .plugin import DEMDownloaderPlugin
    return DEMDownloaderPlugin(iface)
