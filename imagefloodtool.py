
from plugin.geometry import Polygon
from qgis.PyQt.QtCore import Qt, QByteArray, QBuffer, QIODevice
from qgis.PyQt.QtGui import QImage, QColor
from qgis.PyQt.QtWidgets import QLabel, QFrame, QMessageBox

from qgis.core import (
    QgsProject,
    QgsMapLayer, QgsVectorLayer, QgsRasterLayer,
    QgsGeometry, QgsFeature, QgsWkbTypes,
    QgsMapSettings, 
    QgsCoordinateReferenceSystem, QgsCoordinateTransform,
    QgsMapRendererParallelJob 
)
from qgis.gui import QgsMapTool, QgsMapCanvasItem 

from osgeo import gdal, gdal_array, ogr, osr

from PIL import Image, ImageDraw
import numpy as np
from scipy import ndimage

import os


class MapItemFlood(QgsMapCanvasItem):
    def __init__(self, mapCanvas):
        super().__init__( mapCanvas )
        self.mapCanvas = mapCanvas
        self.layers = []
        self.enabled = True

    def paint(self, painter, *args): # NEED *args for   WINDOWS!
        def finished():
            image = job.renderedImage()
            if bool( self.mapCanvas.property('retro') ):
                image = image.scaled( image.width() / 3, image.height() / 3 )
                image = image.convertToFormat( QImage.Format_Indexed8, Qt.OrderedDither | Qt.OrderedAlphaDither )
            painter.drawImage( image.rect(), image )

        if not self.enabled or len( self.layers ) == 0:
            return

        settings = QgsMapSettings( self.mapCanvas.mapSettings() )
        settings.setLayers( self.layers )
        settings.setBackgroundColor( QColor( Qt.transparent ) )
        
        self.setRect( self.mapCanvas.extent() )
        job = QgsMapRendererParallelJob( settings ) 
        job.start()
        job.finished.connect( finished) 
        job.waitForFinished()
        
    def setLayers(self, layers):
        self.layers = layers


class ImageCanvas():
    def __init__(self, canvas):
        self.root = QgsProject.instance().layerTreeRoot()
        self.mapCanvas = canvas
        #
        self.dataset = None # set by process.finished
        self.extent = None
        self.rasters = None

    def _rastersCanvas(self):
        return [ l for l in self.root.checkedLayers() if not l is None and l.type() == QgsMapLayer.RasterLayer ]

    def process(self):
        def finished():
            def createDataset(image):
                def setGeoreference(ds):
                    #
                    extent = self.mapCanvas.extent()
                    imgWidth, imgHeight = image.width(), image.height()
                    resX, resY = extent.width() / imgWidth, extent.height() / imgHeight
                    geoTrans = ( extent.xMinimum(), resX, 0.0, extent.yMaximum(), 0.0, -1 * resY )
                    ds.SetGeoTransform( geoTrans )
                    # 
                    crs = self.mapCanvas.mapSettings().destinationCrs()
                    srs = osr.SpatialReference()
                    srs.ImportFromWkt( crs.toWkt() )
                    ds.SetSpatialRef( srs )
                # Copy image to QByteArray
                ba = QByteArray()
                buf = QBuffer( ba )
                buf.open( QIODevice.WriteOnly )
                image.save( buf, "TIFF", 100 )
                buf.close()
                # Create Dataset
                filename = '/vsimem/mem.tif'
                gdal.FileFromMemBuffer( filename, ba.data() )
                ds = gdal.Open( filename )
                ds_mem = gdal.GetDriverByName('MEM').CreateCopy( '', ds )
                setGeoreference( ds_mem )
                ds = None
                gdal.Unlink( filename )
                ba = None
                #
                return ds_mem

            image = job.renderedImage()
            if bool( self.mapCanvas.property('retro') ):
                image = image.scaled( image.width() / 3, image.height() / 3 )
                image = image.convertToFormat( QImage.Format_Indexed8, Qt.OrderedDither | Qt.OrderedAlphaDither )

            self.dataset = createDataset( image )

        self.dataset = None
        rasters = self._rastersCanvas()
        if not len( rasters ):
            return
        self.extent = self.mapCanvas.extent()
        self.rasters = rasters
        
        settings = QgsMapSettings( self.mapCanvas.mapSettings() )
        settings.setBackgroundColor( QColor( Qt.transparent ) )
        settings.setLayers( rasters )
        job = QgsMapRendererParallelJob( settings ) 
        job.start()
        job.finished.connect( finished) 
        job.waitForFinished()

    def changedCanvas(self):
        return not ( self.rasters == self._rastersCanvas() and self.extent == self.mapCanvas.extent() )


