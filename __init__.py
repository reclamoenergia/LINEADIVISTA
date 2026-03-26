# -*- coding: utf-8 -*-
"""QGIS plugin entry point for LineaDiVista."""


def classFactory(iface):
    from .lineadivista_plugin import LineaDiVistaPlugin

    return LineaDiVistaPlugin(iface)
