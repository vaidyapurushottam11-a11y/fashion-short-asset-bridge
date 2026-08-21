#!/usr/bin/env python3
import argparse
import json
import pathlib
import subprocess


def run(cmd, capture=False):
    if capture:
        return subprocess.check_output(cmd, text=True).strip()
    subprocess.run(cmd, check=True)


def probe(path):
    raw = run([
        'ffprobe','-v','error','-show_entries',
        'format=duration:stream=index,codec_type,codec_name,width,height,r_frame_rate',
        '-of','json',str(path)
    ], capture=True)
    return json.loads(raw)


def video_stream(info):
    return next((s for s in info.get('streams',[]) if s.get('codec_type') == 'video'), None)


def audio_stream(info):
    return next((s for s in info.get('streams',[]) if s.get('codec_type') == 'audio'), None)


def duration(info):
    return float(info['format']['duration'])


def ass_time(seconds):
    seconds = max(0.0, float(seconds))
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f'{h}:{m:02d}:{s:05.2f}'


def ass_escape(text):
    return str(text).replace('\\','\\\\').replace('{','\\{').replace('}','\\}').replace('\n','\\N')


def overlay_qa(manifest, width, height):
    overlays = manifest.get('overlays', [])
    safe_x = int(manifest.get('text_safe_margin_x', 110))
    safe_top = int(manifest.get('text_safe_top', 180))
    safe_bottom = int(manifest.get('text_safe_bottom', 340))
    safe_width = width - safe_x * 2
    usable_height = height - safe_top - safe_bottom
    report = []
    all_fit = True
    all_safe = True
    for i, item in enumerate(overlays):
        text = str(item.get('text', ''))
        lines = text.split('\n')
        size = int(item.get('font_size', 42))
        spacing = float(item.get('spacing', 0.6))
        estimated_width = max((len(line) * size * 0.61 + max(0, len(line)-1) * spacing) for line in lines) if lines else 0
        estimated_height = len(lines) * size * 1.18
        fits_width = estimated_width <= safe_width
        fits_height = estimated_height <= usable_height
        position = item.get('position', 'top')
        position_safe = position in ('top', 'upper', 'center')
        all_fit = all_fit and fits_width and fits_height
        all_safe = all_safe and position_safe
        report.append({
            'index': i,
            'text': text,
            'position': position,
            'font_size': size,
            'estimated_width': round(estimated_width,1),
            'safe_width': safe_width,
            'fits_safe_width': fits_width,
            'fits_safe_height': fits_height,
            'position_safe_for_reels_ui': position_safe,
        })
    return all_fit, all_safe, report


