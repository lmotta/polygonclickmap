# -*- coding: utf-8 -*-
"""
/***************************************************************************
Name                 : Create polygon by clicking in map.
Description          : Plugin for create polygon by clicking in map.
Date                 : August, 2021
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
__date__ = '2021-08-01'
__copyright__ = '(C) 2021, Luiz Motta'
__revision__ = '$Format:%H$'


import os

from qgis.PyQt.QtCore import QObject, pyqtSlot 
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QToolButton, QMenu

from qgis.core import QgsProject, QgsApplication

from .translate import Translate

from .utils import connectSignalSlot

EXISTSSCIPY = True
try:
    from .polygonclickmap import PolygonClickMapTool # from scipy import ndimage
except:
    EXISTSSCIPY = False

from .dialog_setup import DialogSetup


class PolygonClickMapPlugin(QObject):

    def __init__(self, iface):
        super().__init__()
        self.pluginName = 'Polygon Click Map'
        self.iface = iface
        self.mapCanvas = iface.mapCanvas() 
        self.project = QgsProject.instance()

        self.translate = Translate( type(self).__name__ )
        self.tr = self.translate.tr

        self.actions = { 'tool': None, 'layer_field': None }
        self.toolButton = QToolButton()
        self.toolButton.setMenu( QMenu() )
        self.toolButton.setPopupMode( QToolButton.MenuButtonPopup )
        self.toolBtnAction = self.iface.addToolBarWidget( self.toolButton )
        self.titleTool = self.tr('Create polygon by clicking in map')

        self.editingSignalSlot = lambda layer: {
            layer.editingStarted: self._editingStarted,
            layer.editingStopped: self._editingStopped
        }.items()

        self.messageExistsScipy = False
        if EXISTSSCIPY:
            self.tool = PolygonClickMapTool( iface, self.pluginName )

    def initGui(self):
        # Action Tool
        icon = QIcon( os.path.join( os.path.dirname(__file__), 'polygonclickmap.svg' ) )
        self.actions['tool'] = QAction( icon, self.titleTool, self.iface.mainWindow() )
        self.actions['tool'].setToolTip( self.titleTool )
        self.actions['tool'].triggered.connect( self.runTool )
        self.actions['tool'].setCheckable( True )
        if EXISTSSCIPY:
            self.tool.setAction( self.actions['tool'] )
        self.iface.addPluginToMenu( f"&{self.titleTool}" , self.actions['tool'] )
        # Action setFields
        title = self.tr('Setup')
        icon = QgsApplication.getThemeIcon('/propertyicons/general.svg')
        self.actions['layer_field'] = QAction( icon, title, self.iface.mainWindow() )
        self.actions['layer_field'].setToolTip( title )
        self.actions['layer_field'].triggered.connect( self.runSetup )
        self.iface.addPluginToMenu( f"&{self.titleTool}" , self.actions['layer_field'] )
        #
        self._enabled(False)
        m = self.toolButton.menu()
        for k in self.actions:
            m.addAction( self.actions[ k ] )
        self.toolButton.setDefaultAction( self.actions['tool'] )

        self.iface.currentLayerChanged.connect( self._currentLayerChanged )

    def unload(self):
        for action in [ self.actions['tool'], self.actions['layer_field'] ]:
            self.iface.removePluginMenu( f"&{self.titleTool}", action )
            self.iface.removeToolBarIcon( action )
            self.iface.unregisterMainWindowAction( action )
        self.iface.removeToolBarIcon( self.toolBtnAction )
        self.mapCanvas.unsetMapTool( self.tool )
        self.iface.currentLayerChanged.disconnect( self._currentLayerChanged )

    def _enabled(self, enable):
        for k in self.actions:
            self.actions[ k ].setEnabled( enable )

    @pyqtSlot(bool)
    def runTool(self, checked):
        if checked:
            layer = self.iface.activeLayer()
            self.tool.setLayerFlood( layer )
            self.mapCanvas.setMapTool( self.tool )
            return

        self.actions['tool'].setChecked( True )

    @pyqtSlot(bool)
    def runSetup(self, checked):
        layer = self.iface.activeLayer()
        dlg = DialogSetup( self.iface.mainWindow(), self.pluginName, layer, PolygonClickMapTool.KEY_METADATA )
        dlg.exec_()

    @pyqtSlot('QgsMapLayer*')
    def _currentLayerChanged(self, layer):
        if not EXISTSSCIPY and not self.messageExistsScipy:
            msg = self.tr("Missing 'scipy' libray. Need install scipy(https://www.scipy.org/install.html)")
            self.iface.messageBar().pushCritical( self.pluginName, msg )
            self.messageExistsScipy = True
            return

        if self.tool.isPolygon( layer ):
            isEditabled = layer.isEditable()
            self._enabled( isEditabled )
            if isEditabled:
                if self.tool.isActive() and not layer == self.tool.layerFlood:
                    self.tool.setLayerFlood( layer )
                return

            for signal, slot in self.editingSignalSlot( layer ):
                connectSignalSlot( signal, slot )

        self._enabled(False)

    @pyqtSlot()
    def _editingStarted(self):
        self._enabled(True)
        if self.tool.isActive():
            self.tool.setLayerFlood( self.iface.activeLayer() )
            return

    @pyqtSlot()
    def _editingStopped(self):
        self._enabled(False)

