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


from qgis.PyQt.QtCore import Qt, QByteArray, QBuffer, QIODevice, pyqtSignal
from qgis.PyQt.QtGui import QImage, QColor

from qgis.core import (
    QgsProject,
    QgsMapLayer,
    QgsMapSettings, 
    QgsMapRendererParallelJob,
    QgsCoordinateTransform
)
from qgis.gui import QgsMapCanvasItem 

from osgeo import gdal, gdal_array, osr

from PIL import Image, ImageDraw
import numpy as np


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


class CanvasImage():
    def __init__(self, canvas):
        self.project = QgsProject.instance()
        self.root = self.project.layerTreeRoot()
        self.mapCanvas = canvas
        # Set by process
        self.extent = None
        self.dataset = None # set by process.finished

    def rasterLayers(self):
        """
        return: [ QgsRasterLayer ]
        """
        def getExtent(layer, ct):
            crsLayer = layer.crs()
            ct.setSourceCrs( crsLayer )
            return ct.transform( layer.extent() )

        layers =  [ l for l in self.root.checkedLayers() if not l is None and l.type() == QgsMapLayer.RasterLayer ]
        if not len( layers ):
            return []
        # Check Intersects
        extent = self.mapCanvas.extent()
        ct = QgsCoordinateTransform()
        ct.setDestinationCrs( self.project.crs() )
        layersCanvas = [] # [ QgsRasterLayer ]
        for layer in layers:
            extLayer = getExtent( layer, ct )
            if extent.intersects( extLayer ):
                layersCanvas.append( layer )
        return layersCanvas

    def process(self, rasters):
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
        self.extent = self.mapCanvas.extent()
        
        settings = QgsMapSettings( self.mapCanvas.mapSettings() )
        settings.setBackgroundColor( QColor( Qt.transparent ) )
        settings.setLayers( rasters )
        job = QgsMapRendererParallelJob( settings ) 
        job.start()
        job.finished.connect( finished) 
        job.waitForFinished()

    def changedCanvas(self):
        return not self.extent == self.mapCanvas.extent()


class CalculateArrayFlood():
    def __init__(self):
        self.flood_value = None
        self.flood_value_color = 255
        self.flood_out = 0
        self.threshFlood = 10 # 0 .. 255
        self.threshSieve = 100

    def get(self, arraySource, seed, threshFlood=None):
        def sieve(arry):
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
            return arry_sieve
            
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
        arry = sieve( arry )
        arry[ arry == self.flood_value ] = self.flood_value_color
        return arry

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

    def setFloodValue(self, dsImage):
        arry = dsImage.ReadAsArray()
        for v in range(1, 256):
            if arry[arry == v].sum() == 0:
                self.flood_value = v
                return True
        return False


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


def connectSignalSlot(signal, slot):
    """ Connect signal with slot if not connected
    :param signal: signal of QObject
    :param slot:   slot of QObject
    """
    try:
        signal.disconnect( slot )
    except TypeError:
        pass
    signal.connect( slot )