class CalculateArrayFlood():
    def __init__(self):
        self.flood_value = None # Calculate when read image
        self.flood_value_color = 255
        self.flood_out = 0
        self.threshFlood = 10 # 0 .. 255
        self.threshSieve = 100

    def get(self, arraySource, seed, threshFlood=None):
        as_image = (1,2,0)  # rows, columns, bands
        as_raster = (2,0,1) # bands, rows, columns
        #
        n_bands = arraySource.shape[0]
        arry = np.transpose( arraySource, as_image )
        img_flood = Image.fromarray( arry )
        l_flood_value = tuple( n_bands * [ self.flood_value ] )
        tf = threshFlood if threshFlood else self.threshFlood
        ImageDraw.floodfill( img_flood, seed, l_flood_value, thresh=tf )
        # Change outside flood
        arry = np.array( img_flood )
        arry = np.transpose( arry, as_raster )
        bool_out = ~(arry == self.flood_value)
        arry[ bool_out ] = self.flood_out
        # Sieve
        ds = gdal_array.OpenArray( arry ) # Read only
        dsSieve = gdal.GetDriverByName('MEM').CreateCopy('', ds )
        ds = None
        band_sieve = dsSieve.GetRasterBand(1)
        gdal.SieveFilter( srcBand=band_sieve, maskBand=None, dstBand=band_sieve, threshold=self.threshSieve, connectedness=8 )
        arry_sieve = band_sieve.ReadAsArray()
        for b in range( 1, dsSieve.RasterCount ):
            band = dsSieve.GetRasterBand( b+1 )
            gdal.SieveFilter( srcBand=band, maskBand=None, dstBand=band, threshold=self.threshSieve, connectedness=8 )
            arry_band = band.ReadAsArray()
            bool_s = ( arry_sieve == self.flood_value )
            bool_b = ( arry_band == self.flood_value )
            arry_sieve[ bool_s * bool_b ] = self.flood_value
            arry_sieve[ ~(bool_s * bool_b) ] = self.flood_out
        dsSieve = None

        arry_sieve[ arry_sieve == self.flood_value ] = self.flood_value_color
        return arry_sieve

    def getThresholdFlood(self, point1, point2):
        minDelta = 1
        maxDelta = 254
        delta = point2 - point1
        dX, dY = delta.x(), delta.y()
        delta = dX if abs( dX) > abs( dY ) else -1*dY
        threshFlood = self.threshFlood + delta
        if threshFlood < minDelta:
            threshFlood = minDelta
        if threshFlood > maxDelta:
            threshFlood = maxDelta
        return threshFlood


def createDatasetMem(arry, geoTransform, spatialRef, nodata=None):
    if len( arry.shape ) == 2:
        rows, columns = arry.shape
        bands = 1
    else:
        bands, rows, columns = arry.shape
    data_type = gdal_array.NumericTypeCodeToGDALTypeCode( arry.dtype )
    ds = gdal.GetDriverByName('MEM').Create('', columns, rows, bands, data_type )
    if bands == 1:
        band = ds.GetRasterBand(1)
        band.WriteArray( arry )
        if not nodata is None:
            band.SetNoDataValue( nodata )
    else:
        for b in range( bands ):
            band = ds.GetRasterBand( b+1 )
            band.WriteArray( arry[ b ] )
            if not nodata is None:
                band.SetNoDataValue( nodata )
    ds.SetGeoTransform( geoTransform )
    ds.SetSpatialRef( spatialRef )
    return ds


