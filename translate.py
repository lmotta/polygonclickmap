# -*- coding: utf-8 -*-
"""
/***************************************************************************
Name                 : Translate
Description          : Class for translate Plugin
Date                 : 2018-10-19
copyright            : (C) 2018 by Luiz Motta
email                : motta.luiz@gmail.com
 ***************************************************************************/

For create file 'qm'
1) Install pyqt5-dev-tools
2) Define that files need for translation: pluginname.pro
2.1) Define locale.ts(pt.ts, de.ts, ...)
3) Create 'locale.ts' files: pylupdate5 -verbose pluginname.pro
4) Edit your translation: QtLinquist (use Release for create 'qm' file)
4.1) 'locale.qm'
"""

__author__ = 'Luiz Motta'
__date__ = '2021-08-06'
__copyright__ = '(C) 2018, Luiz Motta'
__revision__ = '$Format:%H$'

import os

from qgis.PyQt.QtCore import QTranslator, QCoreApplication
from qgis.core import QgsApplication

class Translate():
    def __init__(self, context):
        self.context = context
        plugin_dir = os.path.dirname(__file__)
        locale = QgsApplication.locale()
        locale_path = os.path.join( plugin_dir, 'i18n', f"{locale}.qm" )
        if os.path.exists( locale_path ):
            self.translator = QTranslator()
            self.translator.load( locale_path )
            QCoreApplication.installTranslator( self.translator )

    def tr(self, message):
        return QCoreApplication.translate( self.context, message )
