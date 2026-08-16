def scenario_skeleton(module: str, functions: list[dict]) -> str:
    """Return an unfinished caller-side acceptance scenario for a module."""
    try:
        module_text = str(module).replace('\r', ' ').replace('\n', ' ')
    except Exception:
        module_text = ''

    lines = [
        f'# --- acceptance scenario for {module_text} -----------------------------------------',
        "# Written from the CALLER's side: what does code using this module need back?",
        '# Each TODO below FAILS until you replace it. An unfinished scenario must never pass.',
    ]

    try:
        entries = functions or []
        for function in entries:
            try:
                name = function.get('name', '')
                if not isinstance(name, str) or name.startswith('_'):
                    continue

                raw_args = function.get('args', []) or []
                args = list(raw_args) if not isinstance(raw_args, str) else []
                arg_names = [arg for arg in args if isinstance(arg, str)]
                signature = ', '.join(arg_names)
                placeholders = ', '.join(
                    '0' if arg == 'id' or arg.endswith('_id') else '""'
                    for arg in arg_names
                )

                doc = function.get('doc', '') or ''
                doc_text = str(doc).replace('\r', ' ').replace('\n', ' ')
                comment = f'# {name}({signature})'
                if doc_text:
                    comment += f'  # {doc_text}'

                lines.extend([
                    '',
                    comment,
                    f'_got = {name}({placeholders})',
                    'assert False, (',
                    f'    "TODO: state what a caller needs from {name}(). It returned %r. "',
                    '    "Replace this line with a real assertion." % (_got,))',
                ])
            except Exception:
                continue
    except Exception:
        pass

    return '\n'.join(lines) + '\n'