class ImageFlood():
    def __init__(self, mapCanvas):
        self.canvasImage = ImageCanvas( mapCanvas )
        self.mapItem = MapItemFlood( mapCanvas )
        self.calcFlood = CalculateArrayFlood()

        self.project = QgsProject.instance()

        self.arrys_flood = []
        self.arrys_flood_delete = []
        self.arryFloodMove = None

        self.lyrSeed = None
        
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

    def changedCanvas(self):
        return self.canvasImage.changedCanvas()

    def needSavePolygon(self):
        return self.canvasImage.changedCanvas() and len( self.arrys_flood )

    def updateCanvasImage(self):
        def getFloodValue():
            arry = self.canvasImage.dataset.ReadAsArray()
            for v in range(1, 256):
                if arry[arry == v].sum() == 0:
                    return v
            raise TypeError("Impossible define value of seed")

        self.arrys_flood *= 0
        self.arrys_flood_delete *= 0
        self.canvasImage.process()
        if not self.canvasImage.dataset:
            raise TypeError("Error created image from canvas. Check exists raster layer visible")
        self.calcFlood.flood_value = getFloodValue()

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

    def polygonizeFlood(self, layerFlood):
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

        crsLayer = layerFlood.crs()
        crsDS = QgsCoordinateReferenceSystem()
        crsDS.createFromString( layer.GetSpatialRef().ExportToWkt() )
        ct = QgsCoordinateTransform( crsDS, crsLayer, self.project )
        for feat in layer:
            g = QgsGeometry()
            g.fromWkb( feat.GetGeometryRef().ExportToIsoWkb() )
            g = g.smooth( self.smooth_iter, self.smooth_offset )
            g.transform( ct )
            f = QgsFeature()
            f.setGeometry( g )
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
    def __init__(self, iface):
        def layerWillBeRemoved(layerId):
            if self.layerFlood and self.layerFlood.id() == layerId:
                if self.imageFlood.totalFlood():
                    self._savePolygon()
                self.layerFlood = None

        def activated():
            def createLabelFlood():
                lbl = QLabel()
                lbl.setFrameStyle( QFrame.StyledPanel )
                lbl.setMinimumWidth( 100 )
                return lbl

            self.lblThreshFlood = createLabelFlood()
            self.lblMessageFlood = createLabelFlood()
            self.statusBar.addPermanentWidget( self.lblMessageFlood, 0)
            self.lblMessageFlood.setText(f"Flood: {self.imageFlood.totalFlood()} images")
            self.statusBar.addPermanentWidget( self.lblThreshFlood, 0)
            self.lblThreshFlood.setText(f"Treshold: {self.imageFlood.getCurrentThreshold()} RGB")

            # if self.layerFlood is None:
            #     self.layerFlood = QgsVectorLayer( 'Polygon?crs=EPSG:4326', 'flood', 'memory')
            #     self.project.addMapLayer( self.layerFlood )
            #     self.layerFlood.loadNamedStyle( self.stylePoylgon )

        def deactivated():
            self.statusBar.removeWidget( self.lblMessageFlood )
            self.statusBar.removeWidget( self.lblThreshFlood )

        def currentLayerChanged(layer):
            if self.isActive() and self.isEditabledPolygon( layer ):
                self.setLayerFlood( layer )

        self.mapCanvas = iface.mapCanvas()
        super().__init__( self.mapCanvas )
        self.statusBar = iface.mainWindow().statusBar()
        self.msgBar = iface.messageBar()
        self.project = QgsProject.instance()
        self.lblThreshFlood, self.lblMessageFlood = None, None

        self.project.layerWillBeRemoved.connect( layerWillBeRemoved )
        self.activated.connect( activated )
        self.deactivated.connect( deactivated )
        iface.layerTreeView().currentLayerChanged.connect( currentLayerChanged )

        self.imageFlood = ImageFlood( self.mapCanvas )
        
        self.hasPressPoint = False
        self.threshFloodMove = None

        self.pointCanvas = None
        
        self.stylePoylgon = os.path.join( os.path.dirname(__file__), 'polygonflood.qml' )

        self.layerFlood = None
        self.nameBack = None

    def __del_(self):
        del self.imageFlood

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

        self.hasPressPoint = True
        
        self.threshFloodMove = None
        self.arryFloodMove = None

        self.imageFlood.setLayerSeed( e.mapPoint() )
        self.pointCanvas = e.originalPixelPoint()

        if savePolygon():
            self.hasPressPoint = False # Escape canvasMoveEvent
        #self.lblMessageFlood.setText(f"Flood: {self.imageFlood.totalFlood()} images")

    def canvasMoveEvent(self, e):
        if not self.hasPressPoint: # Always e.button() = 0
            return

        if self.imageFlood.changedCanvas():
            self.imageFlood.updateCanvasImage()

        pointCanvas = e.originalPixelPoint()
        self.threshFloodMove = self.imageFlood.calculateThreshold( self.pointCanvas, pointCanvas )
        self.lblThreshFlood.setText(f"Treshold: {self.threshFloodMove} pixels")
        totalPixels = self.imageFlood.showFloodMovingCanvas( self.pointCanvas, self.threshFloodMove )
        if not totalPixels:
            self.threshFloodMove = None

    def canvasReleaseEvent(self, e):
        self.hasPressPoint = False
        if e.button() == Qt.RightButton:
            self.imageFlood.enabledFloodCanvas()
            return

        if self.threshFloodMove is None:
            self.lblThreshFlood.setText(f"Treshold: {self.imageFlood.getCurrentThreshold()} pixels")
            totalPixels = self.imageFlood.addFloodCanvas( self.pointCanvas )
            msg = f"{self.imageFlood.totalFlood()} images"
            msg = f"{msg} - Last image added {totalPixels} pixels" if totalPixels \
                else f"{msg} - Not added images( no pixels found)"
            self.lblMessageFlood.setText(f"Flood: {msg}")
            return
        
        totalPixels = self.imageFlood.addFloodMoveCanvas( self.threshFloodMove )
        msg = f"{self.imageFlood.totalFlood()} images - Last image added {totalPixels} pixels"
        self.lblMessageFlood.setText(f"Flood: {msg}")

    def keyReleaseEvent(self, e):
        key = e.key()
        if not key in( Qt.Key_D, Qt.Key_U, Qt.Key_H, Qt.Key_P, Qt.Key_C ): # Delete, Undo, Hole, Polygonize, Clear
            return

        if e.key() == Qt.Key_D:
            if self.imageFlood.deleteFlood():
                self.lblMessageFlood.setText(f"Flood: {self.imageFlood.totalFlood()} images")
            return

        if e.key() == Qt.Key_U:
            if self.imageFlood.undoFlood():
                self.lblMessageFlood.setText(f"Flood: {self.imageFlood.totalFlood()} images")
            return

        if e.key() == Qt.Key_H:
            if self.imageFlood.holeFlood():
                self.lblMessageFlood.setText(f"Flood: remove holes - {self.imageFlood.totalFlood()} images")
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

            totalFeats = self.imageFlood.polygonizeFlood( self.layerFlood )
            msg = 'Flood: Polygonize - Missing features' if not totalFeats \
                else f"Flood: Polygonize - {totalFeats} features added"
            self.lblMessageFlood.setText( msg )
            return

        if e.key() == Qt.Key_C:
            if self.imageFlood.clearFloodCanvas():
                self.lblMessageFlood.setText(f"Flood: clear - {self.imageFlood.totalFlood()} images")
            return


    def setLayerFlood(self, layer):
        if self.layerFlood == layer:
            return
        if self.imageFlood.totalFlood():
            self._savePolygon()
        if self.nameBack:
            self.layerFlood.setName( self.nameBack )
        self.nameBack = layer.name()
        self.layerFlood = layer
        msg = f"Current Flood layer is \"{self.nameBack}\""
        self.msgBar.pushInfo( self.PLUGINNAME, msg )
        name = f"Flood * {self.nameBack}"
        layer.setName( name )

    def _savePolygon(self):
        msg = f"Add features from images to \"{self.layerFlood.name()}\" ?"
        ret = QMessageBox.question(None, self.PLUGINNAME, msg, QMessageBox.Yes | QMessageBox.No )
        if ret == QMessageBox.Yes:
            totalFeats = self.imageFlood.polygonizeFlood( self.layerFlood )
            msg = 'Flood: Polygonize - Missing features' if not totalFeats \
                else f"Flood: Polygonize - {totalFeats} features added"
            self.lblMessageFlood.setText( msg )
            return True
        return False


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
