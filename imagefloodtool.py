
from qgis.PyQt.QtCore import Qt, QByteArray, QBuffer, QIODevice
from qgis.PyQt.QtGui import QImage, QColor 

from qgis.core import (
    QgsProject,
    QgsMapLayer, QgsVectorLayer, QgsRasterLayer,
    QgsGeometry, QgsFeature, QgsPointXY,
    QgsMapSettings, 
    QgsMapRendererParallelJob 
)
from qgis.gui import QgsMapTool, QgsMapCanvasItem 

from osgeo import gdal, gdal_array, ogr, osr

from PIL import Image, ImageDraw

import numpy as np

import os, time


class MapItemFlood(QgsMapCanvasItem):
    def __init__(self, mapCanvas):
        super().__init__( mapCanvas )
        self.mapCanvas = mapCanvas
        self.enabled = True
        self.layers = None
        self.image = None

    def _setImage(self):
        def finished():
            image = job.renderedImage()
            if bool( self.mapCanvas.property('retro') ):
                image = image.scaled( image.width() / 3, image.height() / 3 )
                image = image.convertToFormat( QImage.Format_Indexed8, Qt.OrderedDither | Qt.OrderedAlphaDither )
            self.image = image

        settings = QgsMapSettings( self.mapCanvas.mapSettings() )
        if len( self.layers ):
            settings.setLayers( self.layers )
        settings.setBackgroundColor( QColor( Qt.transparent ) )
        
        self.setRect( self.mapCanvas.extent() )
        job = QgsMapRendererParallelJob( settings ) 
        job.start()
        job.finished.connect( finished) 
        job.waitForFinished()

    def paint(self, painter, *args): # NEED *args for   WINDOWS!
        if not self.layers:
            return

        if not self.enabled:
            image = QImage( 1, 1, QImage.Format_RGB32 )
            image.fill( QColor( Qt.transparent ) )
            painter.drawImage( image.rect(), image )
            return

        self._setImage()
        painter.drawImage( self.image.rect(), self.image )
        
    def setLayers(self, layers):
        self.layers = layers
        self.enabled = True


class ImageCanvas():
    def __init__(self, canvas):
        self.root = QgsProject.instance().layerTreeRoot()
        self.mapCanvas = canvas
        #
        self.dataset = None

    def _setDataset(self, image):
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
        self.dataset = ds_mem

    def process(self):
        def finished():
            image = job.renderedImage()
            if bool( self.mapCanvas.property('retro') ):
                image = image.scaled( image.width() / 3, image.height() / 3 )
                image = image.convertToFormat( QImage.Format_Indexed8, Qt.OrderedDither | Qt.OrderedAlphaDither )

            self._setDataset( image )

        self.dataset = None
        rasters = [ l for l in self.root.checkedLayers() if not l is None and l.type() == QgsMapLayer.RasterLayer ]
        if not len( rasters ):
            return
        
        settings = QgsMapSettings( self.mapCanvas.mapSettings() )
        settings.setBackgroundColor( QColor( Qt.transparent ) )
        settings.setLayers( rasters )
        job = QgsMapRendererParallelJob( settings ) 
        job.start()
        job.finished.connect( finished) 
        job.waitForFinished()


class CalculateArrayFlood():
    flood_value = 255
    flood_out = 0
    threshFlood = 55
    threshSieve = 100
    def get(self, arraySource, seed):
        as_image = (1,2,0) # Rasterio.plot.reshape_as_image - rows, columns, bands
        as_raster = (2,0,1) # Rasterio.plot.reshape_as_raster - bands, rows, columns
        #
        n_bands = arraySource.shape[0]
        arry = np.transpose( arraySource, as_image )
        img_flood = Image.fromarray( arry )
        l_flood_value = tuple( n_bands * [ self.flood_value ] )
        ImageDraw.floodfill( img_flood, seed, l_flood_value, thresh=self.threshFlood )
        # Change outside flood
        arry = np.array( img_flood )
        arry = np.transpose( arry, as_raster )
        bool_out = ~(arry == self.flood_value)
        arry[ bool_out ] = self.flood_out
        # Sieve
        ds = gdal_array.OpenArray( arry ) # Read only
        ds = gdal.GetDriverByName('MEM').CreateCopy('', ds )
        band_sieve = ds.GetRasterBand(1)
        gdal.SieveFilter( srcBand=band_sieve, maskBand=None, dstBand=band_sieve, threshold=self.threshSieve, connectedness=8 )
        arry_sieve = band_sieve.ReadAsArray()
        for b in range( 1, ds.RasterCount ):
            band = ds.GetRasterBand( b+1 )
            gdal.SieveFilter( srcBand=band, maskBand=None, dstBand=band, threshold=self.threshSieve, connectedness=8 )
            arry_band = band.ReadAsArray()
            bool_s = ( arry_sieve == self.flood_value )
            bool_b = ( arry_band == self.flood_value )
            arry_sieve[ bool_s * bool_b ] = self.flood_value
            arry_sieve[ ~(bool_s * bool_b) ] = self.flood_out
        return arry_sieve


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


