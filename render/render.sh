#!/bin/bash
# render.sh <dir>: build → pdf → png → contact sheet
set -e
D=$1; cd "$(dirname "$0")"
python3 engine.py $D/deck.json | grep -v "Нет фото" || true
cd $D && rm -rf r && mkdir r && soffice --headless --convert-to pdf deck.pptx --outdir r >/dev/null 2>&1
pdftoppm -r ${RES:-40} -png r/deck.pdf r/s
python3 -c "
from PIL import Image;import glob
fs=sorted(glob.glob('r/s-*.png'));ims=[Image.open(f) for f in fs];w,h=ims[0].size
o=Image.new('RGB',(w*3+20,(h+10)*((len(ims)+2)//3)),'white')
for i,im in enumerate(ims):o.paste(im,((i%3)*(w+10),(i//3)*(h+10)))
o.save('r/all.png')"
