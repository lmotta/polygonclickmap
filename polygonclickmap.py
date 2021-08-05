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
    Qt, QVariant, QDateTime,
    QObject, pyqtSlot, pyqtSignal
)
from qgis.PyQt.QtWidgets import (
    QLabel, QSpinBox, QPushButton,
    QFrame,
    QMessageBox,
    QStyle
)

from qgis.core import (
    QgsProject, QgsApplication,
    QgsMapLayer, QgsVectorLayer, QgsRasterLayer,
    QgsGeometry, QgsFeature, QgsWkbTypes,
    QgsCoordinateReferenceSystem, QgsCoordinateTransform,
    QgsTask
)
from qgis.gui import QgsMapTool

from osgeo import gdal, ogr
from scipy import ndimage

import os

from .utils import MapItemFlood, CanvasImage, CalculateArrayFlood, createDatasetMem


class ImageFlood(QObject):
    finishMovingFloodCanvas = pyqtSignal()
    finishAddedFloodCanvas = pyqtSignal(int)
    finishAddedMoveFloodCanvas = pyqtSignal(int)
    def __init__(self, mapCanvas):
        super().__init__()
        self.canvasImage = CanvasImage( mapCanvas )
        self.mapItem = MapItemFlood( mapCanvas )
        self.calcFlood = CalculateArrayFlood()

        self.mapCanvas = mapCanvas

        self.taskManager = QgsApplication.taskManager()
        self.taskCreateFlood = None

        self.arrys_flood = []
        self.arrys_flood_delete = []
        self.arryFloodMove = None

        self.lyrSeed = None

        self.rastersCanvas = None # [ RasterLayer inside Canvas]

        self.stylePoint = os.path.join( os.path.dirname(__file__), 'pointflood.qml' )
        self.styleRaster = os.path.join( os.path.dirname(__file__), 'rasterflood.qml' )

        self.filenameRasterFlood = '/vsimem/raster_flood.tif'
        self.existsLinkRasterFlood = False

        self.smooth_iter = 1
        self.smooth_offset  = 0.25

        self.fieldsName = {
            'rasters': 'Visibles rasters in map',
            'user': 'User of QGIS',
            'datetime': 'Date time when features will be add',
            'scale': 'Scale of map'
        }

    def __del__(self):
        self.canvasImage.dataset = None

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
            l.loadNamedStyle( self.stylePoint )
            return l

        self.lyrSeed = createQgsSeedVector()

    def updateCanvasImage(self):
        self.arrys_flood *= 0
        self.arrys_flood_delete *= 0
        self.canvasImage.process( self.rastersCanvas )
        if not self.canvasImage.dataset:
            raise TypeError("Error created image from canvas. Check exists raster layer visible")
        if not self.calcFlood.setFloodValue( self.canvasImage.dataset ):
            raise TypeError("Impossible define value of seed")

    def getRasterCanvas(self):
        return self.canvasImage.rasterLayers()

    def changedCanvas(self):
        return self.canvasImage.changedCanvas()

    def calculateThreshold(self, point1, point2):
        return self.calcFlood.getThresholdFlood( point1, point2 )

    def threshold(self):
        return self.calcFlood.threshFlood

    def setThreshold(self, threshold):
        self.calcFlood.threshFlood = threshold

    def thresholdMinMax(self):
        return self.calcFlood.minValue, self.calcFlood.maxValue

    def totalFlood(self):
        return len( self.arrys_flood )
 
    def existsProcessingFlood(self):
        return not self.taskCreateFlood is None

    def enabledFloodCanvas(self, enabled=True):
        self.mapItem.enabled = enabled
        self.mapItem.updateCanvas()

    def clearFloodCanvas(self):
        self.arrys_flood *= 0
        self.arrys_flood_delete *= 0
        self._setMapItem( False )

    def movingFloodCanvas(self, pointCanvas, threshFlood):
        def finished(exception, dataResult):
            layers = [ self.lyrSeed ]
            if dataResult['totalPixels']:
                layers.append( dataResult['rasterFlood'] )
            self.mapItem.setLayers( layers )
            self.mapItem.updateCanvas()
            self.taskCreateFlood = None
            self.finishMovingFloodCanvas.emit()

        def run(task):
            self.taskCreateFlood = task
            arryFlood, totalPixels = self._createFlood( pointCanvas, threshFlood )
            dataResult = { 'totalPixels': totalPixels }
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
            layers = [ self.lyrSeed ]
            if 'rasterFlood' in dataResult:
                layers.append( dataResult['rasterFlood'] )
            self.mapItem.setLayers( layers )
            self.mapItem.updateCanvas()
            self.taskCreateFlood = None
            self.finishAddedFloodCanvas.emit( dataResult['totalPixels'] )

        def run(task):
            self.taskCreateFlood = task
            arryFlood, totalPixels = self._createFlood( pointCanvas)
            if totalPixels:
                self.arrys_flood.append( arryFlood )
                return {
                    'totalPixels': totalPixels,
                    'rasterFlood': self._rasterFlood( self._reduceArrysFlood() )
                }
            if len( self.arrys_flood ):
                return {
                    'totalPixels': 0,
                    'rasterFlood': self._rasterFlood( self._reduceArrysFlood() )
                }
            return { 'totalPixels': 0 }

        task = QgsTask.fromFunction('PolygonClickImage add flood', run, on_finished=finished )
        self.taskManager.addTask( task )
        # Debug
        # r = run( task )
        # finished( None, r )

    def addFloodMoveCanvas(self):
        def finished(exception, dataResult):
            layers = [ self.lyrSeed, dataResult['rasterFlood'] ]
            self.mapItem.setLayers( layers )
            self.mapItem.updateCanvas()
            self.taskCreateFlood = None
            self.finishAddedMoveFloodCanvas.emit( dataResult['totalPixels'] )

        def run(task):
            self.taskCreateFlood = task
            self.arrys_flood.append( self.arryFloodMove )
            return {
                'totalPixels': ( self.arryFloodMove == self.calcFlood.flood_value_color ).sum().item(),
                'rasterFlood': self._rasterFlood( self._reduceArrysFlood() )
            }

        task = QgsTask.fromFunction('PolygonClickImage add move flood', run, on_finished=finished )
        self.taskManager.addTask( task )
        # Debug
        # r = run( task )
        # finished( None, r )

    def deleteFlood(self):
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
        binary_holes = ndimage.binary_fill_holes( arry )
        arry[ binary_holes ] = self.calcFlood.flood_value_color
        self.arrys_flood.append( arry )
        self._setMapItem()
        return True

    def polygonizeFlood(self, layerFlood, fieldsName):
        def polygonizeFlood(arrayFlood):
            tran = self.canvasImage.dataset.GetGeoTransform()
            srs = self.canvasImage.dataset.GetSpatialRef()
            # Raster
            dsRaster = createDatasetMem( arrayFlood, tran, srs )
            band = dsRaster.GetRasterBand(1)
            # Vector
            ds = ogr.GetDriverByName('MEMORY').CreateDataSource('memData')
            layer = ds.CreateLayer( name='memLayer', srs=srs, geom_type=ogr.wkbPolygon )
            gdal.Polygonize( srcBand=band, maskBand=band, outLayer=layer, iPixValField=-1)
            dsRaster = None
            #
            return layer, ds

        def populateFieldsValues():
            fieldsValues = {}
            key = 'rasters'
            if key in fieldsName:
                value = [ l.name() for l in self.rastersCanvas ]
                value = ','.join( value )
                key_value = fieldsName[ key ]
                fieldsValues[ key_value ] = value
            key = 'user'
            if  key in fieldsName:
                value = QgsApplication.userFullName()
                key_value = fieldsName[ key ]
                fieldsValues[ key_value ] = value
            key = 'datetime'
            if  key in fieldsName:
                value = QDateTime.currentDateTime().toString( Qt.ISODate )
                key_value = fieldsName[ key ]
                fieldsValues[ key_value ] = value
            key = 'scale'
            if  key in fieldsName:
                value = self.mapCanvas.scale()
                key_value = fieldsName[ key ]
                fieldsValues[ key_value ] = value
            return fieldsValues

        layer, ds = polygonizeFlood( self._reduceArrysFlood() )
        totalFeats = layer.GetFeatureCount()
        if not totalFeats:
            return 0

        crsLayer = layerFlood.crs()
        crsDS = QgsCoordinateReferenceSystem()
        crsDS.createFromString( layer.GetSpatialRef().ExportToWkt() )
        ct = QgsCoordinateTransform( crsDS, crsLayer, QgsProject.instance() )
        fields = layerFlood.fields()
        fieldsValues = populateFieldsValues()
        for feat in layer:
            g = QgsGeometry()
            g.fromWkb( feat.GetGeometryRef().ExportToIsoWkb() )
            g = g.smooth( self.smooth_iter, self.smooth_offset )
            g.transform( ct )
            f = QgsFeature( fields )
            f.setGeometry( g )
            for k in fieldsValues:
                f[ k ] = fieldsValues[ k ]
            layerFlood.addFeature( f )
        ds = None
        layerFlood.updateExtents()
        layerFlood.triggerRepaint()

        self.arrys_flood *= 0
        self.arrys_flood_delete *= 0

        self._setMapItem( False )
        return totalFeats

    @pyqtSlot(bool)
    def cancelCreateFlood(self, checked):
        if self.taskCreateFlood:
            self.taskCreateFlood.cancel()

    def _rasterFlood(self, arrayFlood):
        if self.existsLinkRasterFlood:
            gdal.Unlink( self.filenameRasterFlood )
        tran = self.canvasImage.dataset.GetGeoTransform()
        sr = self.canvasImage.dataset.GetSpatialRef()
        ds1 = createDatasetMem( arrayFlood, tran, sr, self.calcFlood.flood_out )
        if DEBUG:
            ds_ = gdal.GetDriverByName('GTiff').CreateCopy( FILENAME_FLOOD, ds1 )
            ds_ = None
        ds2 = gdal.GetDriverByName('GTiff').CreateCopy( self.filenameRasterFlood, ds1 )
        ds1, ds2 = None, None
        rl = QgsRasterLayer( self.filenameRasterFlood, 'raster', 'gdal')
        rl.loadNamedStyle( self.styleRaster )
        self.existsLinkRasterFlood = True
        return rl

    def _createFlood(self, pointCanvas, threshFlood=None):
        # Populate Arrays flood
        arry = self.canvasImage.dataset.ReadAsArray()[:3] # RGBA: NEED Remove Alpha band(255 for all image)
        seed = ( pointCanvas.x(), pointCanvas.y() )
        args = {
            'arraySource': arry,
            'seed': seed,
            'isCanceled': self.taskCreateFlood.isCanceled
        }
        if not threshFlood is None:
            args['threshould'] = threshFlood
        arryFlood = self.calcFlood.get( **args )
        totalPixels = ( arryFlood == self.calcFlood.flood_value_color ).sum().item()
        return arryFlood, totalPixels

    def _reduceArrysFlood(self):
        result = self.arrys_flood[0].copy()
        for arry in self.arrys_flood[ 1:]:
            bool_b = ( arry == self.calcFlood.flood_value_color )
            result[ bool_b ] = self.calcFlood.flood_value_color
        return result

    def _setMapItem(self, existsFlood=True):
        layers = [] if not existsFlood else [ self._rasterFlood( self._reduceArrysFlood() ) ]
        self.mapItem.setLayers( layers )
        self.mapItem.updateCanvas()


