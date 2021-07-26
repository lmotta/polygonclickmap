
from qgis.PyQt.QtCore import Qt, QVariant
from qgis.PyQt.QtWidgets import QLabel, QFrame, QMessageBox

from qgis.core import (
    QgsProject,
    QgsMapLayer, QgsVectorLayer, QgsRasterLayer,
    QgsGeometry, QgsFeature, QgsWkbTypes,
    QgsCoordinateReferenceSystem, QgsCoordinateTransform
)
from qgis.gui import QgsMapTool

from osgeo import gdal, ogr

from scipy import ndimage

import os

from .utils import MapItemFlood, CanvasImage, CalculateArrayFlood, createDatasetMem

class ImageFlood():
    def __init__(self, mapCanvas):
        self.canvasImage = CanvasImage( mapCanvas )
        self.mapItem = MapItemFlood( mapCanvas )
        self.calcFlood = CalculateArrayFlood()

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

    def __del_(self):
        self.canvasImage.dataset = None

    def setLayerSeed(self, pointMap):
        self.lyrSeed = self._createQgsSeedVector( pointMap )

    def setRastersCanvas(self):
        self.rastersCanvas = self.canvasImage.rasterLayers()

    def existsRasterLayer(self):
        return len( self.rastersCanvas ) > 0

    def changedCanvas(self):
        return self.canvasImage.changedCanvas()

    def needSavePolygon(self):
        return self.canvasImage.changedCanvas() and len( self.arrys_flood )

    def updateCanvasImage(self):
        self.arrys_flood *= 0
        self.arrys_flood_delete *= 0
        self.canvasImage.process( self.rastersCanvas )
        if not self.canvasImage.dataset:
            raise TypeError("Error created image from canvas. Check exists raster layer visible")
        if not self.calcFlood.setFloodValue( self.canvasImage.dataset ):
            raise TypeError("Impossible define value of seed")

    def calculateThreshold(self, point1, point2):
        return self.calcFlood.getThresholdFlood( point1, point2 )

    def getCurrentThreshold(self):
        return self.calcFlood.threshFlood

    def totalFlood(self):
        return len( self.arrys_flood )
 
    def enabledFloodCanvas(self, enabled=True):
        # if enabled:
        #     layers = [ self.lyrSeed ]
        #     if len( self.arrys_flood ):
        #         layers.append( self._rasterFlood( self.arrys_flood[-1] ) )
        #     self.mapItem.setLayers( layers )
        self.mapItem.enabled = enabled
        self.mapItem.updateCanvas()

    def clearFloodCanvas(self):
        self.arrys_flood *= 0
        self.arrys_flood_delete *= 0
        self._setMapItem( False )
        return True

    def showFloodMovingCanvas(self, pointCanvas, threshFlood):
        self.arryFloodMove = None
        layers = [ self.lyrSeed ]
        arryFlood, totalPixels = self._createFlood( pointCanvas, threshFlood )
        if totalPixels:
            layers.append( self._rasterFlood( arryFlood )  )
            self.arryFloodMove = arryFlood
        self.mapItem.setLayers( layers )
        self.mapItem.updateCanvas()
        return totalPixels

    def addFloodCanvas(self, pointCanvas):
        if self.canvasImage.changedCanvas():
            self.updateCanvasImage()
        arryFlood, totalPixels = self._createFlood( pointCanvas )
        if totalPixels:
            self._updateArraysShowAll( arryFlood, self.lyrSeed )
            return totalPixels

        if len( self.arrys_flood ):
            self.mapItem.setLayers( [ self.lyrSeed,  self._rasterFlood( self._reduceArrysFlood() ) ] )
        else:
            self.mapItem.setLayers( [ self.lyrSeed ] )
        self.mapItem.updateCanvas()
        return 0

    def addFloodMoveCanvas(self, threshFloodMove):
        self._updateArraysShowAll( self.arryFloodMove, self.lyrSeed )
        totalPixels = ( self.arryFloodMove == self.calcFlood.flood_value_color ).sum().item()
        self.calcFlood.threshFlood = threshFloodMove  # Update treshold
        return totalPixels

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

    def holeFlood(self):
        if not len( self.arrys_flood ):
            return False
        arry = self.arrys_flood.pop()
        binary_holes = ndimage.binary_fill_holes( arry )
        arry[ binary_holes ] = self.calcFlood.flood_value_color
        self.arrys_flood.append( arry )
        self._setMapItem()
        return True

    def polygonizeFlood(self, layerFlood, fieldNameRaster=None):
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

        layer, ds = polygonizeFlood( self._reduceArrysFlood() )
        totalFeats = layer.GetFeatureCount()
        if not totalFeats:
            return 0

        if fieldNameRaster:
            names = [ l.name() for l in self.rastersCanvas ]
            names = ','.join( names )

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
            f.setGeometry( g )
            if fieldNameRaster:
                f[ fieldNameRaster ] = names
                # f.setAttribute( fieldNameRaster, names )
            layerFlood.addFeature( f )
        ds = None
        layerFlood.updateExtents()
        layerFlood.triggerRepaint()

        self.arrys_flood *= 0
        self.arrys_flood_delete *= 0

        self._setMapItem( False )
        return totalFeats

    def _createQgsSeedVector(self, pointMap):
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
        args = { 'arraySource': arry, 'seed': seed }
        if threshFlood:
            args['threshFlood'] = threshFlood
        arryFlood = self.calcFlood.get( **args ) 
        totalPixels = ( arryFlood == self.calcFlood.flood_value_color ).sum().item()
        return arryFlood, totalPixels

    def _reduceArrysFlood(self):
        result = self.arrys_flood[0].copy()
        for arry in self.arrys_flood[ 1:]:
            bool_b = ( arry == self.calcFlood.flood_value_color )
            result[ bool_b ] = self.calcFlood.flood_value_color
        return result

    def _updateArraysShowAll(self, arryFlood, lyrSeed ):
        self.arrys_flood.append( arryFlood )
        self.mapItem.setLayers( [ lyrSeed,  self._rasterFlood( self._reduceArrysFlood() ) ] )
        self.mapItem.updateCanvas()
    
    def _setMapItem(self, existsFlood=True):
        layers = [] if not existsFlood else [ self._rasterFlood( self._reduceArrysFlood() ) ]
        self.mapItem.setLayers( layers )
        self.mapItem.updateCanvas()


