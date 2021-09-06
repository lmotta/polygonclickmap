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
    Qt, QDateTime,
    QObject, pyqtSlot, pyqtSignal
)
from qgis.PyQt.QtWidgets import (
    QLabel, QSpinBox, QPushButton,
    QFrame,
    QMessageBox,
    QStyle
)
from qgis.PyQt.QtXml import QDomDocument

from qgis.core import (
    QgsProject, QgsApplication, Qgis,
    QgsMapLayer, QgsVectorLayer,
    QgsGeometry, QgsFeature, QgsWkbTypes,
    QgsCoordinateReferenceSystem, QgsCoordinateTransform,
    QgsTask
)
from qgis.gui import QgsMapTool

from osgeo import gdal, ogr

import os, json

from .utils import (
    MapItemLayers, CanvasArrayRGB, CalculateArrayFlood, 
    datasetImageFromArray, memoryRasterLayerFromDataset,
    adjustsBorder,
    messageOutputHtml
)


class ImageFlood(QObject):
    finishMovingFloodCanvas = pyqtSignal(bool)
    finishAddedFloodCanvas = pyqtSignal(bool, int)
    finishAddedMoveFloodCanvas = pyqtSignal(bool, int)
    message = pyqtSignal(str, Qgis.MessageLevel)
    def __init__(self, mapCanvas):
        def loadDocStyle(qmlName):
            filepath = os.path.join( os.path.dirname(__file__), 'resources', qmlName )
            doc = QDomDocument('qgis')
            with open( filepath ) as f: doc.setContent( f.read() )
            return doc

        super().__init__()
        self.canvasArray = CanvasArrayRGB( mapCanvas )
        self.mapItem = MapItemLayers( mapCanvas )
        self.calcFlood = CalculateArrayFlood()

        mapCanvas.destinationCrsChanged.connect( self.destinationCrsChanged )

        self.taskManager = QgsApplication.taskManager()
        self.taskCreateFlood = None

        self.arrys_flood = []
        self.arrys_flood_delete = []
        self.arryFloodMove = None

        self.lyrSeed = None

        self.rastersCanvas = None # [ RasterLayer inside Canvas]

        self.stylePoint = loadDocStyle('pointflood.qml')
        self.styleRaster = loadDocStyle('rasterflood.qml')

        self.vsimemNameRasterFlood = '/vsimem/raster_flood.tif'

        self.smooth_iter = 1
        self.smooth_offset  = 0.25

    def __del__(self):
        self.canvasArray.array = None
        try:
            gdal.Unlink( self.vsimemNameRasterFlood )
        except:
            pass

    def setLayerSeed(self, pointMap):
        def createQgsSeedVector():
            crs = self.mapItem.mapCanvas.mapSettings().destinationCrs().authid()
            uri = f"point?crs={crs}"
            l = QgsVectorLayer( uri, 'seed', 'memory')
            prov = l.dataProvider()
            f = QgsFeature()
            f.setGeometry( QgsGeometry.fromPointXY( pointMap ) )
            prov.addFeature( f )
            l.updateExtents()
            l.importNamedStyle( self.stylePoint )
            return l

        self.lyrSeed = createQgsSeedVector()

    def updateCanvasImage(self):
        self.arrys_flood *= 0
        self.arrys_flood_delete *= 0
        self.canvasArray.process( self.rastersCanvas )
        if self.canvasArray.array is None:
            raise TypeError("Error created image from canvas. Check exists raster layer visible")
        if not self.calcFlood.setFloodValue( self.canvasArray.array ):
            raise TypeError("Impossible define value of seed")

    def getRasterCanvas(self):
        return self.canvasArray.rasterLayers()

    def changedCanvas(self):
        return self.canvasArray.changedCanvas()

    def calculateThreshold(self, point1, point2):
        return self.calcFlood.getThresholdFlood( point1, point2 )

    def threshold(self):
        return self.calcFlood.threshFlood

    def setThreshold(self, threshold):
        self.calcFlood.threshFlood = threshold

    def thresholdMinMax(self):
        return self.calcFlood.minValue, self.calcFlood.maxValue

    def setCoordinatesAdjacentFlood(self, is8pixel):
        self.calcFlood.setCoordinatesAdjacentPixels( is8pixel )

    def totalFlood(self):
        return len( self.arrys_flood )
 
    def rasterCanvasNames(self):
        return [ l.name() for l in self.rastersCanvas ]

    def existsProcessingFlood(self):
        return not self.taskCreateFlood is None

    def enabledFloodCanvas(self, enabled=True):
        self.mapItem.enabled = enabled
        self.mapItem.updateCanvas()

    def removeAllFloodCanvas(self):
        self.arrys_flood *= 0
        self.arrys_flood_delete *= 0
        self._setMapItem( False )

    def movingFloodCanvas(self, pointCanvas, threshFlood):
        def finished(exception, dataResult):
            self._finishedFloodCanvas( dataResult )
            self.finishMovingFloodCanvas.emit( not dataResult['isCanceled'] )

        def run(task):
            self.taskCreateFlood = task
            arryFlood, totalPixels = self._createFlood( pointCanvas, threshFlood )
            dataResult = { 'isCanceled': arryFlood is None,  'totalPixels': totalPixels }
            if totalPixels:
                self.arryFloodMove = arryFlood
                dataResult['rasterFlood'] = self._rasterFlood( arryFlood )
            return dataResult

        self.arryFloodMove = None
        task = QgsTask.fromFunction('PolygonClickImage moving', run, on_finished=finished )
        self.taskManager.addTask( task )
        # Debug
        # r = run( task )
        # finished( None, r )

    def addFloodCanvas(self, pointCanvas):
        def finished(exception, dataResult):
            self._finishedFloodCanvas( dataResult )
            self.finishAddedFloodCanvas.emit( not dataResult['isCanceled'], dataResult['totalPixels'] )

        def run(task):
            self.taskCreateFlood = task
            arryFlood, totalPixels = self._createFlood( pointCanvas)
            dataResult = { 'isCanceled': arryFlood is None, 'totalPixels': totalPixels }
            if totalPixels:
                self.arrys_flood.append( arryFlood )
            if len( self.arrys_flood ):
                dataResult['rasterFlood'] = self._rasterFlood( self._reduceArrysFlood() )
            return dataResult

        task = QgsTask.fromFunction('PolygonClickImage add flood', run, on_finished=finished )
        self.taskManager.addTask( task )
        # Debug
        # r = run( task )
        # finished( None, r )

    def addFloodMoveCanvas(self):
        def finished(exception, dataResult):
            self._finishedFloodCanvas( dataResult )
            self.finishAddedMoveFloodCanvas.emit( True, dataResult['totalPixels'] )

        def run(task):
            self.taskCreateFlood = task
            dataResult = {
                'totalPixels': 0
            }
            if not self.arryFloodMove is None:
                self.arrys_flood.append( self.arryFloodMove )
                dataResult['totalPixels'] = ( self.arryFloodMove == self.calcFlood.flood_value_color ).sum().item()
            if len( self.arrys_flood ):
                dataResult['rasterFlood'] = self._rasterFlood( self._reduceArrysFlood() )
            return dataResult

        task = QgsTask.fromFunction('PolygonClickImage add move flood', run, on_finished=finished )
        self.taskManager.addTask( task )
        # Debug
        # r = run( task )
        # finished( None, r )

    def deleteFloodCanvas(self):
        if not len( self.arrys_flood ):
            return False
        self.arrys_flood_delete.append( self.arrys_flood.pop() )
        total = len( self.arrys_flood )
        self._setMapItem( total > 0 )
        return True

    def undoFlood(self):
        if not len( self.arrys_flood_delete ):
            return False
        self.arrys_flood.append( self.arrys_flood_delete.pop() )
        self._setMapItem()
        return True

    def fillHolesFlood(self):
        if not len( self.arrys_flood ):
            return False
        arry = self.arrys_flood.pop()
        try:
            from scipy import ndimage
        except:
            msg = self.tr("Missing 'scipy' libray. Need install scipy(https://www.scipy.org/install.html)")
            self.message.emit( msg , Qgis.Critical )
            return False
        binary_holes = ndimage.binary_fill_holes( arry )
        arry[ binary_holes ] = self.calcFlood.flood_value_color
        self.arrys_flood.append( arry )
        self._setMapItem()
        return True

    def polygonizeFlood(self, layerFlood, metadata, hasAdjustsBorder):
        def polygonizeFlood(arrayFlood):
            args = self.canvasArray.getGeoreference()
            args['array'] = arrayFlood
            # Raster
            dsRaster = datasetImageFromArray( **args )
            band = dsRaster.GetRasterBand(1)
            # Vector
            ds = ogr.GetDriverByName('MEMORY').CreateDataSource('memData')
            layer = ds.CreateLayer( name='memLayer', srs=args['spatialRef'], geom_type=ogr.wkbPolygon )
            gdal.Polygonize( srcBand=band, maskBand=band, outLayer=layer, iPixValField=-1)
            dsRaster = None
            #
            return layer, ds

        layer, ds = polygonizeFlood( self._reduceArrysFlood() )
        totalFeats = layer.GetFeatureCount()
        if not totalFeats:
            return 0

        crsLayer = layerFlood.crs()
        crsDS = QgsCoordinateReferenceSystem()
        crsDS.createFromString( layer.GetSpatialRef().ExportToWkt() )
        ct = QgsCoordinateTransform( crsDS, crsLayer, QgsProject.instance() )
        fields = layerFlood.fields()
        for feat in layer:
            g = QgsGeometry()
            g.fromWkb( feat.GetGeometryRef().ExportToIsoWkb() )
            g = g.smooth( self.smooth_iter, self.smooth_offset )
            g.transform( ct )
            f = QgsFeature( fields )
            if hasAdjustsBorder:
                g = adjustsBorder( g, layerFlood )
            f.setGeometry( g )
            if metadata:
                f[ metadata['field'] ] = metadata['value']
            layerFlood.addFeature( f )
        ds = None
        layerFlood.updateExtents()
        layerFlood.triggerRepaint()

        self.arrys_flood *= 0
        self.arrys_flood_delete *= 0

        self._setMapItem( False )
        return totalFeats

    def _rasterFlood(self, arrayFlood):
        args = self.canvasArray.getGeoreference()
        args['array'] = arrayFlood
        args['nodata'] = self.calcFlood.flood_out
        return datasetImageFromArray( **args )

    def _finishedFloodCanvas(self, dataResult ):
        layers = [ self.lyrSeed ]
        if 'rasterFlood' in dataResult :
            #  VSIMemory need in main thread
            rl = memoryRasterLayerFromDataset( dataResult['rasterFlood'], self.vsimemNameRasterFlood, self.styleRaster )
            dataResult['rasterFlood'] = None
            layers.append( rl )
        self.mapItem.updateCanvas( layers )
        self.taskCreateFlood = None

    def _createFlood(self, pointCanvas, threshFlood=None):
        args = {
            'arraySource': self.canvasArray.array,
            'seed': ( pointCanvas.x(), pointCanvas.y() ),
            'isCanceled': self.taskCreateFlood.isCanceled
        }
        if len( self.arrys_flood ):
            args['arrayFloodBack'] = self._reduceArrysFlood()
        if not threshFlood is None:
            args['threshould'] = threshFlood
        arryFlood = self.calcFlood.get( **args )
        totalPixels = 0 if arryFlood is None else ( arryFlood == self.calcFlood.flood_value_color ).sum().item()
        return arryFlood, totalPixels

    def _reduceArrysFlood(self):
        result = self.arrys_flood[0].copy()
        for arry in self.arrys_flood[ 1:]:
            bool_b = ( arry == self.calcFlood.flood_value_color )
            result[ bool_b ] = self.calcFlood.flood_value_color
        return result

    def _setMapItem(self, existsFlood=True):
        layers = []
        if existsFlood:
            ds = self._rasterFlood( self._reduceArrysFlood() )
            rl = memoryRasterLayerFromDataset( ds, self.vsimemNameRasterFlood, self.styleRaster )
            ds = None
            layers.append( rl)
        self.mapItem.updateCanvas( layers )

    @pyqtSlot(bool)
    def cancelCreateFlood(self, checked):
        if self.taskCreateFlood:
            self.taskCreateFlood.cancel()

    @pyqtSlot()
    def destinationCrsChanged(self):
        if self.mapItem.crs is None:
            return

        if not self.mapItem.changeExtentByCrs():
            msg = self.tr('CRS that was selected, {}, is not supported.')
            msg = msg.format( QgsProject.instance().crs().authid() )
            self.message.emit( msg, Qgis.Warning )
            self.mapItem.backCrs()


