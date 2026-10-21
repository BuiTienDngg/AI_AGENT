"""Account for Codex CLI tokens using event usage, never output word count as actual usage."""
from __future__ import annotations
import json
from pathlib import Path
from .core import load_json, save_json, utc_now


def extract_usage(stdout: str):
    """Codex exec --json emits turn.completed with usage counts.

    Prefer per-turn completed events. Some versions only emit thread.token_usage.updated
    (cumulative), so use its last value as fallback, not the sum of snapshots.
    """
    completed = []
    cumulative = []
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except (ValueError, TypeError):
            continue
        if not isinstance(event, dict):
            continue
        kind = str(event.get('type', ''))
        u = event.get('usage') or {}
        if kind == 'thread.token_usage.updated':
            u = (event.get('token_usage') or {}).get('total_token_usage') or u
        if not isinstance(u, dict):
            continue
        if not any(k in u for k in ('input_tokens', 'output_tokens')):
            continue
        normalized = {k: int(u.get(k, 0) or 0) for k in ('input_tokens', 'cached_input_tokens', 'output_tokens')}
        if kind == 'turn.completed':
            completed.append(normalized)
        elif kind == 'thread.token_usage.updated':
            cumulative.append(normalized)
    if completed:
        return {'input_tokens': sum(c['input_tokens'] for c in completed),
                'cached_input_tokens': sum(c['cached_input_tokens'] for c in completed),
                'output_tokens': sum(c['output_tokens'] for c in completed),
                'source': 'codex_cli_turn_completed'}
    if cumulative:
        return {**cumulative[-1], 'source': 'codex_cli_thread_usage'}
    return None


def record_codex_call(workdir, stage, exit_code, usage, duration_seconds, prompt, result_text, configured_model, stderr=''):
    """Persist a call immediately, including failed requests, to survive interrupted runs."""
    workdir = Path(workdir)
    path = workdir / 'token_usage.json'
    previous = load_json(path, default={'version': 1, 'calls': []})
    entries = previous.get('calls', [])
    row = {'call': len(entries) + 1, 'stage': stage, 'timestamp_utc': utc_now(),
           'exit_code': exit_code, 'duration_seconds': round(duration_seconds, 2),
           'model': configured_model or 'codex_cli_default',
           'usage_status': 'measured' if usage else 'unavailable',
           'input_tokens': usage['input_tokens'] if usage else None,
           'cached_input_tokens': usage['cached_input_tokens'] if usage else None,
           'output_tokens': usage['output_tokens'] if usage else None,
           'source': usage['source'] if usage else None,
           # Diagnostics only: lengths are characters, NOT token estimates.
           'visible_text_characters': {'prompt': len(prompt), 'final_json': len(result_text)}}
    entries.append(row)
    save_json(path, summarize_usage(entries))
    return path


def summarize_usage(entries):
    measured = [x for x in entries if x.get('usage_status') == 'measured']
    missing = [x for x in entries if x.get('usage_status') != 'measured']
    i = sum(x['input_tokens'] for x in measured)
    c = sum(x['cached_input_tokens'] for x in measured)
    o = sum(x['output_tokens'] for x in measured)
    stages = {}
    for x in entries:
        stage = x['stage']
        v = stages.setdefault(stage, {'calls': 0, 'measured_calls': 0, 'input_tokens': 0, 'output_tokens': 0, 'cached_input_tokens': 0})
        v['calls'] += 1
        if x['usage_status'] == 'measured':
            v['measured_calls'] += 1
            for k in ('input_tokens', 'output_tokens', 'cached_input_tokens'):
                v[k] += x[k]
    return {'version': 1, 'updated_at_utc': utc_now(), 'measurement_status': 'complete' if not missing else ('partial' if measured else 'unavailable'),
            'calls_total': len(entries), 'calls_measured': len(measured), 'calls_without_usage': len(missing),
            'measured_totals': {'input_tokens': i, 'cached_input_tokens': c, 'output_tokens': o, 'total_tokens': i + o},
            'note': 'cached_input_tokens is a SUBSET of input_tokens. Usage is Codex CLI-reported tokens, not subscription quota or API dollars. Missing stages are NOT included in totals. visible_text_characters are raw string lengths, NOT token estimates.',
            'by_stage': stages, 'calls': entries}


def usage_markdown(stats):
    totals = stats['measured_totals']
    lines = ['# Codex token usage — Game SEO Office', '',
             f"Measurement status: **{stats['measurement_status']}**; measured calls: **{stats['calls_measured']}/{stats['calls_total']}**.", '',
             '| Metric | CLI-reported tokens |', '|---|---:|',
             f"| Input tokens (includes cached) | {totals['input_tokens']:,} |",
             f"| Cached input tokens (subset of input) | {totals['cached_input_tokens']:,} |",
             f"| Output tokens | {totals['output_tokens']:,} |",
             f"| **Total measured tokens** | **{totals['total_tokens']:,}** |", '',
             '## By stage', '', '| Stage | Calls | Measured | Input | Output | Total |',
             '|---|---:|---:|---:|---:|---:|']
    for stage, v in stats['by_stage'].items():
        lines.append(f"| {stage} | {v['calls']} | {v['measured_calls']} | {v['input_tokens']:,} | {v['output_tokens']:,} | {v['input_tokens'] + v['output_tokens']:,} |")
    lines += ['', '## Interpretation', '',
              '- This report counts Codex CLI-reported tokens for this run folder, including all repair/review/translation calls.',
              '- `cached_input_tokens` is already INCLUDED in `input_tokens`; it is not added again.',
              f"- Calls without usage: **{stats['calls_without_usage']}**. Their tokens are not included; totals are incomplete if this number is nonzero.",
              '- These token counts are NOT equivalent to ChatGPT/Codex subscription quota remaining and are NOT an API bill.',
              '- Web requests made by Python do not use model tokens. The CLI may read extra files not captured in local-text token estimates.', '']
    return '\n'.join(lines)


def print_usage(workdir):
    path = Path(workdir) / 'token_usage.json'
    if not path.exists():
        print('Codex token usage: no CLI calls recorded.')
        return
    stats = load_json(path)
    report = Path(workdir) / 'token_usage.md'
    report.write_text(usage_markdown(stats), encoding='utf-8')
    total = stats['measured_totals']
    print(f"Codex usage ({stats['measurement_status']}): {stats['calls_measured']}/{stats['calls_total']} calls measured; input {total['input_tokens']:,}, output {total['output_tokens']:,}, total {total['total_tokens']:,} tokens (cached input {total['cached_input_tokens']:,} included in input).")
    for stage, values in stats['by_stage'].items():
        print(f"  {stage:>12}: {values['input_tokens']:,} in + {values['output_tokens']:,} out (measured {values['measured_calls']}/{values['calls']} calls)")
    if stats['calls_without_usage']:
        print(f"  CAUTION: {stats['calls_without_usage']} call(s) did not report tokens; displayed total is INCOMPLETE.")
    print(f'  Reports: {path}, {report}')
