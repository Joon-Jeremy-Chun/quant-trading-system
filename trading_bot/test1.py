# -*- coding: utf-8 -*-
"""
Created on Tue Mar  3 22:42:47 2026

@author: joonc
"""

import os, sys
print("Python:", sys.executable)
print("APCA_API_KEY_ID:", os.getenv("APCA_API_KEY_ID"))
print("APCA_API_SECRET_KEY:", os.getenv("APCA_API_SECRET_KEY"))