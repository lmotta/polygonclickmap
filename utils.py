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


from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QImage, QColor

from qgis.core import (
    QgsProject, QgsApplication,
    QgsMapLayer, QgsRasterLayer,
    QgsMapSettings,
    QgsMapRendererParallelJob,
    QgsCoordinateTransform,
    QgsGeometry, QgsPolygon, QgsLineString, QgsPoint,
    QgsFeature,
    QgsMessageOutput
)
from qgis.gui import QgsMapCanvasItem 

from osgeo import gdal, gdal_array, osr

import numpy as np
import os


class MapItemLayers(QgsMapCanvasItem):
    def __init__(self, mapCanvas):
        super().__init__( mapCanvas )
        self.mapCanvas = mapCanvas
        self.project = QgsProject.instance()
        self.enabled = True
        self.layers = []
        self.crs = None

    def paint(self, painter, *args): # NEED *args for   WINDOWS!
        def finished():
            image = job.renderedImage()
            if bool( self.mapCanvas.property('retro') ):
                image = image.scaled( image.width() / 3, image.height() / 3 )
                image = image.convertToFormat( QImage.Format_Indexed8, Qt.OrderedDither | Qt.OrderedAlphaDither )
            painter.drawImage( image.rect(), image )
            job.finished.disconnect( finished) 

        if not ( self.enabled and len( self.layers ) ):
            return

        settings = QgsMapSettings( self.mapCanvas.mapSettings() )
        settings.setLayers( self.layers )
        settings.setBackgroundColor( QColor( Qt.transparent ) )
        
        self.setRect( self.mapCanvas.extent() )
        job = QgsMapRendererParallelJob( settings ) 
        job.start()
        job.finished.connect( finished) 
        job.waitForFinished()
        
    def updateCanvas(self, layers=None):
        if not layers is None:
            for l in layers:
                l = None # Free resources
            self.layers = layers
        self.crs = self.project.crs()
        super().updateCanvas()

    def changeExtentByCrs(self):
        crs = self.project.crs()
        if crs == self.crs:
            return True

        rect = self.rect()
        ct = QgsCoordinateTransform()
        ct.setSourceCrs( self.crs )
        ct.setDestinationCrs( crs )
        try:
            rectNew = ct.transform( rect )
        except:
            return False
        self.setRect( rectNew )
        self.crs = crs
        return True

    def backCrs(self):
        if self.crs:
            self.mapCanvas.setDestinationCrs( self.crs )

class CanvasArrayRGB():
    def __init__(self, canvas):
        self.project = QgsProject.instance()
        self.root = self.project.layerTreeRoot()
        self.mapCanvas = canvas
        # Set by process.finished
        self.extent = None
        self.crs = None
        self.georeference = { 'geoTransform': None, 'spatialRef': None } # createDatasetImageFromArray
        self.array = None

    def rasterLayers(self):
        """
        return: [ QgsRasterLayer ]
        """
        def intersectsExtents( layer):
            ct.setDestinationCrs( layer.crs() )
            extent = ct.transform( extCanvas )
            return extent.intersects( layer.extent())

        layers =  [ l for l in self.root.checkedLayers() if not l is None and l.type() == QgsMapLayer.RasterLayer ]
        if not len( layers ):
            return []
        # Check Intersects
        ct = QgsCoordinateTransform()
        ct.setSourceCrs( self.project.crs() )
        extCanvas = self.mapCanvas.extent()
        
        return  [ layer for layer in layers if intersectsExtents( layer ) ]

    def process(self, rasters):
        def finished():
            def setArray(image):
                b = image.bits()
                width, height = image.width(), image.height()
                bands = 4 # RGBA
                b.setsize( height * width * bands ) # rows, columns, bands
                arry = np.frombuffer(b, np.uint8).reshape(( height,  width, bands ) )
                # arry -> rows, columns, bands => as_image = [1,2,0]
                as_raster = [2,0,1] # bands, rows, columns
                arry = np.transpose( arry, as_raster )
                self.array = arry[:3].copy() # RGBA: NEED Remove Alpha

            def setGeoreference(image, extent):
                imgWidth, imgHeight = image.width(), image.height()
                resX, resY = extent.width() / imgWidth, extent.height() / imgHeight
                transform =  ( extent.xMinimum(), resX, 0.0, extent.yMaximum(), 0.0, -1 * resY )

                crs = self.mapCanvas.mapSettings().destinationCrs()
                srs = osr.SpatialReference()
                srs.ImportFromWkt( crs.toWkt() )
                
                self.georeference['geoTransform'] = transform
                self.georeference['spatialRef'] = srs
                
            image = job.renderedImage()
            if bool( self.mapCanvas.property('retro') ):
                image = image.scaled( image.width() / 3, image.height() / 3 )
                image = image.convertToFormat( QImage.Format_Indexed8, Qt.OrderedDither | Qt.OrderedAlphaDither )

            self.crs = self.project.crs()
            extent = self.mapCanvas.extent()
            self.extent = extent
            setGeoreference( image, extent )
            setArray( image )

        self.array = None

        settings = QgsMapSettings( self.mapCanvas.mapSettings() )
        settings.setBackgroundColor( QColor( Qt.transparent ) )
        settings.setLayers( rasters )
        job = QgsMapRendererParallelJob( settings ) 
        job.start()
        job.finished.connect( finished) 
        job.waitForFinished()

    def changedCanvas(self):
        return not self.extent == self.mapCanvas.extent() or not self.crs == self.project.crs()

    def getGeoreference(self):
        return self.georeference.copy() # shallow copy

