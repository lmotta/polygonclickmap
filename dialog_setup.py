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
    pyqtSlot,
    QVariant,
    QRegExp,
    QSize
)
from qgis.PyQt.QtGui import QRegExpValidator
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QGroupBox,
    QLabel, QLineEdit,
    QDialogButtonBox,
    QSpacerItem, QSizePolicy
)

from qgis.core import (
    QgsApplication,
    QgsFieldProxyModel, QgsField,
    QgsCoordinateReferenceSystem
)
from qgis.gui import (
    QgsFieldComboBox,
    QgsMessageBar,
    QgsProjectionSelectionWidget
)


def boldLabel(lbl):
    font = lbl.font()
    font.setBold( True )
    lbl.setFont( font )


def buttonOkCancel():
    def changeDefault(standardButton, default):
        btn = btnBox.button( standardButton )
        btn.setAutoDefault( default )
        btn.setDefault( default )

    btnBox = QDialogButtonBox( QDialogButtonBox.Ok | QDialogButtonBox.Cancel )
    changeDefault( QDialogButtonBox.Ok, False )
    changeDefault( QDialogButtonBox.Cancel, True )
    return btnBox


class DialogSetup(QDialog):
    def __init__(self, parent, title, layer, keyMetadata):
        super().__init__( parent )
        self.title = title
        self.layer = layer
        self.keyMetadata = keyMetadata

        self.msgBar = QgsMessageBar()

        self.expArea = "area(transform($geometry,layer_property(@layer_id,'crs'),'{}'))/10000"
        self.statusArea = self._statusFieldArea( layer ) # { 'exists': True/False } if True: { 'name', 'index', 'crs' }
        
        self.leNameField, self.psCrs, self.cmbFieldsMetadata = None, None, None
        lytFields = self._layoutFields() 

        self.setWindowTitle( title )
        lytMain = QVBoxLayout()
        lytMain.addWidget( self.msgBar )
        lytMain.addWidget( self._widgetLayer() )
        gpbFields = QGroupBox( self.tr('Fields') )
        gpbFields.setLayout( lytFields )
        lytMain.addWidget( gpbFields )
        btnBox = buttonOkCancel()
        btnBox.accepted.connect( self.accept )
        btnBox.rejected.connect( self.reject )
        lytMain.addWidget( btnBox )
        lytMain.addItem( QSpacerItem( 10, 10, QSizePolicy.Minimum, QSizePolicy.Expanding ) )
        self.setLayout( lytMain )

    def _statusFieldArea(self, layer):
        ini_expArea = self.expArea.split('{')[0]
        end_expArea = self.expArea.split('}')[1]
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
                'exists': False
            }

        return {
            'exists': True,
            'name': fields.at( idxExpr ).name(),
            'index': idxExpr,          
            'crs': exp[ len(ini_expArea):-1*len(end_expArea) ]
        }

    def _messageErrorCrs(self):
        msg = self.tr('Invalid CRS(need be projected)')
        self.msgBar.pushCritical( self.title, msg )

    def _widgetLayer(self):
        msg = self.tr( 'Layer: {}' )
        msg = msg.format( self.layer.name() )
        lbl = QLabel( msg )
        boldLabel( lbl )
        return lbl

    def _layoutFields(self):
        def fieldsComboString():
            w = QgsFieldComboBox()
            w.setSizeAdjustPolicy( w.AdjustToContents)
            w.setFilters( QgsFieldProxyModel.String )
            w.setLayer( self.layer )
            w.setCurrentIndex(0)
            fieldMetadata = self.layer.customProperty( self.keyMetadata, None )
            if fieldMetadata:
                fields = w.fields()
                idx = fields.indexOf( fieldMetadata )
                w.setCurrentIndex( idx )
            return w

        def projectionSelectionWidget():
            p = QgsProjectionSelectionWidget()
            for opt in ( p.LayerCrs, p.ProjectCrs, p.CurrentCrs, p.DefaultCrs, p.RecentCrs ):
                p.setOptionVisible( opt, False )
            return p

        def labelIconNumber():
            icon = QgsApplication.getThemeIcon('/mIconFieldFloat.svg')
            lbl = QLabel()
            lbl.setPixmap( icon.pixmap( QSize(16, 16) ) )
            return lbl

        @pyqtSlot(QgsCoordinateReferenceSystem)
        def crsChanged(crs):
            if crs.isGeographic():
                self._messageErrorCrs()

        lytFields = QVBoxLayout()
        # Metadata
        lytMetadata = QHBoxLayout()
        msg = self.tr( 'Metadata:' )
        lytMetadata.addWidget( QLabel( msg ) )
        self.cmbFieldsMetadata = fieldsComboString()
        lytMetadata.addWidget( self.cmbFieldsMetadata )
        lytMetadata.addItem( QSpacerItem( 10, 10, QSizePolicy.Expanding, QSizePolicy.Minimum ) )
        lytFields.addLayout( lytMetadata )
        # Area Ha
        lytArea = QHBoxLayout()
        lytArea.addWidget( labelIconNumber() )
        lytArea.addWidget( QLabel( self.tr('Field name:') ) )
        if self.statusArea['exists']:
            lbl = QLabel( self.statusArea['name'] )
            boldLabel( lbl )
            lytArea.addWidget( lbl )
        else:
            self.leNameField = QLineEdit('area_ha')
            regex = QRegExp('[A-Za-z0-9_]+')
            validator = QRegExpValidator( regex )
            self.leNameField.setValidator( validator )
            lytArea.addWidget( self.leNameField )
        lytArea.addItem( QSpacerItem( 10, 10, QSizePolicy.Expanding, QSizePolicy.Minimum ) )
        # CRS
        self.psCrs = projectionSelectionWidget()
        if self.statusArea['exists']:
            crs = QgsCoordinateReferenceSystem( self.statusArea['crs'] )
            if not crs.isGeographic():
                self.psCrs.setCrs( crs )
        self.psCrs.crsChanged.connect( crsChanged )
        lytCrs = QHBoxLayout()
        lytCrs.addWidget( self.psCrs )
        # Area + CRS
        lytAreaCrs = QVBoxLayout()
        lytAreaCrs.addLayout( lytArea )
        lytAreaCrs.addLayout( lytCrs )
        gpbArea = QGroupBox( self.tr('Virtual area(ha)') )
        gpbArea.setLayout( lytAreaCrs )
        #
        lytFields.addWidget( gpbArea )
        
        return lytFields

    def _addArea(self):
        field = QgsField( self.leNameField.text(), QVariant.Double )
        expr = self.expArea.format( self.psCrs.crs().authid() )
        self.layer.addExpressionField( expr, field )

    def _updateArea(self):
        index = self.statusArea['index']
        expr = self.expArea.format( self.psCrs.crs().authid() )
        self.layer.updateExpressionField( index, expr )

    def currentCrs(self):
        return self.psCrs.crs()

    def setCurrentCrs(self, crs):
        return self.psCrs.setCrs( crs )

    @pyqtSlot()
    def accept(self):
        crs = self.psCrs.crs()
        if not crs.isValid() or crs.isGeographic():
            self._messageErrorCrs()
            return

        if not self.statusArea['exists']:
            if not self.leNameField.text(): # empty
                msg = self.tr('Virtual area is empty')
                self.msgBar.pushCritical( self.title, msg )
                return

        currentField = self.cmbFieldsMetadata.currentField()
        if currentField:
            # Get Values Metadata: map_get( from_json("pcm_meta" ), 'rasters')[0]
            self.layer.setCustomProperty( self.keyMetadata, currentField )
        else:
            self.layer.removeCustomProperty( self.keyMetadata ) 
        f = self._addArea if not self.statusArea['exists'] else self._updateArea
        f()

        super().accept()
