# -*- coding: utf-8 -*-
from pathlib import Path

from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction

from .lineadivista_dialog import LineaDiVistaDialog


class LineaDiVistaPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = Path(__file__).resolve().parent
        self.action = None
        self.dialog = None

    def tr(self, text):
        return QCoreApplication.translate("LineaDiVista", text)

    def initGui(self):
        icon_path = self.plugin_dir / "icon.png"
        icon = QIcon(str(icon_path)) if icon_path.exists() else QIcon()
        self.action = QAction(icon, self.tr("LineaDiVista"), self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        self.iface.addPluginToMenu(self.tr("&LineaDiVista"), self.action)
        self.iface.addToolBarIcon(self.action)

    def unload(self):
        if self.action:
            self.iface.removePluginMenu(self.tr("&LineaDiVista"), self.action)
            self.iface.removeToolBarIcon(self.action)
        self.action = None
        self.dialog = None

    def run(self):
        if self.dialog is None:
            self.dialog = LineaDiVistaDialog(self.iface)
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()
