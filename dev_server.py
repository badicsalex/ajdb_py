#!/usr/bin/env python3
from ajdb_web.app import create_app, DevelopmentConfig

app = create_app(DevelopmentConfig())
app.run()
