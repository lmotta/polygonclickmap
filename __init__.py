# -*- coding: utf-8 -*-
"""
/***************************************************************************
Name                 : Image flood tool
Description          : Plugin for create polygon from the image using flood algorithm.
Date                 : July, 2021
copyright            : (C) 2021 by Luiz Motta
email                : motta.luiz@gmail.com

 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

__author__ = 'Luiz Motta'
__date__ = '2021-07-01'
__copyright__ = '(C) 2021, Luiz Motta'
__revision__ = '$Format:%H$'



from qgis.PyQt.QtCore import QObject, pyqtSlot
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction

from .imagefloodtool import ImageFloodTool

import os

def classFactory(iface):
    return ImageFloodToolPlugin( iface )

class ImageFloodToolPlugin(QObject):

    def __init__(self, iface):
        super().__init__()
        self.iface = iface
        self.mapCanvas = iface.mapCanvas() 

        self.action = None
        self.tool = ImageFloodTool( iface )

    def initGui(self):
        title = "Create polygon from image using flood algorithm"
        icon = QIcon( os.path.join( os.path.dirname(__file__), 'imagefloodtool.svg' ) )
        self.action = QAction( icon, title, self.iface.mainWindow() )
        self.action.setObjectName( "MapItemImageFlood" )
        self.action.setWhatsThis( title )
        self.action.setStatusTip( title )
        self.action.triggered.connect( self.run )
        self.menu = "&Image flood tool"

        # Maptool
        self.action.setCheckable( True )
        self.tool.setAction( self.action )

        self.iface.addToolBarIcon( self.action )
        self.iface.addPluginToMenu( self.menu, self.action )

    def unload(self):
        self.mapCanvas.unsetMapTool( self.tool )
        self.iface.removeToolBarIcon( self.action )
        self.iface.removePluginMenu( self.menu, self.action )
        del self.action

    @pyqtSlot(bool)
    def run(self, checked):
        layer = self.iface.activeLayer()
        if not self.tool.isEditabledPolygon( layer ):
            msg = f"Invalid layer \"{layer.name()}\", need be Editable Polygon"
            self.tool.msgBar.pushWarning( self.tool.PLUGINNAME, msg )
            return

        if self.mapCanvas.mapTool() != self.tool:
            self.tool.setLayerFlood( layer )
            self.mapCanvas.setMapTool( self.tool)