class ImageFloodTool(QgsMapTool):
    def __init__(self, iface):
        self.mapCanvas = iface.mapCanvas()
        super().__init__( self.mapCanvas )
        self.extent = None
        self.transform = self.mapCanvas.getCoordinateTransform().transform
        self.canvasImage = ImageCanvas( self.mapCanvas )
        self.mapItem = MapItemFlood( self.mapCanvas )

        self.calcFlood = CalculateArrayFlood()
        self.smooth_iter = 1
        self.smooth_offset  = 0.25

        self.point_canvas = None
        self.point_map = None
        self.arrys_flood = []
        
        self.stylePoylgon = os.path.join( os.path.dirname(__file__), 'polygonflood.qml' )
        self.stylePoint = os.path.join( os.path.dirname(__file__), 'pointflood.qml' )
        self.styleRaster = os.path.join( os.path.dirname(__file__), 'rasterflood.qml' )
        
        self.filenameRasterFlood = '/vsimem/raster_flood.tif'
        self.existsLinkRasterFlood = False

    def __del_(self):
        self.canvasImage.dataset = None

    def canvasReleaseEvent(self, e):
        if e.button() == Qt.RightButton:
            self.mapItem.enabled = True
            self.mapItem.updateCanvas()
            return

        self.point_map = e.mapPoint()
        self.point_canvas = e.originalPixelPoint ()
        if not self.extent == self.mapCanvas.extent():
            self.arrys_flood *= 0
            self.canvasImage.process()
            if not self.canvasImage.dataset:
                return
            self.extent = self.mapCanvas.extent()
        self.createFlood()

    def canvasPressEvent(self, e):
        if e.button() == Qt.RightButton:
            self.mapItem.enabled = False
            self.mapItem.updateCanvas()

    def keyReleaseEvent(self, e):
        def setMapItem(layers=[]):
            self.mapItem.setLayers( layers )
            self.mapItem.updateCanvas()

        if e.key() == Qt.Key_Backspace:
            if len( self.arrys_flood ):
                self.arrys_flood.pop()
                if not len( self.arrys_flood ):
                    setMapItem()
                    return
                arryFlood = self._reduceArrysFlood()
                if arryFlood is None:
                    setMapItem()
                    return
                setMapItem( [ self._rasterFlood( arryFlood) ] )

    def _reduceArrysFlood(self):
        result = self.arrys_flood[0].copy()
        if len( self.arrys_flood ) == 1:
            return result
        for arry in self.arrys_flood[1:]:
            bool_b = ( arry == CalculateArrayFlood.flood_value )
            result[ bool_b ] = CalculateArrayFlood.flood_value
        return result

    def _reduceArrysFloodUntilLast(self):
        result = self.arrys_flood[0].copy()
        total = len( self.arrys_flood )
        if total < 2 :
            return None
        for arry in self.arrys_flood[1:total-1]:
            bool_b = ( arry == CalculateArrayFlood.flood_value )
            result[ bool_b ] = CalculateArrayFlood.flood_value
        return result

    def _createQgsMemoryVector(self, name, geomType, data):
        def addFeaturesPointXY(prov):
            f = QgsFeature()
            f.setGeometry( QgsGeometry.fromPointXY( data ) )
            prov.addFeature( f )

        def addFeaturesLayer(prov):
            for feat in data:
                g = QgsGeometry()
                g.fromWkb( feat.GetGeometryRef().ExportToIsoWkb() )
                f = QgsFeature()
                f.setGeometry( g.smooth( self.smooth_iter, self.smooth_offset ) )
                prov.addFeature( f )

        geomStyles = {
            'point': self.stylePoint,
            'polygon': self.stylePoylgon
        }
        if not geomType in geomStyles:
            TypeError(f"Only Geometries '{''.join( geomStyles )}' are allowed")

        crs = self.mapCanvas.mapSettings().destinationCrs().authid()
        uri = f"{geomType}?crs={crs}"
        l = QgsVectorLayer( uri, name, 'memory')
        prov = l.dataProvider()
        if isinstance( data,  QgsPointXY ):
            addFeaturesPointXY( prov )
        elif isinstance( data,  ogr.Layer ):
             addFeaturesLayer( prov )
        else:
            raise TypeError("Only ogr.Layer or QgsPointXY are allowed")

        l.updateExtents()
        l.loadNamedStyle( geomStyles[ geomType ] )
        return l

    def _rasterFlood(self, arrayFlood):
        if self.existsLinkRasterFlood:
            gdal.Unlink( self.filenameRasterFlood )
        tran = self.canvasImage.dataset.GetGeoTransform()
        sr = self.canvasImage.dataset.GetSpatialRef()
        ds1 = createDatasetMem( arrayFlood, tran, sr, CalculateArrayFlood.flood_out )
        if DEBUG:
            ds_ = gdal.GetDriverByName('GTiff').CreateCopy( FILENAME_FLOOD, ds1 )
            ds_ = None
        ds2 = gdal.GetDriverByName('GTiff').CreateCopy( self.filenameRasterFlood, ds1 )
        ds1, ds2 = None, None
        rl = QgsRasterLayer( self.filenameRasterFlood, 'raster', 'gdal')
        rl.loadNamedStyle( self.styleRaster )
        self.existsLinkRasterFlood = True
        return rl

    def _polygonizeFlood(self, arrayFlood):
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
        polygonFlood = self._createQgsMemoryVector( 'flood', 'polygon', layer )
        ds = None
        return polygonFlood

    def createFlood(self):
        if self.point_map is None:
            return
        
        # Populate Arrays flood
        arry = self.canvasImage.dataset.ReadAsArray()[:3] # RGBA: NEED Remove Alpha band(255 for all image)
        seed = ( self.point_canvas.x(), self.point_canvas.y() )
        self.arrys_flood.append( self.calcFlood.get( arry, seed) )

        lyr_seed = self._createQgsMemoryVector( 'seed', 'point',  self.point_map )

        # self._polygonizeFlood( self.arrys_flood[-1] ) # Last
        # self._polygonizeFlood( self._reduceArrysFlood() ) # All(reduce)
        # self._polygonizeFlood( self._reduceArrysFloodUntilLast() ) # All(reduce) until last

        # layers = [ lyr_seed, self._polygonizeFlood() ]
        layers = [ lyr_seed ]
        #arryFlood = self._reduceArrysFloodUntilLast()
        arryFlood = self._reduceArrysFlood()
        if not arryFlood is None:
            layers.append( self._rasterFlood( arryFlood) )
        self.mapItem.setLayers( layers )
        self.mapItem.updateCanvas()

    def removeLastFlood(self):
        if not len( self.arrys_flood ):
            return
        self.arrys_flood.pop()
        if not len( self.arrys_flood ):
            self.geoms_flood *= 0
            return
        self._polygonizeFlood()


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


