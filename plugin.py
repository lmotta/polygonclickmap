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



from qgis.PyQt.QtCore import (
    QObject, pyqtSlot, QCoreApplication,
    QVariant
)
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import (
    QAction, QToolButton, QMenu,
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QDialogButtonBox
)

from qgis.core import (
    QgsProject, QgsApplication,
    QgsFieldProxyModel, QgsField
)
from qgis.gui import QgsFieldComboBox

from .translate import Translate

from .utils import connectSignalSlot

EXISTSSCIPY = True
try:
    from .polygonclickmap import PolygonClickMapTool # from scipy import ndimage
except:
    EXISTSSCIPY = False

import os

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
        title = self.tr('Set fields: metadata(exists) and area_ha(virtual)')
        icon = QgsApplication.getThemeIcon('/propertyicons/editmetadata.svg')
        self.actions['layer_field'] = QAction( icon, title, self.iface.mainWindow() )
        self.actions['layer_field'].setToolTip( title )
        self.actions['layer_field'].triggered.connect( self.setFields )
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
        if not EXISTSSCIPY:
            msg = self.tr("Missing 'scipy' libray. Need install scipy(https://www.scipy.org/install.html)")
            self.iface.messageBar().pushCritical( self.pluginName, msg )
            return

        if checked:
            layer = self.iface.activeLayer()
            self.tool.setLayerFlood( layer )
            self.mapCanvas.setMapTool( self.tool )
            return

        self.actions['tool'].setChecked( True )

    @pyqtSlot(bool)
    def setFields(self, checked):
        def dialogFieldMetadata(layer, fieldArea, existFieldArea):
            def layoutFields():
                def fieldsComboString():
                    w = QgsFieldComboBox()
                    w.setSizeAdjustPolicy( w.AdjustToContents)
                    w.setFilters( QgsFieldProxyModel.String )
                    w.setLayer(layer)
                    w.setCurrentIndex(0)
                    fieldMetadata = layer.customProperty( PolygonClickMapTool.KEY_METADATA, None )
                    if fieldMetadata:
                        fields = w.fields()
                        idx = fields.indexOf( fieldMetadata )
                        w.setCurrentIndex( idx )
                    return w

                lyt = QHBoxLayout()
                msg = self.tr( 'Metadata field:' )
                lyt.addWidget( QLabel( msg ) )
                cmbFields = fieldsComboString()
                lyt.addWidget( cmbFields )
                return cmbFields, lyt

            def buttonOkCancel():
                def changeDefault(standardButton, default):
                    btn = btnBox.button( standardButton )
                    btn.setAutoDefault( default )
                    btn.setDefault( default )

                btnBox = QDialogButtonBox( QDialogButtonBox.Ok | QDialogButtonBox.Cancel )
                changeDefault( QDialogButtonBox.Ok, False )
                changeDefault( QDialogButtonBox.Cancel, True )
                btnBox.accepted.connect( d.accept )
                btnBox.rejected.connect( d.reject )
                return btnBox

            d = QDialog(self.iface.mainWindow() )
            d.setWindowTitle( self.pluginName )
            lytMain = QVBoxLayout()
            msg = self.tr( 'Layer: {}' )
            msg = msg.format( layer.name() )
            lbl = QLabel( msg )
            font = lbl.font()
            font.setBold( True )
            lbl.setFont( font )
            lytMain.addWidget( lbl )
            cmbFields, lyt = layoutFields()
            lytMain.addLayout( lyt )
            msg = self.tr("Virtual field '{}' exists") if existFieldArea else self.tr("Virtual field '{}' will be create")
            msg = msg.format( fieldArea )
            lytMain.addWidget( QLabel( msg ) )
            lytMain.addWidget( buttonOkCancel() )
            d.setLayout( lytMain )
            d.exec_()
            if d.result() == QDialog.Accepted:
                layer.setCustomProperty( PolygonClickMapTool.KEY_METADATA, cmbFields.currentField() )
                return True
            return False

        def fieldAreaHa(layer):
            field = QgsField('area_ha_pcm', QVariant.Double)
            exp = "area(transform($geometry,layer_property(@layer_id, 'crs'),'EPSG:5880'))/10000"
            layer.addExpressionField( exp, field )

        if not EXISTSSCIPY:
            msg = self.tr("Missing 'scipy' libray. Need install scipy(https://www.scipy.org/install.html)")
            self.iface.messageBar().pushCritical( self.pluginName, msg )
            return

        layer = self.iface.activeLayer()
        fieldArea = 'pcm_area_ha'
        existFieldArea = fieldArea in [ f.name() for f in layer.fields() ]
        if dialogFieldMetadata( layer, fieldArea, existFieldArea ):
            if not existFieldArea:
                fieldAreaHa( layer ) #  map_get( from_json("pcm_meta" ), 'rasters')[0]

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

