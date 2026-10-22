"""Stencil file names, the shared geometric masters, and which stencils are plain geometry vs icons."""

from __future__ import annotations

BASFLO = "BASFLO_U.VSSX"
BASIC = "BASIC_U.VSSX"
NETSYM = "NETSYM_U.VSSX"
SERVER = "SERVER_U.VSSX"
COMPS = "COMPS_U.VSSX"
ORGCH = "ORGCH_U.VSSX"
PEOPLE = "PEOPLE_U.VSSX"
AZ_ENT = "AZUREENTERPRISE_U.VSSX"
AZ_GEN = "AZUREGENERAL_U.VSSX"

# Plain geometric stencils take the theme's fill/line/font; icon stencils keep their own colors.
FILLABLE = {BASFLO, BASIC, ORGCH, "DBCHEN_U.VSSX", "WEBSIT_U.VSSX", "ANNOT_U.VSSX"}

# Clean geometric masters (all verified on Visio 16 BASIC_U / BASFLO_U).
RECT = (BASIC, "Rectangle")
RR = (BASIC, "Rounded Rectangle")
HEX = (BASIC, "Hexagon")
ELL = (BASIC, "Ellipse")
CIRCLE = (BASIC, "Circle")
CAN = (BASIC, "Can")
DB = (BASFLO, "Database")
PARA = (BASIC, "Parallelogram")
DIAMOND = (BASIC, "Diamond")
