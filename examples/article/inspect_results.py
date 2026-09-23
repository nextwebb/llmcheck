"""Print stored companion verdicts and reported evidence; never rerun a judge."""
import argparse
import json
from pathlib import Path


def render(rows):
    if not isinstance(rows, list):
        raise ValueError('Expected a JSON list of companion scenarios.')
    lines = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get('scenario'), str):
            raise ValueError('Each scenario needs a string scenario name.')
        if type(row.get('passed')) is not bool or not isinstance(row.get('results'), list):
            raise ValueError('Each scenario needs a boolean passed and a results list.')
        lines.append(f"{'PASS' if row['passed'] else 'FAIL'} | {row['scenario']}")
        for result in row['results']:
            if not isinstance(result, dict) or not isinstance(result.get('judge_result'), dict):
                raise ValueError('Each result needs a judge_result object.')
            judge = result['judge_result']
            for key, label in [('missing_requirements', 'Missing'),
                               ('forbidden_claims_found', 'Forbidden'),
                               ('unsupported_claims', 'Unsupported')]:
                values = judge.get(key)
                if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
                    raise ValueError(f'{key} must be a list of strings.')
                if values:
                    lines.append(f"  {label}: {'; '.join(values)}")
            reason = judge.get('reason')
            if not isinstance(reason, str):
                raise ValueError('Judge reason must be a string.')
            lines.append(f'  Reason: {reason}')
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('results', type=Path, help='Path to companion replay-results.json')
    args = parser.parse_args()
    try:
        output = render(json.loads(args.results.read_text(encoding='utf-8')))
    except (OSError, ValueError) as exc:
        parser.exit(2, f'Cannot inspect results: {exc}\n')
    print(output)
    print('Stored synthetic results only; no application or judge was executed.')


if __name__ == '__main__':
    main()
