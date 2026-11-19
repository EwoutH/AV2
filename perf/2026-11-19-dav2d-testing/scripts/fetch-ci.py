"""Read-only GitLab evidence capture; requires the logged-in glab CLI."""
import concurrent.futures
import json
import os
import re
from pathlib import Path
import subprocess

OUT = Path(__file__).resolve().parents[1] / 'data'
os.environ['GITLAB_HOST'] = 'code.videolan.org'

def get(path):
    return subprocess.check_output(['glab', 'api', path])

def capture(item):
    project, pipeline = item
    stem = f'{project}-{pipeline}'
    info = json.loads(get(f'projects/{project}/pipelines/{pipeline}'))
    jobs = json.loads(get(f'projects/{project}/pipelines/{pipeline}/jobs?per_page=100'))
    (OUT / f'{stem}-pipeline.json').write_text(json.dumps(info, indent=2) + '\n')
    (OUT / f'{stem}-jobs.json').write_text(json.dumps(jobs, indent=2) + '\n')
    return jobs

if __name__ == '__main__':
    targets = [(4935, 753287), (4935, 753262), (4935, 753097),
               (5480, 753295), (5480, 753284),
               (5491, 753294), (5491, 753293)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(capture, targets))
    for jobs in [results[0], results[3], results[5], results[6]]:
        for job in jobs:
            if job['name'] in ('test-debian', 'test-debian-avm', 'test-debian-tsan',
                               'test-debian-msan', 'test-debian-asan', 'test-avmdec',
                               'build-debian-static', 'build-debian-avx'):
                raw = get(f"projects/{job['pipeline']['project_id']}/jobs/{job['id']}/trace").decode()
                raw = re.sub(r'\x1b\[[0-9;]*[mK]', '', raw)
                raw = re.sub(r'\btoken=\S+', 'token=[redacted]', raw)
                raw = re.sub(r'(https?://)[^/\s:@]+:[^@\s/]+@', r'\1[redacted]@', raw)
                (OUT / f"job-{job['id']}.log").write_text(
                    '\n'.join(line.rstrip() for line in raw.splitlines()) + '\n')
    for name in ['index.html', 'index.src.25d902c24283ab8cfbac54dfa101ad31.html']:
        destination = 'coverage-index.html' if name == 'index.html' else 'coverage-src.html'
        (OUT / destination).write_bytes(get(f'projects/4935/jobs/2986098/artifacts/coverage/{name}'))
    for item, jobs in zip(targets, results):
        print(item, len(jobs), 'jobs;', round(sum(j.get('duration') or 0 for j in jobs), 1), 'runner seconds')
