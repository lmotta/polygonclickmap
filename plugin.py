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
    QVariant,
    QRegExp
)
from qgis.PyQt.QtGui import QIcon, QRegExpValidator
from qgis.PyQt.QtWidgets import (
    QAction, QToolButton, QMenu,
    QDialog, QVBoxLayout, QHBoxLayout,
    QGroupBox,
    QLabel, QLineEdit,
    QDialogButtonBox,
    QSpacerItem, QSizePolicy
)

from qgis.core import (
    QgsProject, QgsApplication,
    QgsFieldProxyModel, QgsField,
    QgsCoordinateReferenceSystem
)
from qgis.gui import (
    QgsFieldComboBox,
    QgsMessageBar,
    QgsProjectionSelectionWidget
)

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
        def statusFieldArea(layer):
            expArea = "area(transform($geometry,layer_property(@layer_id,'crs'),'{}'))/10000"
            ini_expArea = expArea.split('{')[0]
            end_expArea = expArea.split('}')[1]
            fields = layer.fields()
            idxExpr = -1
            for idx in range( fields.count() ):
                if fields.OriginExpression == fields.fieldOrigin( idx ) and fields.at( idx ).type() == QVariant.Double:
                    idxOrigin = fields.fieldOriginIndex( idx )
                    exp = layer.expressionField( idxOrigin ).replace(' ', '')
                    if exp.find( ini_expArea ) != -1 and exp.find( end_expArea ) != -1:
                        idxExpr = idx
                        break
            if idxExpr == -1:
                return {
                    'exists': False,
                    'expr': expArea
                }

            return {
                'exists': True,
                'expr': expArea,
                'name': fields.at( idxExpr ).name(),
                'index': idxExpr,          
                'crs': exp[ len(ini_expArea):-1*len(end_expArea) ]
            }

        def dialogSetup(layer, statusArea):
            def boldLabel(lbl):
                font = lbl.font()
                font.setBold( True )
                lbl.setFont( font )

            def messageErrorCrs():
                msg = self.tr('Invalid CRS(need be projected)')
                msgBar.pushCritical( self.pluginName, msg )

            def widgetLayer():
                msg = self.tr( 'Layer: {}' )
                msg = msg.format( layer.name() )
                lbl = QLabel( msg )
                boldLabel( lbl )
                return lbl

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

                @pyqtSlot(QgsCoordinateReferenceSystem)
                def crsChanged(crs):
                    if crs.isGeographic():
                        messageErrorCrs()

                lytFields = QVBoxLayout()
                # Metadata
                lytMetadata = QHBoxLayout()
                msg = self.tr( 'Metadata:' )
                lytMetadata.addWidget( QLabel( msg ) )
                cmbFields = fieldsComboString()
                lytMetadata.addWidget( cmbFields )
                #lytMetadata.addItem( QSpacerItem( 10, 10, QSizePolicy.Expanding, QSizePolicy.Minimum ) )
                lytFields.addLayout( lytMetadata )
                #
                result = {
                    'cmbFields': cmbFields,
                    'layout': lytFields,
                }
                # Area Ha
                lytArea = QHBoxLayout()
                lytArea.addWidget( QLabel( self.tr('Field name:') ) )
                if statusArea['exists']:
                    lbl = QLabel( statusArea['name'] )
                    boldLabel( lbl )
                    lytArea.addWidget( lbl )
                else:
                    result['lblName'] = QLineEdit('area_ha')
                    regex = QRegExp('[A-Za-z0-9_]+')
                    validator = QRegExpValidator( regex )
                    result['lblName'].setValidator( validator )
                    lytArea.addWidget( result['lblName'] )
                # CRS
                psCrs = QgsProjectionSelectionWidget()
                result['psCrs'] = psCrs
                for opt in ( psCrs.LayerCrs, psCrs.ProjectCrs, psCrs.CurrentCrs, psCrs.DefaultCrs, psCrs.RecentCrs ):
                    psCrs.setOptionVisible( opt, False )
                if statusArea['exists']:
                    crs = QgsCoordinateReferenceSystem( statusArea['crs'] )
                    if not crs.isGeographic():
                        psCrs.setCrs( crs )
                psCrs.crsChanged.connect( crsChanged )
                lytCrs = QHBoxLayout()
                lytCrs.addWidget( psCrs )
                # Area + CRS
                lytAreaCrs = QVBoxLayout()
                lytAreaCrs.addLayout( lytArea )
                lytAreaCrs.addLayout( lytCrs )
                gpbArea = QGroupBox( self.tr('Virtual area(ha)') )
                gpbArea.setLayout( lytAreaCrs )
                #
                lytFields.addWidget( gpbArea )
                return result

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

            def addArea(nameField, expr):
                field = QgsField( nameField, QVariant.Double )
                layer.addExpressionField( expr, field )

            def updateArea(index, expr):
                layer.updateExpressionField( index, expr )

            d = QDialog(self.iface.mainWindow() )
            d.setWindowTitle( self.pluginName )
            lytMain = QVBoxLayout()
            msgBar = QgsMessageBar()
            lytMain.addWidget( msgBar )
            lytMain.addWidget( widgetLayer() )
            infoLayoutFields = layoutFields()
            gpbFields = QGroupBox( self.tr('Fields') )
            gpbFields.setLayout( infoLayoutFields['layout'] )
            lytMain.addWidget( gpbFields )
            lytMain.addWidget( buttonOkCancel() )
            lytMain.addItem( QSpacerItem( 10, 10, QSizePolicy.Minimum, QSizePolicy.Expanding ) )
            d.setLayout( lytMain )
            while True:
                d.exec_()
                if d.result() == QDialog.Accepted:
                    if infoLayoutFields['psCrs'].crs().isGeographic():
                        messageErrorCrs()
                        continue

                    if not statusArea['exists']:
                        name = infoLayoutFields['lblName'].text()
                        if not name: # empty
                            msg = self.tr('Virtual area is empty')
                            msgBar.pushCritical( self.pluginName, msg )
                            continue

                    currentField = infoLayoutFields['cmbFields'].currentField()
                    if currentField:
                        # Get Values Metadata: map_get( from_json("pcm_meta" ), 'rasters')[0]
                        layer.setCustomProperty( PolygonClickMapTool.KEY_METADATA, currentField )
                    expr = statusArea['expr'].format( infoLayoutFields['psCrs'].crs().authid() )
                    if not statusArea['exists']:
                        name = infoLayoutFields['lblName'].text()
                        addArea( name, expr )
                    else:
                        updateArea( statusArea['index'], expr )
                break

        layer = self.iface.activeLayer()
        status = statusFieldArea( layer )
        dialogSetup( layer, status )

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