class PolygonClickMapTool(QgsMapTool):
    KEY_METADATA = 'PolygonClickMapTool_metadata'
    KEY_ADJUSTSBORDER = 'PolygonClickMapTool_adjusts_border'
    KEY_ADJACENTPIXELS = 'PolygonClickMapTool_adjacent_pixels'
    def __init__(self, iface, pluginName):
        self.mapCanvas = iface.mapCanvas()
        self.pluginName = pluginName
        super().__init__( self.mapCanvas )

        self.msgBar = iface.messageBar()
        self.statusBar = iface.mainWindow().statusBar()
        self.lblMessageFlood, self.spThreshFlood, self.btnCancel = None, None, None
        self.iconCancel = self.statusBar.style().standardIcon( QStyle.SP_DialogCancelButton )

        self.toolBack = None # self.setLayer
        self.toolCursor = QgsApplication.getThemeCursor( QgsApplication.CapturePoint )

        QgsProject.instance().layerWillBeRemoved.connect( self._layersWillBeRemoved )
        self.activated.connect( self._activatedTool )
        self.deactivated.connect( self._deactivatedTool )

        self.imageFlood = ImageFlood( self.mapCanvas )
        self.imageFlood.finishMovingFloodCanvas.connect( self._finishMovingFloodCanvas )
        self.imageFlood.finishAddedFloodCanvas.connect( self._finishAddedFloodCanvas )
        self.imageFlood.finishAddedMoveFloodCanvas.connect( self._finishAddedFloodCanvas )
        self.imageFlood.message.connect( lambda msg, level: self.msgBar.pushMessage( self.pluginName, msg, level ) )

        self.hasPressPoint = False
        self.startedMoveFlood = False
        self.dtMoveFloodIni = None
        self.msecondsMoveFlood = 1000

        self.pointCanvas = None
        self.layerFlood = None

    def __del__(self):
        del self.imageFlood

    def isPolygon(self, layer):
        return not layer is None and \
               layer.type() == QgsMapLayer.VectorLayer and \
               layer.geometryType() == QgsWkbTypes.PolygonGeometry

    def canvasPressEvent(self, e):
        if e.button() == Qt.RightButton:
            self.imageFlood.enabledFloodCanvas( False )
            return

        if self.imageFlood.existsProcessingFlood():
            return

        self.imageFlood.rastersCanvas = self.imageFlood.getRasterCanvas()
        if not len( self.imageFlood.rastersCanvas ):
            return
        
        self.hasPressPoint = True
        self.startedMoveFlood = False

        self.imageFlood.setLayerSeed( e.mapPoint() )
        self.pointCanvas = e.originalPixelPoint()

        self.imageFlood.setThreshold( self.spThreshFlood.value() )

        if self.imageFlood.changedCanvas():
            if self.imageFlood.totalFlood():
                self._savePolygon()
                self.hasPressPoint = False # Escape canvasMoveEvent
                return
            self.imageFlood.updateCanvasImage()

        self.dtMoveFloodIni = QDateTime.currentDateTime()

        hasAdjacentPixels = self.layerFlood.customProperty( self.KEY_ADJACENTPIXELS, False )
        self.imageFlood.setCoordinatesAdjacentFlood( hasAdjacentPixels ) # True 8 pixels

    def canvasMoveEvent(self, e):
        # Always e.button() = 0
        if not self.hasPressPoint or not len( self.imageFlood.rastersCanvas ) or self.imageFlood.existsProcessingFlood():
            return

        pointCanvas = e.originalPixelPoint()
        treshold = self.imageFlood.calculateThreshold( self.pointCanvas, pointCanvas )
        self._setValueTreshold( treshold )

        mseconds = self.dtMoveFloodIni.msecsTo( QDateTime.currentDateTime() )
        if mseconds < self.msecondsMoveFlood:
            return
        self.startedMoveFlood = True
        self.btnCancel.show()
        self.imageFlood.movingFloodCanvas( self.pointCanvas, treshold )

    def canvasReleaseEvent(self, e):
        if self.imageFlood.rastersCanvas is None:
            return

        if not len( self.imageFlood.rastersCanvas):
            msg = self.tr('Missing raster layer visible in Map')
            self.msgBar.pushWarning( self.pluginName, msg )
            return

        self.hasPressPoint = False
        if e.button() == Qt.RightButton:
            self.imageFlood.enabledFloodCanvas()
            return

        if self.imageFlood.existsProcessingFlood():
            return

        if not self.startedMoveFlood:
            self.btnCancel.show()
            self.imageFlood.addFloodCanvas( self.pointCanvas )
            return

        self.imageFlood.addFloodMoveCanvas()

    def keyReleaseEvent(self, e):
        key = e.key()
        if not key in( Qt.Key_D, Qt.Key_U, Qt.Key_H, Qt.Key_F, Qt.Key_P, Qt.Key_R ):
            return

        if e.key() == Qt.Key_H:
            self._help()
            return

        if e.key() == Qt.Key_D:
            if self.imageFlood.deleteFloodCanvas():
                self._setTextMessage(f"{self.imageFlood.totalFlood()} images")
            return

        if e.key() == Qt.Key_U:
            if self.imageFlood.undoFlood():
                self._setTextMessage(f"{self.imageFlood.totalFlood()} images")
            return

        if e.key() == Qt.Key_F:
            if self.imageFlood.fillHolesFlood():
                msg = self.tr('remove holes - {} images')
                msg = msg.format( self.imageFlood.totalFlood() )
                self._setTextMessage( msg )
            return

        if e.key() == Qt.Key_P:
            if self.layerFlood is None:
                msg = self.tr('Missing polygon layer to receive')
                self.msgBar.pushWarning( self.pluginName, msg )
                return
            if not self.layerFlood.isEditable():
                msg = f"Polygon layer \"{self.layerFlood.name()}\"need be Editable"
                self.msgBar.pushWarning( self.pluginName, msg )
                return

            hasAdjustsBorder = self.layerFlood.customProperty( self.KEY_ADJUSTSBORDER, False )
            totalFeats = self.imageFlood.polygonizeFlood( self.layerFlood, self._getMetadata(), hasAdjustsBorder )
            if not totalFeats:
                msg = self.tr('Polygonize - Missing features')
            else:
                 msg = self.tr('Polygonize - {} features added')
                 msg = msg.format( totalFeats )
            self._setTextMessage( msg )
            return

        if e.key() == Qt.Key_R:
            total = self.imageFlood.totalFlood() 
            if not total:
                return

            msg = self.tr('Remove all images ({})?')
            msg = msg.format( total )
            ret = QMessageBox.question(None, self.pluginName, msg, QMessageBox.Yes | QMessageBox.No, QMessageBox.No )
            if ret == QMessageBox.Yes:
                self.imageFlood.removeAllFloodCanvas()
                msg = 'Delete {} images'
                msg= msg.format( total )
                self._setTextMessage( msg )
            return

    def setLayerFlood(self, layer):
        msg = self.tr('Current layer is')
        msg = f"{msg} \"{layer.name()}\""
        self.msgBar.popWidget()
        self.msgBar.pushInfo( self.pluginName, msg )

        if not self.layerFlood is None:
            self.layerFlood.nameChanged.disconnect( self._nameChangedLayerFlood )
            self.layerFlood.editingStopped.connect( self._editingStoppedLayerFlood )

        # Signal
        layer.nameChanged.connect( self._nameChangedLayerFlood )
        layer.editingStopped.connect( self._editingStoppedLayerFlood )

        self.layerFlood = layer
        if self.lblMessageFlood:
            msg = self.tr('images')
            self._setTextMessage(f"{self.imageFlood.totalFlood()} {msg}")
        if not self == self.mapCanvas.mapTool():
            self.toolBack = self.mapCanvas.mapTool()

    def _getMetadata(self):
        field = self.layerFlood.customProperty( self.KEY_METADATA, None )
        if not field or not field in self.layerFlood.fields().names():
            return None
        
        metadata =  json.dumps( {
            'rasters': self.imageFlood.rasterCanvasNames(),
            'user': QgsApplication.userFullName(),
            'datetime': QDateTime.currentDateTime().toString( Qt.ISODate ),
            'scale': int( self.mapCanvas.scale() )
        } )
        return { 'field': field, 'value': metadata }

    def _savePolygon(self):
        totalImages = self.imageFlood.totalFlood()
        msg = self.tr('Add features from images to')
        msg = f"{msg} \"{self.layerFlood.name()}\""
        ret = QMessageBox.question( None, self.pluginName, msg, QMessageBox.Yes | QMessageBox.No )
        if ret == QMessageBox.Yes:
            hasAdjustsBorder = self.layerFlood.customProperty( self.KEY_ADJUSTSBORDER, False )
            totalFeats = self.imageFlood.polygonizeFlood( self.layerFlood, self._getMetadata(), hasAdjustsBorder )
            if not totalFeats:
                msg = self.tr('Polygonize - Missing features')
            else:
                msg = self.tr('Polygonize - {} features added')
                msg = msg.format( totalFeats )
            self._setTextMessage( msg )
            return

        self.imageFlood.removeAllFloodCanvas()
        msg = self.tr('Delete {} images')
        msg = msg.format( totalImages )
        self._setTextMessage( msg )

    def _setTextMessage(self, message):
        self.lblMessageFlood.setText(f"{self.pluginName}({self.layerFlood.name()}): {message}")

    def _setValueTreshold(self, treshold):
        self.spThreshFlood.setValue( treshold )

    def _help(self):
        title = self.tr('{} - Help')
        title = title.format( self.pluginName )
        args = {
            'title': title,
            'prefixHtml': 'help',
            'dirHtml': os.path.join( os.path.dirname(__file__), 'resources' )
        }
        messageOutputHtml( **args )

    @pyqtSlot()
    def _nameChangedLayerFlood(self):
        msg = self.tr('{} images')
        msg = msg.format( self.imageFlood.totalFlood() )
        self._setTextMessage( msg )
    
    @pyqtSlot()
    def _editingStoppedLayerFlood(self):
        if self.imageFlood.totalFlood():
            self.layerFlood.startEditing()
            self._savePolygon()
            self.layerFlood.commitChanges()
        self.mapCanvas.setMapTool( self.toolBack )
        self.action().setEnabled( False )
        self.layerFlood = None

    @pyqtSlot(str)
    def _layersWillBeRemoved(self, layerIds):
        if not self.isActive():
            return

        if self.layerFlood and self.layerFlood.id() in layerIds:
            self.imageFlood.removeAllFloodCanvas()
            self.layerFlood = None

    @pyqtSlot()
    def _activatedTool(self):
        def createLabel():
            w = QLabel()
            w.setFrameStyle( QFrame.StyledPanel )
            w.setMinimumWidth( 100 )
            self.statusBar.addPermanentWidget( w, 0 )
            return w

        def createSpin(min, max, step, prefix, suffix):
            w = QSpinBox()
            w.setRange( min, max )
            w.setSingleStep( step )
            w.setPrefix( prefix )
            w.setSuffix( suffix )
            self.statusBar.addPermanentWidget( w, 0 )
            return w

        self.lblMessageFlood = createLabel()
        msg = self.tr('{} images')
        msg = msg.format( self.imageFlood.totalFlood() )
        self._setTextMessage( msg )
        min, max = self.imageFlood.thresholdMinMax()
        msgTreshold = self.tr('Treshold')
        msgTreshold = f"{msgTreshold}:  "
        msgRGB = self.tr('(pixel RGB)')
        msgRGB = f" {msgRGB}"
        self.spThreshFlood = createSpin( min, max, 1, msgTreshold, msgRGB )
        self._setValueTreshold( self.imageFlood.threshold() )
        self.btnCancel = QPushButton( self.iconCancel, '' )
        self.statusBar.addPermanentWidget( self.btnCancel, 0 )
        self.btnCancel.hide()
        self.btnCancel.clicked.connect( self.imageFlood.cancelCreateFlood )
        self.setCursor( self.toolCursor )

    @pyqtSlot()
    def _deactivatedTool(self):
        self.statusBar.removeWidget( self.lblMessageFlood )
        self.statusBar.removeWidget( self.spThreshFlood )
        self.statusBar.removeWidget( self.btnCancel )

    @pyqtSlot(bool)
    def _finishMovingFloodCanvas(self, isOk):
        if not self.hasPressPoint: # canvasReleaseEvent before
            self.imageFlood.addFloodMoveCanvas() # Can be None floodMove
        self.btnCancel.hide()
        self.dtMoveFloodIni = QDateTime.currentDateTime()
        if not isOk:
            msg = self.tr('Canceled by user')
            self.msgBar.pushCritical( self.pluginName, msg )

    @pyqtSlot(bool, int)
    def _finishAddedFloodCanvas(self, isOk, totalPixels):
        msg1 = self.tr('images')
        msg1 = f"{self.imageFlood.totalFlood()} {msg1}"
        if totalPixels:
            msg = self.tr('{} - Last image added {} pixels')
            msg = msg.format( msg1, totalPixels )
        else:
            msg = self.tr('{} - Not added images( no pixels found)')
            msg = msg.format( msg1 )
        self._setTextMessage( msg )
        self.btnCancel.hide()
        if not isOk:
            msg = self.tr('Canceled by user')
            self.msgBar.pushCritical( self.pluginName, msg )
