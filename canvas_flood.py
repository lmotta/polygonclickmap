
from qgis.PyQt.QtCore import Qt, QByteArray, QBuffer, QIODevice
from qgis.PyQt.QtGui import QImage, QColor 

from qgis.core import (
    QgsProject,
    QgsMapLayer, QgsVectorLayer, QgsRasterLayer,
    QgsGeometry, QgsFeature,
    QgsMapSettings, 
    QgsMapRendererParallelJob 
)
from qgis.gui import QgsMapToolEmitPoint, QgsMapCanvasItem

from qgis import utils as QgsUtils

from osgeo import gdal, gdal_array, ogr, osr

from PIL import Image, ImageDraw

import numpy as np

import os


class MapItemFlood(QgsMapCanvasItem):
    def __init__(self, canvas):
        super().__init__( canvas )
        self.image = None
        self.layers = None
        self.mapCanvas = canvas
      
    def _setImage(self):
        def finished():
            image = job.renderedImage()
            if bool( self.mapCanvas.property('retro') ):
                image = image.scaled( image.width() / 3, image.height() / 3 )
                image = image.convertToFormat( QImage.Format_Indexed8, Qt.OrderedDither | Qt.OrderedAlphaDither )
            self.image = image

        settings = QgsMapSettings( self.mapCanvas.mapSettings() )
        settings.setLayers( self.layers )
        settings.setBackgroundColor( QColor( Qt.transparent ) )
        
        self.setRect( self.mapCanvas.extent() )
        job = QgsMapRendererParallelJob( settings ) 
        job.start()
        job.finished.connect( finished) 
        job.waitForFinished()

    def paint(self, painter, *args): # NEED *args for   WINDOWS!
        self._setImage()
        painter.drawImage( self.image.rect(), self.image )
        
    def setLayers(self, layers):
        self.layers = layers


class CanvasDatasetImage():
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
        if DEBUG:
            #image.save( FILENAME_IMAGE, 'TIFF', 100)
            _ds = gdal.GetDriverByName('GTiff').CreateCopy( FILENAME_ARRAY, ds_mem)
            _ds = None

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