class PolygonClickMapTool(QgsMapTool):
    PLUGINNAME = 'Image flood tool'
    def __init__(self, iface):
        self.mapCanvas = iface.mapCanvas()
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

        self.hasPressPoint = False
        self.startedMoveFlood = False
        self.dtMoveFloodIni = None
        self.msecondsMoveFlood = 1000

        self.pointCanvas = None
        
        self.stylePoylgon = os.path.join( os.path.dirname(__file__), 'polygonflood.qml' )
        self.layerFlood = None
        self.fieldsName = None # keys = self.imageFlood.fieldsName

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

    def canvasMoveEvent(self, e):
        # Always e.button() = 0
        if not self.hasPressPoint or not len( self.imageFlood.rastersCanvas ):
            return

        if self.imageFlood.existsProcessingFlood():
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
        if not len( self.imageFlood.rastersCanvas):
            msg = 'Missing raster layer visible in Map'
            self.msgBar.pushWarning( self.PLUGINNAME, msg )
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
        if not key in( Qt.Key_D, Qt.Key_U, Qt.Key_H, Qt.Key_P, Qt.Key_C ): # Delete, Undo, Hole, Polygonize, Clear
            return

        if e.key() == Qt.Key_D:
            if self.imageFlood.deleteFlood():
                self._setTextMessage(f"{self.imageFlood.totalFlood()} images")
            return

        if e.key() == Qt.Key_U:
            if self.imageFlood.undoFlood():
                self._setTextMessage(f"{self.imageFlood.totalFlood()} images")
            return

        if e.key() == Qt.Key_H:
            if self.imageFlood.fillHolesFlood():
                self._setTextMessage(f"remove holes - {self.imageFlood.totalFlood()} images")
            return

        if e.key() == Qt.Key_P:
            if self.layerFlood is None:
                msg = 'Missing polygon layer to receive'
                self.msgBar.pushWarning( self.PLUGINNAME, msg )
                return
            if not self.layerFlood.isEditable():
                msg = f"Polygon layer \"{self.layerFlood.name()}\"need be Editable"
                self.msgBar.pushWarning( self.PLUGINNAME, msg )
                return

            totalFeats = self.imageFlood.polygonizeFlood( self.layerFlood, self.fieldsName )
            msg = 'Polygonize - Missing features' if not totalFeats \
                else f"Polygonize - {totalFeats} features added"
            self._setTextMessage( msg )
            return

        if e.key() == Qt.Key_C:
            total = self.imageFlood.totalFlood() 
            if not total:
                return

            msg = f"Clear {total} images?"
            ret = QMessageBox.question(None, self.PLUGINNAME, msg, QMessageBox.Yes | QMessageBox.No, QMessageBox.No )
            if ret == QMessageBox.Yes:
                self.imageFlood.clearFloodCanvas()
                self._setTextMessage(f"Delete {total} images")
            return

    def setLayerFlood(self, layer):
        def existsFieldName(layer, name, type=QVariant.String):
            for field in layer.fields():
                if field.type() == type and field.name() == name:
                    return True
            return False

        if not self.layerFlood == layer and self.imageFlood.totalFlood():
            self._savePolygon()

        self.fieldsName = {}
        name = 'imagens'
        if existsFieldName( layer, name ):
            self.fieldsName['rasters'] = name
        name = 'datahora'
        if existsFieldName( layer, name ):
            self.fieldsName['datetime'] = name
        name = 'usuario'
        if existsFieldName( layer, name ):
            self.fieldsName['user'] = name
        name = 'escala'
        if existsFieldName( layer, name, QVariant.Double ):
            self.fieldsName['scale'] = name

        msg = f"Current Flood layer is \"{layer.name()}\""
        self.msgBar.popWidget()
        self.msgBar.pushInfo( self.PLUGINNAME, msg )

        if not self.layerFlood is None:
            self.layerFlood.nameChanged.disconnect( self._nameChangedLayerFlood )
            self.layerFlood.editingStopped.connect( self._editingStoppedLayerFlood )

        # Signal
        layer.nameChanged.connect( self._nameChangedLayerFlood )
        layer.editingStopped.connect( self._editingStoppedLayerFlood )

        self.layerFlood = layer
        if self.lblMessageFlood:
            self._setTextMessage(f"{self.imageFlood.totalFlood()} images")
        if not self == self.mapCanvas.mapTool():
            self.toolBack = self.mapCanvas.mapTool()

    def _savePolygon(self):
        totalImages = self.imageFlood.totalFlood()
        msg = f"Add features from images to \"{self.layerFlood.name()}\" ?"
        ret = QMessageBox.question( None, self.PLUGINNAME, msg, QMessageBox.Yes | QMessageBox.No )
        if ret == QMessageBox.Yes:
            totalFeats = self.imageFlood.polygonizeFlood( self.layerFlood, self.fieldsName )
            msg = 'Polygonize - Missing features' if not totalFeats \
                else f"Polygonize - {totalFeats} features added"
            self._setTextMessage( msg )
            return

        self.imageFlood.clearFloodCanvas()
        self._setTextMessage(f"Delete {totalImages} images")

    def _setTextMessage(self, message):
        self.lblMessageFlood.setText(f"Flood({self.layerFlood.name()}): {message}")

    def _setValueTreshold(self, treshold):
        self.spThreshFlood.setValue( treshold )

    @pyqtSlot()
    def _nameChangedLayerFlood(self):
        msg = f"{self.imageFlood.totalFlood()} images"
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
            self.imageFlood.clearFloodCanvas()
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
        self._setTextMessage(f"{self.imageFlood.totalFlood()} images")
        min, max = self.imageFlood.thresholdMinMax()
        self.spThreshFlood = createSpin( min, max, 1, 'Treshold:  ', ' (pixel RGB)')
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

    @pyqtSlot()
    def _finishMovingFloodCanvas(self):
        if not self.hasPressPoint: # canvasReleaseEvent before
            self.imageFlood.addFloodMoveCanvas()
        self.btnCancel.hide()
        self.dtMoveFloodIni = QDateTime.currentDateTime()

    @pyqtSlot(int)
    def _finishAddedFloodCanvas(self, totalPixels):
        msg = f"{self.imageFlood.totalFlood()} images"
        msg = f"{msg} - Last image added {totalPixels} pixels" if totalPixels \
            else f"{msg} - Not added images( no pixels found)"
        self._setTextMessage( msg )
        self.btnCancel.hide()