class CalculateArrayFlood():
    def __init__(self):
        self.flood_value_color = 255
        self.flood_out = 0
        self.minValue, self.maxValue = 1, 254
        self.threshFlood = 50 # 0 .. 255
        self.threshSieve = 100
        self.coordinatesAdjacentPixels = self._coordinatesAdjacent4Pixels

    def get(self, arraySource, seed, isCanceled, arrayFloodBack=None, threshould=None):
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
                bool_s = ( arry_sieve == flood_value )
                bool_b = ( arry_band == flood_value )
                arry_sieve[ bool_s * bool_b ] = flood_value
                arry_sieve[ ~(bool_s * bool_b) ] = self.flood_out
            dsSieve = None
            return arry_sieve

        def floodfill():
            # Adaptation from https://github.com/python-pillow/Pillow/src/PIL/ImageDraw.py
            def isSameValue(row, col):
                for idx in range( n_bands ):
                    if abs( value_seed[ idx ] - arry_flood[ idx, row, col ].item() ) > thresh:
                        return False
                return True

            def process():
                row, col = seed[1], seed[0]
                for idx in range( n_bands ):
                    value_seed.append( arry_flood[ idx, row, col ] )
                    arry_flood[ idx, row, col ] = flood_value
                edge = { ( row, col ) }
                full_edge = set()
                while edge:
                    new_edge = set()
                    for ( row, col ) in edge:
                        if isCanceled():
                            return None
                        for (s, t) in self.coordinatesAdjacentPixels( row, col ):
                            # If already processed, or if a coordinate is negative, or a coordinate greather image limit, skip
                            if (s, t) in full_edge or s < 0 or t < 0 or s > (rows-1) or t > (cols-1):
                                continue
                            coord = ( s, t )
                            full_edge.add( coord )
                            if isSameValue( coord[0], coord[1] ):
                                arry_flood[ :, coord[0], coord[1] ] = flood_value
                                new_edge.add((s, t))
                    full_edge = edge  # discard pixels processed
                    edge = new_edge

                return arry_flood

            def processFloodBack():
                def isBoundary(row, col):
                    for idx in range( n_bands ):
                        if not arry_flood[ idx, row, col ].item() == flood_value_back:
                            return False
                    return True

                flood_value_back = 1001 # RGB value 0 - 255
                bool_FloodBack = ( arrayFloodBack == self.flood_value_color )
                row, col = seed[1], seed[0]
                for idx in range( n_bands ):
                    value_seed.append( arry_flood[ idx, row, col ] )
                    arry_flood[ idx, row, col ] = flood_value
                    arry_flood[ idx ][ bool_FloodBack ] = flood_value_back # Boundary
                edge = { ( row, col ) }
                full_edge = set()
                while edge:
                    new_edge = set()
                    for ( row, col ) in edge:
                        if isCanceled():
                            return None
                        for (s, t) in self.coordinatesAdjacentPixels( row, col ):
                            # If already processed, or if a coordinate is negative, or a coordinate greather image limit, skip
                            if (s, t) in full_edge or s < 0 or t < 0 or s > (rows-1) or t > (cols-1):
                                continue
                            coord = ( s, t )
                            full_edge.add( coord )
                            if isBoundary( coord[0], coord[1] ):
                                continue
                            if isSameValue( coord[0], coord[1] ):
                                arry_flood[ :, coord[0], coord[1] ] = flood_value
                                new_edge.add((s, t))
                    full_edge = edge  # discard pixels processed
                    edge = new_edge

                for idx in range( n_bands ):
                    arry_flood[ idx ][ bool_FloodBack ] = self.flood_out # Remove Boundary

                return arry_flood

            thresh = threshould if threshould else self.threshFlood
            ( n_bands, rows, cols ) = arraySource.shape
            value_seed = []
            return processFloodBack() if not arrayFloodBack is None else process()

        flood_value = 1000 # RGB value 0 - 255
        arry_flood = arraySource.astype('uint16') # Using flood_value and flood_value_back
        arry_flood = floodfill()
        if arry_flood is None:
            return None # Cancel

        bool_out = ~(arry_flood == flood_value)
        arry_flood[ bool_out ] = self.flood_out
        arry_flood = sieve( arry_flood )
        arry_flood[ arry_flood == flood_value ] = self.flood_value_color
        return arry_flood.astype('uint8')

    def getThresholdFlood(self, point1, point2):
        minDelta = 1
        maxDelta = 254
        delta = point2 - point1
        dX, dY = delta.x(), delta.y()
        delta = dX if abs( dX) > abs( dY ) else -1*dY
        threshFlood = self.threshFlood + delta
        if threshFlood < self.minValue:
            threshFlood = self.minValue
        if threshFlood > self.maxValue:
            threshFlood = self.maxValue
        return threshFlood

    def setCoordinatesAdjacentPixels(self, is8pixels):
        self.coordinatesAdjacentPixels = self._coordinateAdjacent8Pixels if is8pixels else self._coordinatesAdjacent4Pixels

    def setFloodValueFromDatasetImage(self, dsImage):
        return self.setFloodValue( dsImage.ReadAsArray() )

    def _coordinatesAdjacent4Pixels(self, row, col):
        coords = []
        for d in (-1, 1):
            coords.append( ( row+d, col ) )
            coords.append( ( row, col+d ) )
        return coords

    def _coordinateAdjacent8Pixels(self, row, col):
        coords = self._coordinatesAdjacent4Pixels( row, col )
        for d in (-1, 1):
            coords.append( ( row+d, col+d ) )
            coords.append( ( row-d, col+d ) )
        return coords


