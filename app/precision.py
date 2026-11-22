"""Stream glyph-only OpenCV cleanup into FFmpeg H264 without paid APIs.
Output contains no audio: original audio is reattached in media.py.
"""
import subprocess
import os
from pathlib import Path
import cv2
from .cleanup import inpaint_frame,validate_regions

def limited_video_dimensions(width, height, max_edge=1280):
    """Reduce large frames before OpenCV inpaint/FFmpeg on 512 MiB hosts.

    Zero disables the limit. Ensure even H.264 dimensions and preserve aspect.
    """
    if not max_edge or max(width,height)<=max_edge:
        return width,height
    factor=max_edge/max(width,height)
    out_w=max(2,2*round(width*factor/2))
    out_h=max(2,2*round(height*factor/2))
    return out_w,out_h


def precision_video(source:Path,destination:Path,regions):
    glyph=[r for r in validate_regions(regions) if r['method']=='glyph']
    if not glyph:return None
    # Constrain OpenCV worker pools on 512 MiB Render Free instances.
    cv2.setNumThreads(1)
    cap=cv2.VideoCapture(str(source))
    if not cap.isOpened():raise ValueError('Không thể mở video gốc để làm sạch từng nét chữ.')
    if hasattr(cv2, 'CAP_PROP_BUFFERSIZE'):
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    w,h=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps=float(cap.get(cv2.CAP_PROP_FPS))
    if w<8 or h<8 or not (0<fps<=120):
        cap.release();raise ValueError('Video có thông số hình ảnh không hợp lệ.')
    # Render Free cannot sustain multiple 1080p frame copies + H.264 encoding.
    max_edge=int(os.getenv('VIETFRAME_MAX_VIDEO_EDGE', '1280'))
    out_w,out_h=limited_video_dimensions(w,h,max_edge)
    command=['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y',
             '-threads','1','-filter_threads','1','-f','rawvideo',
             '-pix_fmt','bgr24','-s',f'{out_w}x{out_h}','-r',str(fps),'-i','pipe:0',
             '-an','-c:v','libx264','-threads','1','-preset','veryfast','-crf','18','-pix_fmt','yuv420p',
             '-movflags','+faststart',str(destination)]
    proc=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    frames=0;count=0;skipped=0
    try:
        while True:
            ok,frame=cap.read()
            if not ok:break
            if (out_w,out_h)!=(w,h):
                frame=cv2.resize(frame,(out_w,out_h),interpolation=cv2.INTER_AREA)
            frame,info=inpaint_frame(frame,glyph,frames/fps)
            try:proc.stdin.write(frame.tobytes())
            except BrokenPipeError as exc:raise RuntimeError('FFmpeg không nhận được khung hình đã xử lý.') from exc
            count+=info['glyph_pixels'];skipped+=info['regions_skipped'];frames+=1
        proc.stdin.close()
        if proc.wait(timeout=120)!=0 or not destination.is_file():raise RuntimeError('Xử lý chính xác phụ đề thất bại.')
        if not frames:raise RuntimeError('Không có khung hình nào được xử lý.')
        if not count:raise RuntimeError('Không phát hiện điểm chữ trong vùng/thời gian chọn. Hãy điều chỉnh vùng hoặc dùng Nội suy cạnh cho logo đơn giản; không xuất kết quả che giả.')
        return {'frames':frames,'glyph_pixels':count,'skipped':skipped}
    finally:
        cap.release()
        if proc.poll() is None:proc.kill();proc.wait(timeout=10)
        if proc.stdin and not proc.stdin.closed:proc.stdin.close()
