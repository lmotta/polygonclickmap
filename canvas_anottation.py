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
    def __init__(self, mapCanvas):
        super().__init__()
        self.mapCanvas = mapCanvas
        self.symbol = {
            'fill': {'color': 'white', 'outline_color': 'red'},
            'marker': {'name': 'x', 'color': 'white' },
            'opacity': 0
        }
        #
        self.annotationManager = QgsProject.instance().annotationManager()
        self.annot = None # _create
        self.text = None

    def setText(self, text):
        self.text = text
        if not self.annot in self.annotationManager.annotations():
            self._create()
            self.annotationManager.addAnnotation( self.annot )
        self._setPosition()

    def remove(self):
        if self.annot:
            self.annotationManager.removeAnnotation( self.annot )
            self.annot = None

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

        def setFrameDocument(annot):
            td = QTextDocument( self.text )
            td.setDefaultFont( QFont('Noto Sans', 12) )
            annot.setFrameOffsetFromReferencePointMm(QPointF(0,0))
            annot.setFrameSize( td.size() )
            annot.setDocument( td )

        annot = QgsTextAnnotation()
        setFillMarker( annot )
        setFrameDocument( annot)
        self.annot = annot
