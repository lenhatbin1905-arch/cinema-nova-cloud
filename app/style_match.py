"""Conservative color sampler for reference-video subtitles; does not identify font families."""
from pathlib import Path
import cv2
import numpy as np


def sample_reference_style(source: Path) -> dict:
    cap = cv2.VideoCapture(str(source))
    if not cap.isOpened():
        raise ValueError('Không thể đọc video mẫu.')
    length = cap.get(cv2.CAP_PROP_FRAME_COUNT)
    cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, int(length*0.45)))
    ok, frame = cap.read()
    cap.release()
    if not ok:
        raise ValueError('Không lấy được khung hình video.')
    h, w = frame.shape[:2]
    roi = frame[int(h*.58):int(h*.93), :]
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    # Samples vivid, high-brightness pixels that might belong to decorative captions.
    sat = hsv[:,:,1]
    value = hsv[:,:,2]
    mask = (sat > 105) & (value > 150)
    pixels = roi[mask]
    if len(pixels) < 20:
        return {'detected':False,'font':None,'color':'#FFFFFF','confidence':'low',
                'reason':'Không đủ tín hiệu màu trong vùng phụ đề. Hãy chọn font/màu thủ công.'}
    # Choose most frequent quantized saturated hue, rather than foreground background mean.
    quantized = (pixels // 32) * 32 + 16
    colors, count = np.unique(quantized,axis=0,return_counts=True)
    selected = colors[np.argmax(count)]
    b,g,r = [int(x) for x in selected]
    return {'detected':True,'font':None,'color':f'#{r:02X}{g:02X}{b:02X}',
            'confidence':'low', 'reason':'Gợi ý màu từ khung hình (có thể là màu hậu cảnh). Chưa nhận dạng đúng tên font, cỡ chữ hay hiệu ứng.'}
