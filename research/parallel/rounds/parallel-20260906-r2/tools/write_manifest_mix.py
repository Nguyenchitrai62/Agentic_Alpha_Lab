import json,hashlib,sys
R='research/parallel/rounds/parallel-20260906-r2'; v,track,note=sys.argv[1],sys.argv[2],sys.argv[3]
tmpl=json.load(open(f'{R}/v388/result_manifest.json'))
raw=open(f'{R}/{v}/{v}_result.json','rb').read(); res=json.loads(raw); f=res['final']['dev4']
m=dict(tmpl); m.update(experiment_id=v,track=track,status='rejected',hashes={'result_sha256':hashlib.sha256(raw).hexdigest()})
m['scenarios']={sc:dict(monthly_geometric_net_percent=f['R'],max_drawdown_percent=f['DD'],fills=0,months=48) for sc in ('normal','fee_stress','execution_stress')}
m['result']={'transfer':res['transfer'],'folds':res['folds'],'final':res['final'],'rows':{k:x['dev4'] for k,x in res['rows'].items()},'note':note}
m['audit']={'passed':False,'replay_complete':False,'notes':'awaiting OpenCode blind audit'}
json.dump(m,open(f'{R}/{v}/result_manifest.json','w'),indent=1); print(v,'manifest ok')
