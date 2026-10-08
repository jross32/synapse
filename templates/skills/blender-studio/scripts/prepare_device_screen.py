#!/usr/bin/env python3
"""Prepare real browser screenshots for phone/laptop/tablet mockups.

Crops a full-page screenshot to a target aspect ratio without inventing UI.
"""
from __future__ import annotations
import argparse
from pathlib import Path
from PIL import Image

def parse_aspect(value: str) -> float:
    if ":" in value:
        a,b=value.split(":",1)
        return float(a)/float(b)
    return float(value)

def crop_box(w:int,h:int,target:float,gravity:str):
    current=w/h
    if abs(current-target)<1e-6:
        return (0,0,w,h)
    if current>target:
        new_w=max(1,round(h*target))
        x=0 if gravity=="left" else (w-new_w if gravity=="right" else (w-new_w)//2)
        return (x,0,x+new_w,h)
    new_h=max(1,round(w/target))
    y=0 if gravity=="top" else (h-new_h if gravity=="bottom" else (h-new_h)//2)
    return (0,y,w,y+new_h)

def prepare(source:Path,output:Path,aspect:float,gravity:str,max_width:int|None=None):
    im=Image.open(source).convert("RGB")
    box=crop_box(im.width,im.height,aspect,gravity)
    im=im.crop(box)
    if max_width and im.width>max_width:
        new_h=round(im.height*(max_width/im.width))
        im=im.resize((max_width,new_h),Image.Resampling.LANCZOS)
    output.parent.mkdir(parents=True,exist_ok=True)
    im.save(output,quality=94)
    return {"source":str(source),"output":str(output),"size":list(im.size),"crop_box":list(box),"aspect":aspect,"gravity":gravity}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("source",type=Path);p.add_argument("output",type=Path)
    p.add_argument("--aspect",required=True,help="e.g. 390:844 or 16:10")
    p.add_argument("--gravity",choices=["top","center","bottom","left","right"],default="top")
    p.add_argument("--max-width",type=int)
    a=p.parse_args()
    import json
    print(json.dumps(prepare(a.source,a.output,parse_aspect(a.aspect),a.gravity,a.max_width),indent=2))

if __name__=="__main__": main()