class ImageFloodTool(QgsMapTool):
    PLUGINNAME = 'Image flood tool'
    FIELDNAMEFLOOD = 'raster'
    def __init__(self, iface):
        self.mapCanvas = iface.mapCanvas()
        super().__init__( self.mapCanvas )

        self.msgBar = iface.messageBar()
        self.statusBar = iface.mainWindow().statusBar()
        self.lblThreshFlood, self.lblMessageFlood = None, None
        self.toolBack = None # self.setLayer

        self.activated.connect( self._activatedTool )
        self.deactivated.connect( self._deactivatedTool )
        iface.layerTreeView().currentLayerChanged.connect( self._currentLayerChanged )
        self.iface = iface

        self.imageFlood = ImageFlood( self.mapCanvas )
        self.hasPressPoint = False
        self.threshFloodMove = None

        self.pointCanvas = None
        
        self.stylePoylgon = os.path.join( os.path.dirname(__file__), 'polygonflood.qml' )
        self.layerFlood = None
        self.existsFieldNameFlood = False

    def __del__(self):
        del self.imageFlood
        self.activated.connect( self._activated )
        self.deactivated.connect( self._deactivatedTool )
        self.iface.layerTreeView().currentLayerChanged.disconnect( self._currentLayerChanged )

    def isEditabledPolygon(self, layer):
        return not layer is None and \
               layer.type() == QgsMapLayer.VectorLayer and \
               layer.geometryType() == QgsWkbTypes.PolygonGeometry and \
               layer.isEditable()

    def canvasPressEvent(self, e):
        def savePolygon():
            if self.layerFlood is None or not self.imageFlood.needSavePolygon():
                return False
            return self._savePolygon()

        if e.button() == Qt.RightButton:
            self.imageFlood.enabledFloodCanvas( False )
            return

        self.imageFlood.setRastersCanvas()
        if not self.imageFlood.existsRasterLayer():
            return

        self.hasPressPoint = True
        
        self.threshFloodMove = None
        self.arryFloodMove = None

        self.imageFlood.setLayerSeed( e.mapPoint() )
        self.pointCanvas = e.originalPixelPoint()

        if savePolygon():
            self.hasPressPoint = False # Escape canvasMoveEvent

    def canvasMoveEvent(self, e):
        # Always e.button() = 0

        if not self.hasPressPoint or not self.imageFlood.existsRasterLayer():
            return

        if self.imageFlood.changedCanvas():
            self.imageFlood.updateCanvasImage()

        pointCanvas = e.originalPixelPoint()
        self.threshFloodMove = self.imageFlood.calculateThreshold( self.pointCanvas, pointCanvas )
        self._setTextTreshold( self.threshFloodMove )
        totalPixels = self.imageFlood.showFloodMovingCanvas( self.pointCanvas, self.threshFloodMove )
        if not totalPixels:
            self.threshFloodMove = None

    def canvasReleaseEvent(self, e):
        if not self.imageFlood.existsRasterLayer():
            msg = 'Missing raster layer visible in Map'
            self.msgBar.pushWarning( self.PLUGINNAME, msg )
            return

        self.hasPressPoint = False
        if e.button() == Qt.RightButton:
            self.imageFlood.enabledFloodCanvas()
            return

        if self.threshFloodMove is None:
            self._setTextTreshold( self.imageFlood.getCurrentThreshold() )
            totalPixels = self.imageFlood.addFloodCanvas( self.pointCanvas )
            msg = f"{self.imageFlood.totalFlood()} images"
            msg = f"{msg} - Last image added {totalPixels} pixels" if totalPixels \
                else f"{msg} - Not added images( no pixels found)"
            self._setTextMessage( msg )
            return
        
        totalPixels = self.imageFlood.addFloodMoveCanvas( self.threshFloodMove )
        msg = f"{self.imageFlood.totalFlood()} images - Last image added {totalPixels} pixels"
        self._setTextMessage( msg )

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
            if self.imageFlood.holeFlood():
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

            args = [ self.layerFlood ]
            if self.existsFieldNameFlood:
                args.append( self.FIELDNAMEFLOOD )
            totalFeats = self.imageFlood.polygonizeFlood( *args )
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
        def existsFieldNameFlood(layer):
            for field in layer.fields():
                if field.type() == QVariant.String and field.name() == self.FIELDNAMEFLOOD:
                    self.existsFieldNameFlood = True
                    return
            self.existsFieldNameFlood = False

        existsFieldNameFlood( layer )
        if self.layerFlood == layer:
            return

        if self.imageFlood.totalFlood():
            self._savePolygon()

        msg = f"Current Flood layer is \"{layer.name()}\""
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
        msg = f"Add features from images to \"{self.layerFlood.name()}\" ?"
        ret = QMessageBox.question(None, self.PLUGINNAME, msg, QMessageBox.Yes | QMessageBox.No )
        if ret == QMessageBox.Yes:
            args = [ self.layerFlood ]
            if self.existsFieldNameFlood:
                args.append( self.FIELDNAMEFLOOD )
            totalFeats = self.imageFlood.polygonizeFlood( *args )
            msg = 'Flood: Polygonize - Missing features' if not totalFeats \
                else f"Flood: Polygonize - {totalFeats} features added"
            self.lblMessageFlood.setText( msg )
            return True
        return False

    def _setTextMessage(self, message):
        self.lblMessageFlood.setText(f"Flood({self.layerFlood.name()}): {message}")

    def _setTextTreshold(self, treshold):
        self.lblThreshFlood.setText(f"Treshold: {treshold} (pixel RGB)")

    # Slots
    def _nameChangedLayerFlood(self):
        self.lblMessageFlood.setText(f"Flood({self.layerFlood.name()}): {self.imageFlood.totalFlood()} images")
    
    def _editingStoppedLayerFlood(self):
        if self.imageFlood.totalFlood():
            self.layerFlood.startEditing()
            self._savePolygon()
            self.layerFlood.commitChanges()
        self.mapCanvas.setMapTool( self.toolBack )
        self.action().setEnabled( False )
        self.layerFlood = None

    def _currentLayerChanged(self, layer):
        if self.isActive() and self.isEditabledPolygon( layer ):
            self.setLayerFlood( layer )

    def _activatedTool(self):
        def createLabelFlood():
            lbl = QLabel()
            lbl.setFrameStyle( QFrame.StyledPanel )
            lbl.setMinimumWidth( 100 )
            return lbl

        self.lblThreshFlood = createLabelFlood()
        self.lblMessageFlood = createLabelFlood()
        self.statusBar.addPermanentWidget( self.lblMessageFlood, 0)
        self._setTextMessage(f"{self.imageFlood.totalFlood()} images")
        self.statusBar.addPermanentWidget( self.lblThreshFlood, 0)
        self._setTextTreshold( self.imageFlood.getCurrentThreshold() )

    def _deactivatedTool(self):
        self.statusBar.removeWidget( self.lblMessageFlood )
        self.statusBar.removeWidget( self.lblThreshFlood )



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