def datasetImageFromArray(array, geoTransform, spatialRef, nodata=None):
    ds = gdal_array.OpenArray( array )
    ds.SetGeoTransform( geoTransform )
    ds.SetSpatialRef( spatialRef )
    if not nodata is None:
        for idx in range( ds.RasterCount ):
            b = ds.GetRasterBand( idx+1 )
            b.SetNoDataValue( nodata )
    return ds

def memoryRasterLayerFromDataset(dataset, vsimemFile, nameStyle):
    ds = gdal.GetDriverByName('GTiff').CreateCopy( vsimemFile, dataset )
    ds = None
    rl = QgsRasterLayer( vsimemFile, 'raster', 'gdal')
    rl.importNamedStyle( nameStyle )
    return rl

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

def adjustsBorder(geom, layer):
    """
    Return { 'isOk', 'geometry', 'message'}
    """
    def getGeomAjustBorder(geom2ajust, geom):
        def getGeomsInternalRing(rings):
            # rings = [ QgsPointXY ]
            for idRing in range(1, len( rings ) ):
                ringPoints = [ QgsPoint( p ) for p in rings[ idRing  ] ]  # [ QgsPoint ]
                line = QgsLineString( ringPoints )
                del ringPoints[:]
                polygon = QgsPolygon()
                polygon.setExteriorRing( line )
                del line
                yield QgsGeometry( polygon )

        def getBorderCombine():
            border = geom.removeInteriorRings()
            border2ajust = geom2ajust.removeInteriorRings()
            geomOp = border2ajust.combine( border )
            msgError = border2ajust.lastError()
            if geomOp is None or msgError:
                msg = f"combine ({msgError})" if msgError else 'combine'
                return { 'isOk': False, 'message': msg }
            
            return { 'isOk': True, 'geometry': geomOp }

        r = getBorderCombine()
        if not r['isOk']:
            return r

        border = r['geometry']
        rings = border.asPolygon()
        geomOp = geom2ajust.difference( geom )
        msgError = geom2ajust.lastError()
        if geomOp is None or msgError:
            msg = f"difference ({msgError})" if msgError else 'diference'
            return { 'isOk': False, 'message': msg }

        if len( rings ) == 1: # Not gaps
            return { 'isOk': True, 'geometry': geomOp }
        
        result = geomOp
        for geom in getGeomsInternalRing( rings):
            geomOp = result.combine( geom )
            msgError = result.lastError()
            if geomOp is None or msgError:
                msg = f"combine rings ({msgError})" if msgError else 'combine rings'
                return { 'isOk': False, 'message': msg }
            result = geomOp
        return { 'isOk': True, 'geometry': geomOp }

    resultOp = { 'isOk': True, 'geometry': geom}
    iter = layer.getFeatures( geom.boundingBox() )
    feat = QgsFeature()
    while iter.nextFeature( feat ):
        g = feat.geometry()
        if geom.overlaps( g ):
            resultOp = getGeomAjustBorder( geom, g )
            if not resultOp['isOk']:
                resultOp['geometry'] = geom
                resultOp['message'] = f"[{feat.id()}]: {resultOp['message']}"
                return resultOp
            geom = resultOp['geometry']
    return resultOp

def messageOutputHtml(title, prefixHtml, dirHtml):
    def readFile(filepath):
        with open(filepath, 'r') as reader:
            content = reader.read()
        return content

    dlg = QgsMessageOutput.createMessageOutput()
    dlg.setTitle( title )

    pathCurrent = os.getcwd()
    os.chdir( dirHtml )
    file = f"{prefixHtml}_{QgsApplication.locale()}.html"
    if not os.path.exists( file):
        file = f"{prefixHtml}_en.html"
    content = readFile( file )
    dlg.setMessage( content, QgsMessageOutput.MessageHtml )
    dlg.showMessage()
    os.chdir( pathCurrent )