class CanvasFlood():
    def __init__(self):
        self.mapCanvas = QgsUtils.iface.mapCanvas()
        self.statusBar = QgsUtils.iface.mainWindow().statusBar()
        self.extent = None
        self.transform = self.mapCanvas.getCoordinateTransform().transform
        self.mapCanvasImage = CanvasDatasetImage( self.mapCanvas )
        self.mapItem = None

        self.pointTool = QgsMapToolEmitPoint( self.mapCanvas )
        self.pointTool.canvasClicked.connect( self._canvasClicked )

        self.flood_value = 255
        self.flood_out = 0
        self.threshFlood = 55
        self.threshSieve = 100

        self.smooth_iter = 1
        self.smooth_offset  = 0.25

        self.point_canvas = None
        self.point_map = None
        self.arrys_flood = []
        self.polygonLast = None
        
        self.filenameMemory = '/vsimem/raster.tif'
        self.existsLink = False

    def __del_(self):
        self.mapCanvasImage.dataset = None

    def _writeMessage(self, message):
        self.statusBar.showMessage (f"Flood: {message}")

    def _canvasClicked(self, point, button):
        def createFlood():
            self.point_map = point
            self.point_canvas = self.transform( point )
            if not self.extent == self.mapCanvas.extent():
                self._writeMessage('Creating canvas image...')
                self.arrys_flood *= 0
                self.mapCanvasImage.process()
                if not self.mapCanvasImage.dataset:
                    self._writeMessage('Empty image!')
                    return
                self.extent = self.mapCanvas.extent()
            self.createFlood()

        actions = {
            Qt.LeftButton: createFlood,
            Qt.RightButton: self.removeLastFlood
        }
        actions[ button ]()

    def _calculateArryFlood(self):
        as_image = (1,2,0) # Rasterio.plot.reshape_as_image - rows, columns, bands
        as_raster = (2,0,1) # Rasterio.plot.reshape_as_raster - bands, rows, columns
        #
        arry = self.mapCanvasImage.dataset.ReadAsArray()[:3] # RGBA: NEED Remove Alpha band(255 for all image)
        n_bands = arry.shape[0]
        arry = np.transpose( arry, as_image )
        img_flood = Image.fromarray( arry )
        l_flood_value = tuple( n_bands * [ self.flood_value ] )
        x, y = int(self.point_canvas.x()), int(self.point_canvas.y())
        ImageDraw.floodfill( img_flood, (x, y), l_flood_value, thresh=self.threshFlood )
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
        self.arrys_flood.append( arry_sieve )

    def _createDatasetMem(self, arry):
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
        else:
            for b in range( bands ):
                band = ds.GetRasterBand( b+1 )
                band.WriteArray( arry[ b ] )
        ds.SetGeoTransform( self.mapCanvasImage.dataset.GetGeoTransform() )
        ds.SetSpatialRef( self.mapCanvasImage.dataset.GetSpatialRef() )
        return ds

    def _saveFloodTif(self, arry):
        ds = gdal.GetDriverByName('GTiff').CreateCopy( FILENAME_FLOOD, self._createDatasetMem( arry ) )
        ds.GetRasterBand(1).SetNoDataValue( self.flood_out )
        ds = None

    def _reduceArrysFlood(self):
        result = self.arrys_flood[0].copy()
        if len( self.arrys_flood ) == 1:
            return result
        for arry in self.arrys_flood[1:]:
            bool_b = ( arry == self.flood_value )
            result[ bool_b ] = self.flood_value
        return result

    def _reduceArrysFloodUntilLast(self):
        result = self.arrys_flood[0].copy()
        total = len( self.arrys_flood )
        if total == 1:
            return None
        for arry in self.arrys_flood[1:total]:
            bool_b = ( arry == self.flood_value )
            result[ bool_b ] = self.flood_value
        return result

    def _polygonizeFlood(self):
        self._writeMessage('Creating vector flood...')
        #dsImage = self._createDatasetMem( self._reduceArrysFlood() )
        dsImage = self._createDatasetMem( self.arrys_flood[-1] )
        band = dsImage.GetRasterBand(1)
        ds = ogr.GetDriverByName('MEMORY').CreateDataSource('memData')
        layer = ds.CreateLayer( name='memLayer', srs=dsImage.GetSpatialRef(), geom_type=ogr.wkbPolygon )
        gdal.Polygonize( srcBand=band, maskBand=band, outLayer=layer, iPixValField=-1)
        
        crs = self.mapCanvas.mapSettings().destinationCrs().authid()
        uri = "polygon?crs={crs}"
        self.polygonLast = QgsVectorLayer( uri, 'flood', 'memory')
        prov = self.polygonLast.dataProvider()
        for feat in layer:
            g = QgsGeometry()
            g.fromWkb( feat.GetGeometryRef().ExportToIsoWkb() )
            f = QgsFeature()
            f.setGeometry( g.smooth( self.smooth_iter, self.smooth_offset ) )
            prov.addFeature( f )
        self.polygonLast.updateExtents()
        ds = None

    def createFlood(self):
        if self.point_map is None:
            return
        self.mapCanvas.flashGeometries( [ QgsGeometry.fromPointXY( self.point_map ) ] )
        self._writeMessage('Creating image flood...')
        self._calculateArryFlood()

        if DEBUG:
            # self._saveFloodTif( self.arrys_flood[0] )
            # if len(self.arrys_flood) > 1:
            #     self._saveFloodTif( self.arrys_flood[1] )
            self._saveFloodTif( self._reduceArrysFlood() )

        self._polygonizeFlood()
        
        if self.mapItem:
            self.mapCanvas.scene().removeItem( self.mapItem )
        if self.existsLink:
            gdal.Unlink( self.filenameMemory )

        self.mapItem = MapItemFlood( self.mapCanvas )
        layers = [ self.polygonLast]
        arryLast = self._reduceArrysFloodUntilLast()
        if arryLast:
            ds1 = self._createDatasetMem( arryLast )
            ds2 = gdal.GetDriverByName('GTiff').CreateCopy( self.filenameMemory, ds1 )
            ds1, ds2 = None, None
            layers.append( QgsRasterLayer( self.filenameMemory, 'raster', 'gdal') )
            self.existsLink = True
        self.mapItem.setLayers( layers )
        #self.showFlood()

    def showFlood(self):
        if not len( self.geoms_flood ):
            return
        self.mapCanvas.flashGeometries( self.geoms_flood )
        self.statusBar.clearMessage()
        #saveShp( geoms, self.mapCanvasImage.dataset.GetSpatialRef() )

    def removeLastFlood(self):
        if not len( self.arrys_flood ):
            return
        self.arrys_flood.pop()
        if not len( self.arrys_flood ):
            self.geoms_flood *= 0
            return
        self._polygonizeFlood()
        self.showFlood()
        
    def active(self):
        self.mapCanvas.setMapTool( self.pointTool )
        self._writeMessage('Actived')


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


cf = CanvasFlood()
cf.active()
#cf.createFlood() # Change tolerance
#cf.showFlood() # View last flood
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