#cf = CanvasFlood()
#cf.active()
#cf.createFlood() # Change tolerance
#cf.removeLastFlood() # Remove last flood

FILENAME_IMAGE = '/home/lmotta/data/work/AAA_IMAGE.tif'
FILENAME_ARRAY = '/home/lmotta/data/work/AAA_ARRAY.tif'
FILENAME_FLOOD = '/home/lmotta/data/work/AAA_FLOOD.tif'
DEBUG = False


"""
1) Adicionar QgsMapCanvasItem:
.) /home/lmotta/.local/share/QGIS/QGIS3/profiles/default/python/plugins/mapswipetool_plugin/mapswipetool.py
.) /home/lmotta/.local/share/QGIS/QGIS3/profiles/default/python/plugins/mapswipetool_plugin/swipemap.py
.) QgsMapCanvasItem.paint:
    image = QImage *** Obtido via Array(Numpy) -> QImage(im_np, im_np.shape[1], im_np.shape[0], QImage.Format_RGB888 )
    painter.drawImage( QRect( 0,0,w,h ), image )
https://stackoverflow.com/questions/48639185/pyqt5-qimage-from-numpy-array

2) Aumentar a tolerancia p/ o Flood
.) Criar a ferramenta a partir de QgsMapTool ou QgsMapToolEmitPoint
Ao mover o mouse pressionando o button, aumenta/diminui a tolerância
"""
