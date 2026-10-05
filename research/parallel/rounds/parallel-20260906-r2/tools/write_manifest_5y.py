"""Manifest for 5-year reset-metric results ({rows, folds, transfer, final=<row name>}); full-path DD parsed from run.log."""
import json, hashlib, re, sys
R = 'research/parallel/rounds/parallel-20260906-r2'
v, track, note = sys.argv[1], sys.argv[2], sys.argv[3]
tmpl = json.load(open(f'{R}/v388/result_manifest.json'))
raw = open(f'{R}/{v}/{v}_result.json', 'rb').read(); res = json.loads(raw)
fp = dict(re.findall(r'^(\S+) full-path DD ([\d.]+)', open(f'{R}/{v}/run.log').read(), re.M))
rows = {k: dict(x, full_path_dd=float(fp[k]) if k in fp else None) for k, x in res['rows'].items()}
f = rows[res['final']]
m = dict(tmpl); m.update(experiment_id=v, track=track, status='rejected', hashes={'result_sha256': hashlib.sha256(raw).hexdigest()})
m['scenarios'] = {sc: dict(monthly_geometric_net_percent=f['R'], max_drawdown_percent=f['full_path_dd'], fills=0, months=60)
                  for sc in ('normal', 'fee_stress', 'execution_stress')}
m['result'] = {'rows': rows, 'folds': res['folds'], 'final': res['final'], 'transfer': res['transfer'], 'note': note}
m['audit'] = {'passed': False, 'replay_complete': False, 'notes': 'awaiting OpenCode blind audit'}
json.dump(m, open(f'{R}/{v}/result_manifest.json', 'w'), indent=1); print(v, 'manifest ok')
