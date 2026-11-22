"""Validated stationary areas for FFmpeg delogo, applied BEFORE Vietnamese subtitle overlay.
This is interpolation, not temporal AI reconstruction or object tracking.
"""


def validate_regions(regions):
    if len(regions) > 3:
        raise ValueError('Mỗi video tối đa 3 vùng che chữ/logo.')
    out=[]
    for reg in regions:
        x,y,w,h=(int(reg[k]) for k in ('x','y','w','h'))
        if not (0 <= x <= 98 and 0 <= y <= 98 and 2 <= w <= 100 and 2 <= h <= 100):
            raise ValueError('Vùng che nằm ngoài giới hạn 0–100%.')
        if x+w>100 or y+h>100:
            raise ValueError('Vùng che vượt ra ngoài khung video.')
        out.append(dict(x=x,y=y,w=w,h=h))
    return out


def filter_chain(regions, width, height):
    filters=[]
    for r in validate_regions(regions):
        # Avoid edge zero-pixel errors and preserve aspect on even dimensions.
        x=max(0,round(width*r['x']/100)); y=max(0,round(height*r['y']/100))
        w=min(width-x, max(2,round(width*r['w']/100)))
        h=min(height-y, max(2,round(height*r['h']/100)))
        if x+w>width or y+h>height or w<2 or h<2:
            raise ValueError('Kích thước vùng che không hợp lệ.')
        filters.append(f'delogo=x={x}:y={y}:w={w}:h={h}:show=0')
    return filters
