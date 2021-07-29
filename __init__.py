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

from qgis.core import QgsProject

from .imagefloodtool import ImageFloodTool

from .utils import connectSignalSlot

import os

def classFactory(iface):
    return ImageFloodToolPlugin( iface )

class ImageFloodToolPlugin(QObject):

    def __init__(self, iface):
        super().__init__()
        self.iface = iface
        self.mapCanvas = iface.mapCanvas() 
        self.project = QgsProject.instance()

        self.action = None
        self.tool = ImageFloodTool( iface )

        self.editingSignalSlot = lambda layer: {
            layer.editingStarted: self._editingStarted,
            layer.editingStopped: self._editingStopped
        }.items()

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
        self.action.setEnabled( False )
        self.tool.setAction( self.action )

        self.iface.addToolBarIcon( self.action )
        self.iface.addPluginToMenu( self.menu, self.action )

        self.iface.currentLayerChanged.connect( self._currentLayerChanged )

    def unload(self):
        self.mapCanvas.unsetMapTool( self.tool )
        self.iface.removeToolBarIcon( self.action )
        self.iface.removePluginMenu( self.menu, self.action )
        self.iface.currentLayerChanged.disconnect( self._currentLayerChanged )
        del self.action

    @pyqtSlot(bool)
    def run(self, checked):
        if checked:
            layer = self.iface.activeLayer()
            self.tool.setLayerFlood( layer )
            self.mapCanvas.setMapTool( self.tool )
            return

        self.action.setChecked( True )
        
    @pyqtSlot('QgsMapLayer*')
    def _currentLayerChanged(self, layer):
        if self.tool.isPolygon( layer ):
            isEditabled = layer.isEditable()
            self.action.setEnabled( isEditabled )
            if isEditabled:
                if self.tool.isActive() and not layer == self.tool.layerFlood:
                    self.tool.setLayerFlood( layer )
                return

            for signal, slot in self.editingSignalSlot( layer ):
                connectSignalSlot( signal, slot )

        self.action.setEnabled(False)

    @pyqtSlot()
    def _editingStarted(self):
        self.action.setEnabled( True )
        if self.tool.isActive():
            self.tool.setLayerFlood( self.iface.activeLayer() )
            return

    @pyqtSlot()
    def _editingStopped(self):
        self.action.setEnabled( False )

