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
  QObject, QPointF,
  pyqtSlot, pyqtSignal
)

from qgis.PyQt.QtGui import QFont, QTextDocument

from qgis.core import (
    QgsProject,
    QgsPointXY,
    QgsTextAnnotation, QgsMarkerSymbol, QgsFillSymbol,
)


class AnnotationCanvas(QObject):
    removed = pyqtSignal()
    def __init__(self, mapCanvas):
        super().__init__()
        self.annotationManager = QgsProject.instance().annotationManager()
        self.annotationManager.annotationAboutToBeRemoved.connect( self.annotationAboutToBeRemoved )
        self.mapCanvas = mapCanvas
        self.symbol = {
            'fill': {'color': 'white', 'outline_color': 'white'},
            'marker': {'name': 'x', 'color': 'white' },
            'opacity': 0
        }
        #
        self._create() # Create self.annot
        self.active = False
        self.annotationManager = QgsProject.instance().annotationManager()

    def setText(self, text):
        def setFrameDocument():
            td = QTextDocument( text )
            td.setDefaultFont( QFont('Arial', 14) )
            self.annot.setFrameOffsetFromReferencePointMm(QPointF(0,0))
            self.annot.setFrameSize( td.size() )
            self.annot.setDocument( td )

        if not text: # None or ''
            self.active = False
            self.mapCanvas.extentsChanged.disconnect( self.extentsChanged )
            if self.annot:
                self.annot.setVisible( False )
            return
        #
        self.active = True
        self.mapCanvas.extentsChanged.connect( self.extentsChanged )
        if not self.annot in self.annotationManager.annotations():
            self._create()
            self.annotationManager.addAnnotation( self.annot )
        self._setPosition()
        setFrameDocument()
        self.annot.setVisible( True )

    def remove(self):
        if self.annot:
            self.active = False
            self.annotationManager.removeAnnotation( self.annot )

    @pyqtSlot()
    def extentsChanged(self):
        if not self.active:
            return

        if not self.annot in self.annotationManager.annotations():
            self._create()
            self.annotationManager.addAnnotation( self.annot )
        self._setPosition()

    @pyqtSlot('QgsAnnotation*')
    def annotationAboutToBeRemoved(self, annot):
        if annot == self.annot:
            self.annot = None
            self.active = False
            self.removed.emit()

    def _setPosition(self):
        e = self.mapCanvas.extent()
        p = QgsPointXY(e.xMinimum(), e.yMaximum() )
        self.annot.setMapPosition( p )

    def _create(self):
        def setFillMarker(annotation):
            annotation.setFillSymbol( QgsFillSymbol.createSimple( self.symbol['fill'] ) )
            marker = QgsMarkerSymbol.createSimple( self.symbol['marker'] )
            marker.setOpacity( self.symbol['opacity'] )
            annotation.setMarkerSymbol(  marker )

        annot = QgsTextAnnotation()
        setFillMarker( annot )
        self.annot = annot
