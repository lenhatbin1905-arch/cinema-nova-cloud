"""Precision, time-aware caption cleanup.

All positions are percentages. Small rectangles are search bounds, not filled masks.
In glyph mode, only bright caption-like pixels are inpainted inside that bound.
edge is FFmpeg delogo fallback for small fixed logos.
"""
import math
import cv2
import numpy as np

MAX_REGIONS = 80
MAX_AREA_PERCENT = 9.0

def validate_regions(regions):
    if not isinstance(regions,list) or len(regions)>MAX_REGIONS:
        raise ValueError(f'Tối đa {MAX_REGIONS} vùng chữ theo thời gian.')
    out=[]
    for reg in regions:
        if not isinstance(reg,dict):raise ValueError('Vùng chữ không hợp lệ.')
        try:x,y,w,h=(int(reg[k]) for k in ('x','y','w','h'))
        except (KeyError,TypeError,ValueError) as exc:raise ValueError('Thiếu tọa độ vùng chữ.') from exc
        if not (0<=x<=98 and 0<=y<=98 and 2<=w<=100 and 2<=h<=100 and x+w<=100 and y+h<=100):
            raise ValueError('Vùng chữ vượt ra ngoài khung hình.')
        if w*h/100 > MAX_AREA_PERCENT or h>12:
            raise ValueError('Vùng che quá lớn. Hãy chọn sát từng dòng chữ, không che thành dải ngang.')
        method=reg.get('method','glyph')
        if method not in ('glyph','edge'):raise ValueError('Phương pháp che không hợp lệ.')
        purpose=reg.get('purpose','cleanup')
        if purpose not in ('cleanup','subtitle','logo'):
            raise ValueError('Mục đích vùng xử lý không hợp lệ.')
        start=reg.get('start',None);end=reg.get('end',None)
        if (start is None)!=(end is None):raise ValueError('Phải có cả thời điểm bắt đầu và kết thúc.')
        if start is not None:
            try:start=float(start);end=float(end)
            except (ValueError,TypeError) as exc:raise ValueError('Thời gian không hợp lệ.') from exc
            if not (math.isfinite(start) and math.isfinite(end) and 0<=start<end<=1800):
                raise ValueError('Thời gian phải hợp lệ và kết thúc sau bắt đầu.')
        normalized=dict(x=x,y=y,w=w,h=h,method=method)
        # Preserve old regions verbatim for existing projects; only explicit
        # subtitle regions are valid anchors for replacement Vietnamese text.
        if purpose!='cleanup': normalized['purpose']=purpose
        if start is not None:normalized.update(start=round(start,3),end=round(end,3))
        out.append(normalized)
    return out

def pixels(region,width,height):
    x=max(1,min(width-3,round(width*region['x']/100)))
    y=max(1,min(height-3,round(height*region['y']/100)))
    w=min(width-x-1,max(2,round(width*region['w']/100)))
    h=min(height-y-1,max(2,round(height*region['h']/100)))
    return x,y,w,h

def active(reg,seconds):
    return 'start' not in reg or reg['start']<=seconds<reg['end']

def filter_chain(regions,width,height):
    result=[]
    for reg in validate_regions(regions):
        if reg['method']!='edge':continue
        x,y,w,h=pixels(reg,width,height)
        filt=f'delogo=x={x}:y={y}:w={w}:h={h}:show=0'
        if 'start' in reg:filt+=f":enable='between(t,{reg['start']},{reg['end']})'"
        result.append(filt)
    return result

def glyph_mask(frame,bounds):
    """Detect white/yellow high-contrast captions in a narrow ROI; NOT OCR."""
    x,y,w,h=bounds
    roi=frame[y:y+h,x:x+w]
    hsv=cv2.cvtColor(roi,cv2.COLOR_BGR2HSV)
    hh,ss,vv=cv2.split(hsv)
    white=(vv>=205)&(ss<=125)
    yellow=(hh>=13)&(hh<=40)&(ss>=100)&(vv>=155)
    foreground=((white|yellow).astype('uint8')*255)
    count,labels,stats,_=cv2.connectedComponentsWithStats(foreground,8)
    mask=np.zeros((h,w),dtype='uint8')
    for i in range(1,count):
        area=int(stats[i,cv2.CC_STAT_AREA]);left,top,bw,bh=stats[i,:4]
        if 2<=area<=max(3,int(w*h*.10)) and bw<=w*.65 and bh<=h*.9:
            mask[labels==i]=255
    radius=max(4,min(8,round(frame.shape[0]*0.007)))
    kernel=cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(radius*2+1,radius*2+1))
    mask=cv2.dilate(mask,kernel)
    ratio=float(np.count_nonzero(mask))/max(1,mask.size)
    if ratio>.55:mask[:]=0
    return mask

def inpaint_frame(frame,regions,time_s):
    """Restore only detected glyph pixels; background may remain imperfect."""
    total=0;changed=0;skipped=0
    for region in validate_regions(regions):
        if region['method']!='glyph' or not active(region,time_s):continue
        x,y,w,h=pixels(region,frame.shape[1],frame.shape[0])
        mask=glyph_mask(frame,(x,y,w,h));n=int(np.count_nonzero(mask))
        if n<3:skipped+=1;continue
        target=frame[y:y+h,x:x+w]
        frame[y:y+h,x:x+w]=cv2.inpaint(target,mask,3,cv2.INPAINT_TELEA)
        total+=w*h;changed+=n
    return frame,{'area_bound_pixels':total,'glyph_pixels':changed,'regions_skipped':skipped}