def build_ass(manifest, path, width, height):
    overlays = manifest.get('overlays', [])
    if not overlays:
        return None
    safe_x = int(manifest.get('text_safe_margin_x', 110))
    header = f'''[Script Info]\nScriptType: v4.00+\nPlayResX: {width}\nPlayResY: {height}\nWrapStyle: 2\nScaledBorderAndShadow: yes\n\n[V4+ Styles]\nFormat: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding\nStyle: Hook,DejaVu Sans Mono,43,&H00FFFFFF,&H000000FF,&H00151515,&H00000000,-1,-1,0,0,92,100,0.8,0,1,1.6,2.2,8,{safe_x},{safe_x},250,1\nStyle: Upper,DejaVu Sans Mono,39,&H00FFFFFF,&H000000FF,&H00151515,&H00000000,-1,-1,0,0,92,100,0.6,0,1,1.4,2.0,8,{safe_x},{safe_x},285,1\nStyle: Center,DejaVu Sans Mono,40,&H00FFFFFF,&H000000FF,&H00151515,&H00000000,-1,-1,0,0,92,100,0.7,0,1,1.5,2.0,5,{safe_x},{safe_x},0,1\n\n[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n'''
    lines = [header]
    for item in overlays:
        position = item.get('position', 'upper')
        style = {'top':'Hook','upper':'Upper','center':'Center'}.get(position, 'Upper')
        start = ass_time(item['start'])
        end = ass_time(item['end'])
        size = int(item.get('font_size', 42))
        spacing = float(item.get('spacing', 0.6))
        text = ass_escape(item['text'])
        # No Face Style typography: narrow italic white type, no box, subtle outline/shadow.
        lines.append(f'Dialogue: 0,{start},{end},{style},,0,0,0,,{{\\fs{size}\\fsp{spacing}\\i1\\b1\\bord1.5\\shad2}}{text}\n')
    path.write_text(''.join(lines), encoding='utf-8')
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--manifest', required=True)
    ap.add_argument('--assets', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--qa', required=True)
    args = ap.parse_args()

    manifest = json.load(open(args.manifest, encoding='utf-8'))
    assets = pathlib.Path(args.assets)
    out_dir = pathlib.Path(args.out)
    qa_dir = pathlib.Path(args.qa)
    out_dir.mkdir(parents=True, exist_ok=True)
    qa_dir.mkdir(parents=True, exist_ok=True)

    reel_id = manifest['reel_id']
    width = int(manifest.get('width', 1080))
    height = int(manifest.get('height', 1920))
    fps = int(manifest.get('fps', 30))
    clips_cfg = manifest['clips']
    if not clips_cfg:
        raise SystemExit('Manifest contains no clips')

    overlay_fit, overlay_safe, overlay_report = overlay_qa(manifest, width, height)
    if not overlay_fit:
        bad = [x['text'] for x in overlay_report if not x['fits_safe_width'] or not x['fits_safe_height']]
        raise SystemExit('Overlay text exceeds safe area: ' + ' | '.join(bad))
    if not overlay_safe:
        bad = [x['text'] for x in overlay_report if not x['position_safe_for_reels_ui']]
        raise SystemExit('Overlay uses unsafe lower Reels UI zone: ' + ' | '.join(bad))

    paths = [assets / c['file'] for c in clips_cfg]
    missing = [str(p) for p in paths if not p.exists()]
    if missing:
        raise SystemExit('Missing assets: ' + ', '.join(missing))

    infos = [probe(p) for p in paths]
    for p, info in zip(paths, infos):
        if not video_stream(info):
            raise SystemExit(f'No video stream: {p}')

    inputs = []
    filters = []
    labels = []
    timeline_total = 0.0
    segment_report = []
    min_speed = float(manifest.get('min_speed', 0.5))
    max_speed = float(manifest.get('max_speed', 2.0))

    for i, (cfg, path, info) in enumerate(zip(clips_cfg, paths, infos)):
        inputs += ['-i', str(path)]
        src_duration = duration(info)
        start = float(cfg.get('source_start', 0.0))
        end = min(float(cfg.get('source_end', src_duration)), src_duration)
        if start < 0 or end <= start:
            raise SystemExit(f'Invalid trim for {path.name}: {start}..{end}')
        trimmed = end - start
        target = float(cfg.get('target_seconds', trimmed))
        if target <= 0:
            raise SystemExit(f'Invalid target_seconds for {path.name}')
        speed = trimmed / target
        if speed < min_speed or speed > max_speed:
            raise SystemExit(f'Speed {speed:.3f}x outside guardrail {min_speed}..{max_speed} for {path.name}')
        zoom = max(1.0, float(cfg.get('zoom', 1.0)))
        sw = int(round(width * zoom))
        sh = int(round(height * zoom))
        label = f'v{i}'
        labels.append(f'[{label}]')
        filters.append(
            f'[{i}:v]trim=start={start:.6f}:end={end:.6f},setpts=PTS-STARTPTS,'
            f'scale={sw}:{sh}:force_original_aspect_ratio=increase,'
            f'crop={width}:{height},fps={fps},setpts={target/trimmed:.9f}*PTS[{label}]'
        )
        timeline_total += target
        segment_report.append({'file':path.name,'source_start':round(start,3),'source_end':round(end,3),'target_seconds':round(target,3),'speed':round(speed,3),'zoom':round(zoom,3)})

    base_label = 'base' if manifest.get('overlays') else 'vout'
    filters.append(''.join(labels) + f'concat=n={len(labels)}:v=1:a=0[{base_label}]')
    ass_path = qa_dir / f'{reel_id}.ass'
    if build_ass(manifest, ass_path, width, height):
        escaped = str(ass_path).replace('\\','/').replace(':','\\:').replace("'","\\'")
        filters.append(f"[base]subtitles='{escaped}'[vout]")

    output = out_dir / manifest.get('output', f'{reel_id}-final.mp4')
    run([
        'ffmpeg','-y',*inputs,'-filter_complex',';'.join(filters),'-map','[vout]','-an',
        '-c:v','libx264','-preset','medium','-crf','18','-pix_fmt','yuv420p','-r',str(fps),
        '-movflags','+faststart',str(output)
    ])

    final = probe(output)
    v = video_stream(final)
    a = audio_stream(final)
    final_duration = duration(final)
    checks = {
        'file_exists': output.exists(),
        'video_codec_h264': bool(v and v.get('codec_name') == 'h264'),
        'resolution_correct': bool(v and v.get('width') == width and v.get('height') == height),
        'silent_no_audio_stream': a is None,
        'duration_matches_manifest': abs(final_duration - timeline_total) <= 0.25,
        'all_source_assets_valid': True,
        'overlay_text_fits_safe_width': overlay_fit,
        'overlay_positions_avoid_lower_reels_ui': overlay_safe,
    }
    passed = all(checks.values())
    qa = {
        'reel_id': reel_id,
        'output': output.name,
        'output_seconds': round(final_duration,3),
        'planned_seconds': round(timeline_total,3),
        'clip_count': len(paths),
        'segments': segment_report,
        'overlay_count': len(manifest.get('overlays',[])),
        'overlay_safe_zone_report': overlay_report,
        'typography_profile': 'NO_FACE_STYLE_EXISTING_REEL_REFERENCE',
        'audio_policy': 'SILENT_NO_AUDIO_STREAM',
        'checks': checks,
        'technical_status': 'PASS' if passed else 'FAIL',
        'editorial_status': 'PENDING_VISUAL_REVIEW',
    }
    (qa_dir / f'{reel_id}.json').write_text(json.dumps(qa, indent=2), encoding='utf-8')
    (qa_dir / f'{reel_id}.txt').write_text('\n'.join([
        f'reel={reel_id}',f'duration={final_duration:.3f}',f'resolution={v.get("width")}x{v.get("height")}',
        f'video_codec={v.get("codec_name")}','audio_stream=NONE' if a is None else 'audio_stream=PRESENT',
        f'overlay_fit={"PASS" if overlay_fit else "FAIL"}',f'overlay_safe_zone={"PASS" if overlay_safe else "FAIL"}',
        'typography=NO_FACE_STYLE_REFERENCE',f'technical_status={"PASS" if passed else "FAIL"}','editorial_status=PENDING_VISUAL_REVIEW'
    ]) + '\n', encoding='utf-8')
    if not passed:
        raise SystemExit('Technical QA failed')


if __name__ == '__main__':
    main()
