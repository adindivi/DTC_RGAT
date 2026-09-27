# -*- coding: utf-8 -*-
with open("mobile/templates/index.html", "r", encoding="utf-8") as f:
    content = f.read()

asset_content = content.replace('src="/static/dtc_ondevice_engine.js"', 'src="dtc_ondevice_engine.js"')
asset_content = asset_content.replace('src="/static/vis-network.min.js"', 'src="vis-network.min.js"')

with open("mobile/app/src/main/assets/index.html", "w", encoding="utf-8") as f:
    f.write(asset_content)

print("Updated Android assets index.html successfully!")
