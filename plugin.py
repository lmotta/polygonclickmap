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

from .utils import connectSignalSlot, messageOutputHtml

from .polygonclickmap import PolygonClickMapTool

from .dialog_setup import DialogSetup


class PolygonClickMapPlugin(QObject):

    def __init__(self, iface):
        super().__init__()
        self.pluginName = 'Polygon Click Map'
        self.iface = iface
        self.mapCanvas = iface.mapCanvas() 
        self.project = QgsProject.instance()
        self.currentCrs = None

        self.translate = Translate( type(self).__name__ )
        self.tr = self.translate.tr

        self.actions = {}
        self.toolButton = QToolButton()
        self.toolButton.setMenu( QMenu() )
        self.toolButton.setPopupMode( QToolButton.MenuButtonPopup )
        self.toolBtnAction = self.iface.addToolBarWidget( self.toolButton )
        self.titleTool = self.tr('Create polygon by clicking on the map')

        self.editingSignalSlot = lambda layer: {
            layer.editingStarted: self._editingStarted,
            layer.editingStopped: self._editingStopped
        }.items()

        self.tool = PolygonClickMapTool( iface, self.pluginName )

    def initGui(self):
        def createAction(icon, title, calback, toolTip=None, isCheckable=False):
            action = QAction( icon, title, self.iface.mainWindow() )
            if toolTip:
                action.setToolTip( toolTip )
            action.triggered.connect( calback )
            action.setCheckable( isCheckable )
            self.iface.addPluginToMenu( f"&{self.titleTool}" , action )
            return action

        # Action Tool
        icon = QIcon( os.path.join( os.path.dirname(__file__), 'resources', 'polygonclickmap.svg' ) )
        toolTip = self.tr('Only for editable layers.')
        toolTip = f"{self.titleTool}. *{toolTip}"
        self.actions['tool'] = createAction( icon, self.titleTool, self.runTool, toolTip, True )
        self.tool.setAction( self.actions['tool'] )
        # Action setFields
        title = self.tr('Setup...')
        icon = QgsApplication.getThemeIcon('/propertyicons/general.svg')
        self.actions['layer_field'] = createAction( icon, title, self.runSetup )
        # Action About
        title = self.tr('About...')
        icon = QgsApplication.getThemeIcon('/mActionHelpContents.svg')
        self.actions['about'] = createAction( icon, title, self.runAbout )
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
        args = (
            self.iface.mainWindow(),
            self.pluginName,
            layer,
            {
                'metadata': PolygonClickMapTool.KEY_METADATA,
                'adjacent_pixels': PolygonClickMapTool.KEY_ADJACENTPIXELS,
                'adjusts_border': PolygonClickMapTool.KEY_ADJUSTSBORDER
            }
        )
        dlg = DialogSetup( *args )
        if self.currentCrs:
            dlg.setCurrentCrs( self.currentCrs )
        if dlg.exec_() == dlg.Accepted:
            self.currentCrs = dlg.currentCrs()

    @pyqtSlot(bool)
    def runAbout(self, checked):
        title = self.tr('{} - About')
        title = title.format( self.pluginName )
        args = {
            'title': title,
            'prefixHtml': 'about',
            'dirHtml': os.path.join( os.path.dirname(__file__), 'resources' )
        }
        messageOutputHtml( **args )

    @pyqtSlot('QgsMapLayer*')
    def _currentLayerChanged(self, layer):
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