def saveShp(geoms, srs):
    driver = ogr.GetDriverByName('ESRI Shapefile')
    name = 'flood'
    filename = f"/home/lmotta/data/work/{name}.shp"
    if os.path.exists( filename ):
        driver.DeleteDataSource( filename )

    ds_out = driver.CreateDataSource( filename )
    layer_out = ds_out.CreateLayer( name, srs=srs, geom_type=ogr.wkbPolygon )
    field_defn = ogr.FieldDefn('id', ogr.OFTInteger)
    layer_out.CreateField( field_defn )
    feat_defn = layer_out.GetLayerDefn()
    id = 1
    for geom in geoms:
        feat_out = ogr.Feature( feat_defn )
        wkb = geom.asWkb()
        feat_out.SetGeometry( ogr.CreateGeometryFromWkb( wkb ) )
        wkb = None
        feat_out.SetField('id', id)
        id += 1
        layer_out.CreateFeature( feat_out )
        feat_out = None
    ds_out = None

FILENAME_IMAGE = '/home/lmotta/data/work/AAA_IMAGE.tif'
FILENAME_ARRAY = '/home/lmotta/data/work/AAA_ARRAY.tif'
FILENAME_FLOOD = '/home/lmotta/data/work/AAA_FLOOD.tif'
DEBUG = False
