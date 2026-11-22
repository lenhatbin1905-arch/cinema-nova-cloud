# VietFrame Studio v0.6 — Precision Cleanup QA

Local regression: 63/63 tests PASS, JavaScript syntax check PASS, Python compileall PASS. Github Actions result must be checked separately.

- Rejected half-screen rectangles and out-of-bound coordinates; checked time-gated delogo filter.
- OpenCV glyph mask preserved pixels outside chosen region and outside cue lifetime; synthetic test measured lower text-region error after inpaint.
- FFmpeg integration rendered real MP4 and kept input audio, no mock output.
- Safe Vietnamese yellow emphasis markup, anti-injection and fail-closed when no detectable text.
- Produced a 4-second synthetic western sample with English captions and Vietnamese styled subtitles; visual check found no large rectangular haze, but a few faint restoration artifacts remain.
- Original TikTok short URL was not available for direct inspection, so exact font matching was NOT validated. The user-provided 56.1-second reference MP4 is already blurred and cannot fully restore hidden background.
- Still pending: OCR detection, optical-flow temporal fill, model-based video inpainting, font recognition from original source, real-world blind panel and signed-in end-to-end browser tests.
- No paid AI API or billing was used. Production deployment NOT approved.
